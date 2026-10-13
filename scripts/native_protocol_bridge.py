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
                result = await litellm.aresponses(**payload, use_chat_completions_api=True)
        except Exception as exc:
            # SDK exception text can contain request URLs or credentials.
            raise HTTPException(502, f"Upstream conversion failed: {type(exc).__name__}") from None
        if not payload.get("stream"):
            return JSONResponse(result.model_dump(mode="json", exclude_none=True))

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
