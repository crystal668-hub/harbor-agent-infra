"""Validate or explicitly execute an ordered list of approved hai recovery batches."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(plan: dict, workspace: Path) -> None:
    outputs = set()
    identities = set()
    for batch in plan["batches"]:
        for field in ("manifest", "approval", "config"):
            path = workspace / batch[field]
            if digest(path) != batch[field + "_sha256"]:
                raise ValueError(f"Changed input: {path}")
        manifest = json.loads((workspace / batch["manifest"]).read_text())
        approved = sorted(s["original_trial_id"] for s in manifest["slots"] if s["approved"])
        if approved != sorted(batch["trial_ids"]) or len(set(approved)) != len(approved):
            raise ValueError("Approved Trial scope differs from sequence plan")
        if identities.intersection(approved):
            raise ValueError("Duplicate Trial across batches")
        identities.update(approved)
        output = (workspace / batch["output_dir"]).resolve()
        if output in outputs or output.exists():
            raise ValueError(f"Recovery output already exists or is duplicated: {output}")
        outputs.add(output)


def command(batch: dict, execute: bool) -> list[str]:
    args = ["uv", "run", "--locked", "--python", "3.12", "hai", "recover",
            batch["manifest"], "--config", batch["config"],
            "--output-dir", batch["output_dir"]]
    return args if execute else [*args, "--dry-run"]


def run_sequence(plan: dict, workspace: Path, *, execute: bool) -> int:
    """No polling, retries, merging or implicit continuation of existing batches."""
    validate(plan, workspace)
    # Validate every frozen Job before starting the first actual batch.
    for batch in plan["batches"]:
        subprocess.run(command(batch, False), cwd=workspace, check=True)
    if not execute:
        return 0
    log_dir = workspace / plan["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    any_failed = False
    with (log_dir / "sequence.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate(plan, workspace)
        journal = log_dir / "sequence.jsonl"
        for batch in plan["batches"]:
            name = batch["run"]
            log = log_dir / (name + ".log")
            def record(event: str, **details) -> None:
                with journal.open("a") as stream:
                    stream.write(json.dumps({"at": datetime.now(UTC).isoformat(),
                                             "run": name, "event": event, **details}) + "\n")

            record("start", log=str(log))
            try:
                with log.open("xb") as stream:
                    completed = subprocess.run(command(batch, True), cwd=workspace,
                                               stdout=stream, stderr=subprocess.STDOUT)
                output = workspace / batch["output_dir"]
                result = json.loads((output / "recovery-result.json").read_text())
                state = json.loads((output / "recovery-state.json").read_text())
                count = len(batch["trial_ids"])
                if (state["status"] != "finished" or result["total_slots"] != count
                        or result["executed"] != count or result["skipped"] != 0
                        or result["succeeded"] + result["failed"] != count
                        or set(state["slots"].values()) != {"finished"}
                        or completed.returncode != (1 if result["failed"] else 0)):
                    raise ValueError(f"Incomplete or inconsistent recovery batch: {name}")
                any_failed |= bool(result["failed"])
                record("finished", returncode=completed.returncode,
                       succeeded=result["succeeded"], failed=result["failed"])
            except BaseException as exc:
                record("stopped", error_type=type(exc).__name__)
                raise
        with journal.open("a") as stream:
            stream.write(json.dumps({"event": "sequence_finished", "any_failed": any_failed,
                                     "at": datetime.now(UTC).isoformat()}) + "\n")
    return 1 if any_failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--execute", action="store_true", help="start the approved batches")
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[1]
    plan = json.loads(args.plan.read_text())
    return run_sequence(plan, workspace, execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
