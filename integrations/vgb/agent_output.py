from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def response_from_openclaw_log(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            envelope, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(envelope, dict) or not isinstance(envelope.get("meta"), dict):
            continue
        meta: dict[str, Any] = envelope["meta"]
        if isinstance(meta.get("finalAssistantVisibleText"), str):
            return meta["finalAssistantVisibleText"]
        payloads = envelope.get("payloads")
        if isinstance(payloads, list):
            texts = [
                item["text"]
                for item in payloads
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            if texts:
                return "\n\n".join(texts)
    raise ValueError("OpenClaw output did not contain a complete assistant response")
