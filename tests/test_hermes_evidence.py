from __future__ import annotations

import json
import os
import shlex
import sqlite3
import sys
import time

import pytest

from adapters.hermes.evidence import (
    collect,
    evidence_command,
    prepare,
    session_record,
    snapshot,
    write_json,
)


@pytest.fixture
def native(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    home.mkdir()
    (home / "logs").mkdir()
    logs = tmp_path / "agent"
    logs.mkdir()
    db = sqlite3.connect(home / "state.db")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, model_config TEXT);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT);"
        "CREATE VIRTUAL TABLE messages_fts USING fts5(content);"
    )
    # This executable only reads synthetic local data; it cannot call a provider.
    cli = tmp_path / "hermes-cli" / "hermes"
    cli.parent.mkdir()
    cli.write_text(
        f"#!{sys.executable}\n"
        + """
import json, os, sqlite3, sys, time
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ["sessions", "export"] and "--redact" in args
sid = args[args.index("--session-id") + 1]
source = args[args.index("--source") + 1]
mode = os.environ.get("FIXTURE_EXPORT_MODE", "ok")
if mode == "slow":
    Path(os.environ["FIXTURE_PID"]).write_text(str(os.getpid()))
    time.sleep(30)
if mode == "fail" or (mode == "fallback" and source == "oneshot"):
    print("export failed " + os.environ.get("OPENAI_API_KEY", ""), file=sys.stderr)
    sys.exit(7)
with sqlite3.connect(Path(os.environ["HERMES_HOME"]) / "state.db") as db:
    messages = [{"role": r, "content": c} for r, c in db.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (sid,))]
record = {"id": "wrong-session" if mode == "wrong" else sid,
          "messages": [] if mode == "empty" else messages}
path = Path(args[2])
path.write_text("broken json" if mode == "malformed" else json.dumps(record) + "\\n")
"""
    )
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", str(cli.parent) + os.pathsep + os.environ["PATH"])
    prepare(home, logs, None)
    yield home, logs, db
    db.close()


def add_session(db, sid="new", source="oneshot", content="partial answer"):
    db.execute("INSERT INTO sessions VALUES (?, ?, '{}')", (sid, source))
    db.execute(
        "INSERT INTO messages(session_id,role,content) VALUES (?, 'user', 'question')", (sid,)
    )
    db.execute(
        "INSERT INTO messages(session_id,role,content) VALUES (?, 'assistant', ?)", (sid, content)
    )
    db.commit()


@pytest.mark.parametrize("source", ["oneshot", "cli"])
def test_wal_snapshot_and_export_preserve_real_partial_messages(native, source):
    home, logs, db = native
    add_session(db, source=source)
    assert (home / "state.db-wal").stat().st_size > 32
    report = collect(home, logs, None)
    assert report["status"] == "exported"
    assert report["exports"][0]["source"] == source
    assert (
        session_record(logs / "hermes-session.jsonl")["messages"][-1]["content"] == "partial answer"
    )
    with sqlite3.connect(logs / "hermes-native/state.db") as backup:
        assert backup.execute("SELECT count(*) FROM messages").fetchone()[0] == 2
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not backup.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%fts%'"
        ).fetchall()
    assert not list(logs.rglob("*.tmp"))


def test_redacts_db_export_logs_and_stderr_without_exporting_environment(native, monkeypatch):
    home, logs, db = native
    secret = "opaque-provider-credential"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    add_session(db, content="answer " + secret)
    db.execute("UPDATE sessions SET model_config=?", (json.dumps({"password": "unknown-value"}),))
    db.execute("INSERT INTO messages_fts VALUES (?)", (secret,))
    db.commit()
    (home / "logs/agent.log").write_text("retry " + secret + " Bearer another-token")
    (home / "logs/errors.log.1").write_text("OPENAI_API_KEY=" + secret)
    (home / "logs/.env").write_text("must not be copied")
    monkeypatch.setenv("FIXTURE_EXPORT_MODE", "fallback")
    report = collect(home, logs, None)
    assert report["status"] == "exported"
    assert report["exports"][0]["return_code"] == 7
    assert "[REDACTED]" in report["exports"][0]["stderr"]
    for file in logs.rglob("*"):
        if file.is_file():
            assert secret.encode() not in file.read_bytes()
            assert b"unknown-value" not in file.read_bytes()
            assert file.stat().st_mode & 0o777 == 0o600
    assert not (logs / "hermes-native/.env").exists()


