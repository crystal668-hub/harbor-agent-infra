from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "recovery_sequence", Path(__file__).resolve().parents[1] / "scripts/run_recovery_sequence.py"
)
sequence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sequence)


def plan_for(tmp_path):
    batches = []
    for index in range(2):
        trial_id = f"trial-{index}"
        manifest = tmp_path / f"manifest-{index}.json"
        manifest.write_text(json.dumps({"slots": [
            {"original_trial_id": trial_id, "approved": True},
        ]}))
        config = tmp_path / f"config-{index}.yaml"
        config.write_text("frozen")
        approval = tmp_path / f"approval-{index}.json"
        approval.write_text("approved")
        batch = {"run": str(index), "manifest": manifest.name, "config": config.name,
                 "approval": approval.name, "output_dir": f"output-{index}",
                 "trial_ids": [trial_id]}
        for field in ("manifest", "config", "approval"):
            batch[field + "_sha256"] = sequence.digest(tmp_path / batch[field])
        batches.append(batch)
    return {"batches": batches, "log_dir": "logs"}


@pytest.mark.parametrize("mode", ["success", "failed_trial", "interrupted", "dry_run"])
def test_order_and_failure_boundaries(tmp_path, monkeypatch, mode):
    plan = plan_for(tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--dry-run" in args:
            return SimpleNamespace(returncode=0)
        output = tmp_path / args[args.index("--output-dir") + 1]
        output.mkdir()
        if mode == "interrupted":
            return SimpleNamespace(returncode=137)
        failed = int(mode == "failed_trial")
        (output / "recovery-result.json").write_text(json.dumps({
            "total_slots": 1, "executed": 1, "skipped": 0,
            "succeeded": 1 - failed, "failed": failed,
        }))
        (output / "recovery-state.json").write_text(json.dumps({
            "status": "finished", "slots": {"trial": "finished"},
        }))
        return SimpleNamespace(returncode=failed)

    monkeypatch.setattr(sequence.subprocess, "run", fake_run)
    if mode == "interrupted":
        with pytest.raises(FileNotFoundError):
            sequence.run_sequence(plan, tmp_path, execute=True)
        assert len(calls) == 3  # Both preflights, then only the first batch.
    else:
        code = sequence.run_sequence(plan, tmp_path, execute=mode != "dry_run")
        assert code == int(mode == "failed_trial")
        assert len(calls) == (2 if mode == "dry_run" else 4)
        assert [c[c.index("--output-dir") + 1] for c in calls[:2]] == [
            "output-0", "output-1",
        ]
        if mode == "dry_run":
            assert not (tmp_path / "logs").exists()
        else:
            assert [c[c.index("--output-dir") + 1] for c in calls[2:]] == [
                "output-0", "output-1",
            ]


@pytest.mark.parametrize("problem", ["changed_approval", "existing_output", "scope_change"])
def test_rejects_unsafe_plan_before_running(tmp_path, monkeypatch, problem):
    plan = plan_for(tmp_path)
    if problem == "changed_approval":
        (tmp_path / plan["batches"][0]["approval"]).write_text("changed")
    elif problem == "existing_output":
        (tmp_path / plan["batches"][0]["output_dir"]).mkdir()
    else:
        plan["batches"][0]["trial_ids"] = ["unapproved"]

    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before launching a subprocess")

    monkeypatch.setattr(sequence.subprocess, "run", forbidden)
    with pytest.raises(ValueError):
        sequence.run_sequence(plan, tmp_path, execute=True)
