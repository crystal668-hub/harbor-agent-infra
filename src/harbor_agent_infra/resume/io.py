from __future__ import annotations

import json
from pathlib import Path


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_object(path: Path, value: dict) -> bool:
    """Replace atomically, without touching already equivalent metadata."""
    if path.is_file() and read_object(path) == value:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
    return True


def read_journal(path: Path, *, repair=False) -> list[dict]:
    """A hard kill can leave only the last append incomplete; never hide middle corruption."""
    if not path.exists():
        return []
    data = path.read_bytes()
    rows, valid_bytes = [], 0
    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            valid_bytes += len(line)
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            if index != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError(f"Corrupt event journal: {path}") from None
            if repair:
                with path.open("r+b") as stream:
                    stream.truncate(valid_bytes)
            break
        if not isinstance(row, dict):
            raise ValueError(f"Invalid event journal entry: {path}")
        rows.append(row)
        valid_bytes += len(line)
    if repair and valid_bytes and not data[:valid_bytes].endswith(b"\n"):
        with path.open("ab") as stream:
            stream.write(b"\n")
    return rows
