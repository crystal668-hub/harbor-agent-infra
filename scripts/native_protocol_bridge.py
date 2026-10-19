"""Local protocol conversion for the locked Harbor CLI agents.

Uses LiteLLM from Harbor's locked environment; credentials are loaded only at
runtime. Start before running the Codex/Claude and Claude Code/GPT templates.
"""

from __future__ import annotations

import argparse
import hmac
import os
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

OUTPUT_CAP = 64_000
CODEX_MODELS = {
    "openai": "gpt-6.1-sol",
    "anthropic": "claude-opus-5.5",
    "qwen": "qwen3.8-max",
    "deepseek": "deepseek-v4-pro",
}


def _normalize_assistant_input(payload: dict[str, object]) -> None:
    """Remove empty assistant text items that Claude's chat endpoint rejects."""
    input_items = payload.get("input")
    if not isinstance(input_items, list):
        return

    normalized: list[object] = []
    for item in input_items:
        if (
            not isinstance(item, dict)
            or item.get("type", "message") != "message"
            or item.get("role") != "assistant"
        ):
            normalized.append(item)
            continue

        content = item.get("content")
        if isinstance(content, str):
            if content:
                normalized.append(item)
            continue
        if not isinstance(content, list):
            normalized.append(item)
            continue

        filtered_content = [
            part
            for part in content
            if not (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and part.get("text") == ""
            )
        ]
        if filtered_content:
            normalized.append({**item, "content": filtered_content})

    payload["input"] = normalized


def create_app(*, gpt_model: str = "gpt-6.1-sol", claude_model: str = "claude-opus-5.5") -> FastAPI:
    # Avoid LiteLLM's remote model-pricing refresh during local startup.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm

    litellm.suppress_debug_info = True
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def dispatch(request: Request, *, messages: bool):
        prefix = "OPENAI" if messages else "ANTHROPIC"
        model = gpt_model if messages else claude_model
        key = os.environ.get(f"{prefix}_API_KEY", "")
        base = os.environ.get(f"{prefix}_BASE_URL", "").rstrip("/")
        if not key or not base:
            raise HTTPException(503, f"Missing {prefix} provider configuration")
        auth = request.headers.get("authorization", "")
        supplied = auth.removeprefix("Bearer ") or request.headers.get("x-api-key", "")
        if not hmac.compare_digest(supplied, key):
            raise HTTPException(401, "Invalid bridge credential")
        payload = await request.json()
        if payload.get("model") != model:
            raise HTTPException(400, "Model does not match the configured bridge route")
        if not messages:
            _normalize_assistant_input(payload)
        payload["max_tokens" if messages else "max_output_tokens"] = OUTPUT_CAP
        # A Claude credential is already validated with Chat Completions at
        # this gateway. Its Responses route has no upstream channel.
        if not base.endswith("/v1"):
            base += "/v1"
        payload["model"] = f"openai/{model}"
        payload.update(api_key=key, api_base=base, timeout=240)
        try:
            if messages:
                result = await litellm.anthropic.messages.acreate(**payload)
            else:
                # LiteLLM preserves a Responses reasoning dict when it has a
                # summary field. This gateway's Chat Completions endpoint
                # requires reasoning_effort to be a string. Keep the requested
                # effort and omit the unsupported summary presentation setting.
                reasoning = payload.get("reasoning")
                if isinstance(reasoning, dict):
                    payload["reasoning"] = {
                        name: value for name, value in reasoning.items() if name != "summary"
                    }
                # Keep an explicit Chat cap even if the Responses conversion
                # drops its mapped optional parameter for this provider.
                payload["extra_body"] = {**payload.get("extra_body", {}), "max_tokens": OUTPUT_CAP}
                result = await litellm.aresponses(**payload, use_chat_completions_api=True)
        except Exception as exc:
            # SDK exception text can contain request URLs or credentials.
            raise HTTPException(502, f"Upstream conversion failed: {type(exc).__name__}") from None
        if not payload.get("stream"):
            response = (
                result.model_dump(mode="json", exclude_none=True)
                if hasattr(result, "model_dump") else result
            )
            return JSONResponse(response)

        async def events() -> AsyncIterator[bytes]:
            async for event in result:
                if isinstance(event, bytes):
                    yield event
                else:
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n".encode()

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/v1/messages")
    async def messages(request: Request):
        return await dispatch(request, messages=True)

    @app.post("/v1/responses")
    async def responses(request: Request):
        return await dispatch(request, messages=False)

    @app.post("/{provider}/v1/responses")
    async def capped_responses(provider: str, request: Request):
        import httpx

        if provider not in CODEX_MODELS:
            raise HTTPException(404, "Unknown capped provider route")
        if provider == "anthropic":
            return await dispatch(request, messages=False)
        prefix = provider.upper()
        key = os.environ.get(f"{prefix}_API_KEY", "")
        base = os.environ.get(f"{prefix}_BASE_URL", "").rstrip("/")
        if not key or not base:
            raise HTTPException(503, f"Missing {prefix} provider configuration")
        if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {key}"):
            raise HTTPException(401, "Invalid bridge credential")
        payload = await request.json()
        if payload.get("model") != CODEX_MODELS[provider]:
            raise HTTPException(400, "Model does not match the configured bridge route")
        payload["max_output_tokens"] = OUTPUT_CAP
        if not base.endswith("/v1"):
            base += "/v1"
        client = httpx.AsyncClient(timeout=240)
        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    base + "/responses",
                    json=payload,
                    headers={"authorization": f"Bearer {key}"},
                ),
                stream=True,
            )
        except Exception:
            await client.aclose()
            raise HTTPException(502, "Upstream request failed") from None
        if upstream.status_code != 200:
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(upstream.status_code, "Upstream rejected capped request")

        async def passthrough() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            passthrough(), media_type=upstream.headers.get("content-type", "text/event-stream")
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4141)
    parser.add_argument("--gpt-model", default="gpt-6.1-sol")
    parser.add_argument("--claude-model", default="claude-opus-5.5")
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env", override=False)
    import uvicorn

    uvicorn.run(
        create_app(gpt_model=args.gpt_model, claude_model=args.claude_model),
        host=args.host,
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
