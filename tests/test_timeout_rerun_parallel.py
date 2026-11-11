"""Parallel timeout dispatch is scoped, hash-bound, and globally capped."""

import asyncio
import copy
import shutil
from pathlib import Path

import pytest
from test_timeout_rerun_execution import dispatch
from test_timeout_rerun_plan import timeout_fixture

from harbor_agent_infra.resume.io import read_object, write_object
from harbor_agent_infra.timeout_rerun.execution import (
    jobs_to_start,
    run_campaign,
    run_with_global_limit,
)
from harbor_agent_infra.timeout_rerun.outcomes import scan
from harbor_agent_infra.timeout_rerun.plan import (
    create_plan,
    digest,
    files,
    load_plan,
    object_digest,
    set_toml,
)


def parallel_fixture(tmp_path, *, activation_ordinal=1):
    sources = [
        timeout_fixture(tmp_path, harness=harness, provider="qwen", repeat=2)
        for harness in ("claude-code", "hermes", "openclaw")
    ]
    plan = create_plan(sources, tmp_path / "campaign", Path("runtime-lock.json"), repeat=2)
    root = Path(plan["root"])
    slot = next(s for s in plan["slots"] if s["harness"] == "openclaw")
    base = root / "parallel-inputs" / slot["slot_id"]
    source = read_object(root / "inputs" / slot["slot_id"] / "job.json")
    target = copy.deepcopy(source)
    target_task = base / "task" / slot["task_name"]
    target_task.parent.mkdir(parents=True)
    shutil.copytree(Path(source["tasks"][0]["path"]), target_task)
    old_lock = read_object(root / "runtime-lock.json")
    new_lock = copy.deepcopy(old_lock)
    image = new_lock["harness_images"]["openclaw"]
    image["digest"] = "sha256:" + "1" * 64
    image["manifest_sha256"] = "2" * 64
    immutable = image["reference"] + "@" + image["digest"]
    target["tasks"][0]["path"] = str(target_task)
    target["agents"][0]["kwargs"]["preinstalled"].update(
        image=immutable, manifest_sha256=image["manifest_sha256"]
    )
    (target_task / "task.toml").write_text(
        set_toml(
            (target_task / "task.toml").read_text(),
            "environment", "docker_image", immutable,
        )
    )
    write_object(base / "job.json", target)
    write_object(base / "runtime-lock.json", new_lock)
    condition = {
        "slot_id": slot["slot_id"],
        "activation_ordinal": activation_ordinal,
        "source_job_sha256": digest(root / "inputs" / slot["slot_id"] / "job.json"),
        "target_job_sha256": digest(base / "job.json"),
        "target_runtime_lock_sha256": digest(base / "runtime-lock.json"),
        "target_task_files": files(target_task),
    }
    amendment = {
        "schema_version": "timeout-parallel-amendment.v1",
        "plan_sha256": plan["plan_sha256"],
        "authorization": "User approves global cap two with different harnesses",
        "reason": "Test isolated cross-harness replacement conditions",
        "slot_ids": [s["slot_id"] for s in plan["slots"]],
        "max_active_trials": 2,
        "condition_changes": [condition],
    }
    amendment["sha256"] = object_digest(amendment)
    write_object(root / "parallel-amendment.json", amendment)
    return plan, root / "manifest.json", amendment, base


def test_parallel_amendment_selects_three_single_task_jobs(tmp_path):
    _, manifest, amendment, base = parallel_fixture(tmp_path)
    plan = load_plan(manifest)
    state = scan(plan)
    jobs = jobs_to_start(plan, state)
    assert len(jobs) == 3 and all(len(items) == 1 for _, items in jobs)
    assert {s["harness"] for s in plan["slots"]} == {"claude-code", "hermes", "openclaw"}
    openclaw_job = next(cfg for cfg, _ in jobs if cfg["agents"][0]["import_path"].endswith(
        "OpenClawAgent"
    ))
    assert openclaw_job["tasks"][0]["path"].startswith(str(base))
    assert openclaw_job["agents"][0]["kwargs"]["preinstalled"]["image"].endswith(
        "sha256:" + "1" * 64
    )
    preview = asyncio.run(run_campaign(manifest, dry_run=True, parallel=True))
    assert preview["jobs_to_start"] == preview["slots_to_start"] == 3
    assert preview["global_concurrency"] == amendment["max_active_trials"] == 2
    with pytest.raises(ValueError, match="explicit flag"):
        asyncio.run(run_campaign(manifest, dry_run=True))


def test_parallel_condition_keeps_historical_trial_on_original_image(tmp_path):
    plan, manifest, _, _ = parallel_fixture(tmp_path, activation_ordinal=2)
    slot = next(s for s in plan["slots"] if s["harness"] == "openclaw")
    original = dispatch(
        {**plan, "slots": [slot]}, kind="NetworkConnectionError", answer=None, score=None,
        job_name="historical-openclaw",
    )
    state = scan(load_plan(manifest))
    assert state["slots"][slot["slot_id"]]["attempts"][0]["path"] == str(original)


@pytest.mark.parametrize("mutation", ["job", "task", "lock", "scope", "cap"])
def test_parallel_amendment_rejects_drift(tmp_path, mutation):
    _, manifest, amendment, base = parallel_fixture(tmp_path)
    if mutation == "job":
        payload = read_object(base / "job.json")
        payload["agents"][0]["model_name"] = "wrong"
        write_object(base / "job.json", payload)
    elif mutation == "task":
        (next((base / "task").glob("*/task.toml"))).write_text("[agent]\ntimeout_sec=1\n")
    elif mutation == "lock":
        payload = read_object(base / "runtime-lock.json")
        payload["harness_images"]["codex"]["digest"] = "changed"
        write_object(base / "runtime-lock.json", payload)
    else:
        amendment.pop("sha256")
        amendment["slot_ids" if mutation == "scope" else "max_active_trials"] = (
            [] if mutation == "scope" else 4
        )
        amendment["sha256"] = object_digest(amendment)
        write_object(manifest.parent / "parallel-amendment.json", amendment)
    with pytest.raises((ValueError, OSError)):
        load_plan(manifest)


def test_global_cap_overlaps_two_harnesses_then_starts_third():
    async def scenario():
        started = []
        active = set()
        max_active = 0
        release = [asyncio.Event() for _ in range(3)]
        two_started = asyncio.Event()
        third_started = asyncio.Event()

        async def runner(config, _):
            nonlocal max_active
            index = config["index"]
            started.append(index)
            active.add(index)
            max_active = max(max_active, len(active))
            if len(started) == 2:
                two_started.set()
            if len(started) == 3:
                third_started.set()
            await release[index].wait()
            active.remove(index)

        work = [({"index": i, "harness": h}, [{"slot_id": str(i)}]) for i, h in enumerate(
            ("claude-code", "hermes", "openclaw")
        )]
        task = asyncio.create_task(run_with_global_limit(work, 2, runner))
        await asyncio.wait_for(two_started.wait(), 2)
        assert started == [0, 1] and active == {0, 1}
        assert work[0][0]["harness"] != work[1][0]["harness"]
        release[0].set()
        await asyncio.wait_for(third_started.wait(), 2)
        assert active == {1, 2} and max_active == 2
        release[1].set()
        release[2].set()
        await task

    asyncio.run(scenario())
