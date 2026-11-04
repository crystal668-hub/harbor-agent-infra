"""Bounded, stdlib-only collector executed inside the Trial environment.

The saved DB is a redacted logical snapshot: ordinary tables only, without
indexes, triggers or FTS shadow copies that could retain unredacted text.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"authorization|password|secret|credential|^token$)",
    re.I,
)
_SECRET_ENV = re.compile(r"KEY|SECRET|TOKEN(?!S)|PASSWORD|CREDENTIAL|AUTH", re.I)
_TOKEN = re.compile(r"\b(?:sk-|sk-ant-|ghp_|github_pat_)[A-Za-z0-9_-]{8,}")
_AUTH = re.compile(r"(?i)(\b(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+")
_QUERY = re.compile(r"(?i)([?&](?:api_key|token|access_token|key|password|secret)=)[^&\s]+")
_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:[a-z0-9_]*api_key|access_token|refresh_token|password|client_secret)"
    r"[\"']?\s*[:=]\s*[\"']?)[^\s,\"';&}]+"
)


def scrub(value, secrets=()):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEY.search(key) else scrub(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item, secrets) for item in value]
    if isinstance(value, bytes):
        # Opaque binary can contain secrets, including FTS internals. Do not retain it.
        return b"[REDACTED BINARY]"
    if not isinstance(value, str):
        return value
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = _TOKEN.sub("[REDACTED]", value)
    value = _AUTH.sub(r"\1[REDACTED]", value)
    value = _QUERY.sub(r"\1[REDACTED]", value)
    value = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
    return _ASSIGNMENT.sub(r"\1[REDACTED]", value)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        temporary.chmod(0o600)
        json.dump(value, stream, ensure_ascii=False, indent=None if path.suffix == ".jsonl" else 2)
        stream.write("\n")
    temporary.replace(path)


def session_record(path: Path, session_id: str | None = None):
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(records) != 1 or not isinstance(records[0], dict):
        raise ValueError("expected exactly one session")
    record = records[0]
    if not isinstance(record.get("id"), str) or not isinstance(record.get("messages"), list):
        raise ValueError("invalid session")
    if session_id is not None and record["id"] != session_id:
        raise ValueError("session identity mismatch")
    return record


def prepare(home: Path, logs: Path, session_id: str | None):
    native = logs / "hermes-native"
    native.mkdir(parents=True, exist_ok=True, mode=0o700)
    baseline = {"session_id": session_id, "ids": [], "status": "ok"}
    try:
        if (home / "state.db").exists():
            with closing(
                sqlite3.connect((home / "state.db").as_uri() + "?mode=ro", uri=True, timeout=1)
            ) as db:
                baseline["ids"] = [row[0] for row in db.execute("SELECT id FROM sessions")]
        previous = logs / "hermes-session.jsonl"
        if previous.exists() and session_id:
            record = session_record(previous, session_id)
            if record["messages"]:
                write_json(native / "previous-session.jsonl", scrub(record, secret_values()))
    except Exception as exc:
        baseline.update(status="failed", error=type(exc).__name__)
    write_json(native / "baseline.json", baseline)


def snapshot(home: Path, target: Path, secrets, deadline: float):
    """SQLite backup includes committed WAL frames; never copies a live main file."""

    def progress(*_):
        if time.monotonic() >= deadline:
            raise TimeoutError("database snapshot deadline")

    def quote(identifier):
        return '"' + identifier.replace('"', '""') + '"'

    temporary = target.with_suffix(".tmp")
    try:
        # The unsanitized consistent copy lives only in memory.
        with closing(sqlite3.connect(":memory:")) as backup:
            with closing(
                sqlite3.connect((home / "state.db").as_uri() + "?mode=ro", uri=True, timeout=1)
            ) as source:
                source.backup(backup, pages=128, progress=progress, sleep=0.01)
                ordinary = {r[1] for r in backup.execute("PRAGMA table_list") if r[2] == "table"}
                tables = [
                    (name, sql)
                    for name, sql in backup.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                    if name in ordinary and not name.startswith("sqlite_")
                ]
                with closing(sqlite3.connect(temporary)) as redacted:
                    temporary.chmod(0o600)
                    for name, sql in tables:
                        progress()
                        redacted.execute(sql)
                        columns = [
                            r[1] for r in backup.execute(f"PRAGMA table_info({quote(name)})")
                        ]
                        insert = (
                            f"INSERT INTO {quote(name)} VALUES ({','.join('?' for _ in columns)})"
                        )
                        for row in backup.execute(f"SELECT * FROM {quote(name)}"):
                            progress()
                            cleaned = []
                            for column, value in zip(columns, row, strict=True):
                                if _SECRET_KEY.search(column) and value is not None:
                                    cleaned.append("[REDACTED]")
                                elif isinstance(value, str):
                                    try:
                                        value = json.dumps(scrub(json.loads(value), secrets))
                                    except (ValueError, TypeError):
                                        value = scrub(value, secrets)
                                    cleaned.append(value)
                                else:
                                    cleaned.append(scrub(value, secrets))
                            redacted.execute(insert, cleaned)
                    assert redacted.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    redacted.commit()
        temporary.replace(target)
        return {
            "status": "ok",
            "method": "sqlite_backup_redacted_logical_copy",
            "tables": [name for name, _ in tables],
            "integrity_check": "ok",
            "omitted": ["indexes", "triggers", "virtual_and_shadow_tables"],
            "binary_values": "redacted",
        }
    finally:
        temporary.unlink(missing_ok=True)


def collect(home: Path, logs: Path, session_id: str | None, *, budget: float = 24):
    native = logs / "hermes-native"
    native.mkdir(parents=True, exist_ok=True, mode=0o700)
    secrets = secret_values()
    report = {"schema_version": "hermes-evidence.v1", "exports": [], "logs": []}
    deadline = time.monotonic() + budget
    try:
        # Diagnostics and native state survive even when session export fails.
        try:
            report["database"] = snapshot(
                home, native / "state.db", secrets, min(deadline, time.monotonic() + 5)
            )
        except Exception as exc:
            report["database"] = {"status": "failed", "error": type(exc).__name__}
        for path in sorted((home / "logs").glob("*")):
            if not re.fullmatch(r"(?:agent|errors)\.log(?:\.[0-9]+)?", path.name):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            try:
                size = path.stat().st_size
                with path.open("rb") as stream:
                    stream.seek(max(0, size - 1024 * 1024))
                    content = stream.read(1024 * 1024).decode("utf-8", errors="replace")
                destination = native / path.name
                with destination.open("w") as stream:
                    destination.chmod(0o600)
                    stream.write(scrub(content, secrets))
                report["logs"].append(
                    {"file": path.name, "source_bytes": size, "truncated": size > 1024 * 1024}
                )
            except OSError as exc:
                report["logs"].append({"file": path.name, "error": type(exc).__name__})
            if time.monotonic() >= deadline or len(report["logs"]) >= 10:
                break
        report["failure_stage"] = "session_selection"
        baseline = json.loads((native / "baseline.json").read_text())
        if baseline["status"] != "ok" and session_id is None:
            report["reason"] = "baseline_unavailable"
            raise ValueError("baseline unavailable")
        selected_source = None
        if session_id is None:
            if report["database"]["status"] != "ok":
                report["reason"] = "session_inventory_unavailable"
                raise ValueError("session inventory unavailable")
            with closing(sqlite3.connect(native / "state.db")) as db:
                rows = db.execute("SELECT id, source FROM sessions").fetchall()
            for source in ("oneshot", "cli"):
                candidates = [
                    sid for sid, kind in rows if kind == source and sid not in baseline["ids"]
                ]
                if len(candidates) > 1:
                    report["reason"] = "ambiguous_new_sessions"
                    raise ValueError("ambiguous new sessions")
                if candidates:
                    session_id, selected_source = candidates[0], source
                    break
        if session_id is None:
            report["status"] = "no_session"
            return report
        report["session_id"] = session_id
        report["failure_stage"] = "session_export"
        # Both sources use the same exact ID. Never fall back to another session.
        for source in (selected_source,) if selected_source == "cli" else ("oneshot", "cli"):
            candidate = native / "export.candidate.jsonl"
            candidate.unlink(missing_ok=True)
            attempt = {
                "source": source,
                "session_id": session_id,
                "return_code": None,
                "stderr": "",
                "nonempty": False,
            }
            report["exports"].append(attempt)
            try:
                result = subprocess.run(
                    [
                        "hermes",
                        "sessions",
                        "export",
                        str(candidate),
                        "--session-id",
                        session_id,
                        "--source",
                        source,
                        "--redact",
                    ],
                    env={**os.environ, "HERMES_HOME": str(home)},
                    capture_output=True,
                    text=True,
                    timeout=max(0.01, min(8, deadline - time.monotonic())),
                )
                attempt.update(
                    return_code=result.returncode,
                    stdout=scrub(result.stdout[-4096:], secrets),
                    stderr=scrub(result.stderr[-4096:], secrets),
                    nonempty=candidate.is_file() and candidate.stat().st_size > 0,
                )
                if result.returncode:
                    attempt["status"] = "command_failed"
                    continue
                record = session_record(candidate, session_id)
                if not record["messages"]:
                    attempt["status"] = "no_messages"
                    continue
                write_json(logs / "hermes-session.jsonl", scrub(record, secrets))
                attempt["status"] = "exported"
                report["status"] = "exported"
                break
            except subprocess.TimeoutExpired as exc:
                stderr = exc.stderr or b""
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="replace")
                attempt.update(status="timed_out", stderr=scrub(stderr[-4096:], secrets))
            except Exception as exc:
                attempt.update(status="failed", error=type(exc).__name__)
            finally:
                attempt["nonempty"] = candidate.is_file() and candidate.stat().st_size > 0
                candidate.unlink(missing_ok=True)
        else:
            report["status"] = "export_failed"
        return report
    except Exception as exc:
        report.update(status="collection_failed", error=type(exc).__name__)
        return report
    finally:
        # Parent Harbor exports directly to the final path, even on cancellation.
        # Keep only a validated single session; restore a prior valid resume export.
        final = logs / "hermes-session.jsonl"
        if report.get("status") != "exported":
            retained = False
            if session_id:
                for path in (final, native / "previous-session.jsonl"):
                    try:
                        record = session_record(path, session_id)
                        if record["messages"]:
                            write_json(final, scrub(record, secrets))
                            retained = True
                            break
                    except (OSError, ValueError, TypeError):
                        pass
            if not retained:
                final.unlink(missing_ok=True)
            report["retained_existing_session"] = retained
        (native / "previous-session.jsonl").unlink(missing_ok=True)
        if report.get("status") in {"exported", "no_session"}:
            report.pop("failure_stage", None)
        write_json(logs / "hermes-evidence.json", scrub(report, secrets))


def record_conversion(logs: Path, status: str, error: str | None = None):
    try:
        path = logs / "hermes-evidence.json"
        report = json.loads(path.read_text()) if path.exists() else {}
        report["conversion"] = {"status": status, **({"error": error} if error else {})}
        write_json(path, report)
    except Exception:
        # Diagnostics must never replace the run's primary failure.
        pass


def secret_values():
    values = [v for k, v in os.environ.items() if _SECRET_ENV.search(k) and v]
    values.extend(json.loads(os.environ.get("HAI_HERMES_SECRET_VALUES", "[]")))
    return values


def evidence_command(phase: str, session_id: str | None) -> str:
    script = Path(__file__).read_text()
    args = [phase, "/tmp/hermes", "/logs/agent", session_id or ""]
    return (
        'export PATH="$HOME/.local/bin:$PATH"; python3 -c '
        + shlex.quote(script)
        + " "
        + shlex.join(args)
    )


if __name__ == "__main__":
    os.umask(0o077)
    phase, home, logs, session_id = sys.argv[1:]
    if phase == "prepare":
        prepare(Path(home), Path(logs), session_id or None)
    else:
        report = collect(Path(home), Path(logs), session_id or None)
        if report.get("status") == "exported" or report.get("retained_existing_session"):
            print(json.dumps({"id": report["session_id"]}))