@pytest.mark.parametrize("mode", ["fail", "empty", "malformed", "wrong"])
def test_export_failures_leave_evidence_without_fake_session(native, monkeypatch, mode):
    home, logs, db = native
    add_session(db)
    (home / "logs/errors.log").write_text("synthetic export diagnostic")
    monkeypatch.setenv("FIXTURE_EXPORT_MODE", mode)
    report = collect(home, logs, None)
    assert report["status"] == "export_failed"
    assert report["failure_stage"] == "session_export"
    assert all(not attempt["nonempty"] for attempt in report["exports"]) if mode == "fail" else True
    assert (logs / "hermes-native/state.db").is_file()
    assert (logs / "hermes-native/errors.log").is_file()
    assert (logs / "hermes-evidence.json").is_file()
    assert not (logs / "hermes-session.jsonl").exists()
    assert not (logs / "trajectory.json").exists()


def test_no_messages_or_no_new_session_is_explicit(native, monkeypatch):
    home, logs, db = native
    report = collect(home, logs, None)
    assert report["status"] == "no_session" and report["exports"] == []
    add_session(db)
    db.execute("DELETE FROM messages")
    db.commit()
    report = collect(home, logs, None)
    assert report["status"] == "export_failed"
    assert all(attempt["status"] == "no_messages" for attempt in report["exports"])
    assert not (logs / "hermes-session.jsonl").exists()


def test_ambiguous_sessions_never_merge_or_use_parent_bulk_export(native):
    home, logs, db = native
    add_session(db, "one")
    add_session(db, "two")
    (logs / "hermes-session.jsonl").write_text('{"id":"unrelated","messages":[{}]}\n')
    report = collect(home, logs, None)
    assert report["reason"] == "ambiguous_new_sessions"
    assert report["exports"] == []
    assert not (logs / "hermes-session.jsonl").exists()


def test_known_resume_id_restores_valid_export_after_parent_truncation(native, monkeypatch):
    home, logs, db = native
    add_session(db, "resume")
    add_session(db, "unrelated")
    prior = {"id": "resume", "messages": [{"role": "assistant", "content": "saved answer"}]}
    write_json(logs / "hermes-session.jsonl", prior)
    prepare(home, logs, "resume")
    (logs / "hermes-session.jsonl").write_text("")
    monkeypatch.setenv("FIXTURE_EXPORT_MODE", "fail")
    report = collect(home, logs, "resume")
    assert report["retained_existing_session"]
    assert session_record(logs / "hermes-session.jsonl") == prior
    assert {a["session_id"] for a in report["exports"]} == {"resume"}


def test_new_run_ignores_existing_sessions(native):
    home, logs, db = native
    add_session(db, "old")
    prepare(home, logs, None)
    add_session(db, "new", source="cli")
    report = collect(home, logs, None)
    assert report["session_id"] == "new"


def test_snapshot_deadline_and_export_subprocess_are_bounded(native, monkeypatch, tmp_path):
    home, logs, db = native
    add_session(db)
    with pytest.raises(TimeoutError):
        snapshot(home, logs / "expired.db", (), time.monotonic() - 1)
    monkeypatch.setenv("FIXTURE_EXPORT_MODE", "slow")
    pid = tmp_path / "export.pid"
    monkeypatch.setenv("FIXTURE_PID", str(pid))
    started = time.monotonic()
    report = collect(home, logs, "new", budget=1)
    assert time.monotonic() - started < 3
    assert report["status"] == "export_failed"
    assert report["exports"][0]["status"] == "timed_out"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid.read_text()), 0)


def test_remote_command_quotes_session_identity():
    identity = "session ' $(touch /tmp/should-never-run)"
    arguments = shlex.split(evidence_command("collect", identity).split("python3 -c ", 1)[1])
    assert arguments[-1] == identity
    compile(arguments[0], "evidence.py", "exec")
