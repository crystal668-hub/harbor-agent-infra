"""Bind native Codex custom providers to Harbor's resolved cap-bridge endpoint."""

from __future__ import annotations

from harbor.agents.installed.codex import Codex


class CodexAgent(Codex):
    def _build_effective_config(self, openai_base_url: str | None = None):
        config = super()._build_effective_config(openai_base_url)
        provider_id = config.get("model_provider")
        if provider_id in {"deepseek-responses", "qwen-responses"}:
            if not openai_base_url:
                raise ValueError("custom Codex Responses providers require the cap-bridge URL")
            provider = config["model_providers"][provider_id]
            if "base_url" in provider:
                raise ValueError("custom Codex provider base_url must come from Harbor")
            provider["base_url"] = openai_base_url
        return config
