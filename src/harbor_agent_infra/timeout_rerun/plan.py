"""Freeze selected representatives and new execution inputs without touching sources."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from harbor import JobConfig

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.resume.io import read_object, write_object

SCHEMA = "timeout-rerun-plan.v1"
TIMEOUT = 43200
POLICY = {
    "agent_timeout_sec": TIMEOUT,
    "source_timeout_sec": 7200,
    "engineering_replacements": 2,
    "scoring_retries": 2,
    "concurrency": 2,
    "group": "skills_off",
    "repeat": 1,
}
NAME = re.compile(
    r"^(openclaw|hermes|codex|claude-code)-(openai|anthropic|qwen|deepseek)-repeat1(?:-.*)?$"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def native_index(root: Path) -> dict[str, tuple[Path, dict]]:
    indexed = {}
    for p in sorted(root.glob("jobs/*/*/result.json")):
        trial = read_object(p)
        tid = trial["id"]
        if tid in indexed:
            raise ValueError(f"Duplicate native Trial UUID in {root}: {tid}")
        indexed[tid] = (p, trial)
    return indexed


def representative(record: dict, indexed: dict) -> tuple[Path, dict]:
    embedded = record.get("trial_result") or record.get("raw", {}).get("harbor_trial_result") or {}
    tid = (record.get("final_attempt") or {}).get("trial_id") or embedded.get("id")
    if not tid or (embedded.get("id") and tid != embedded["id"]):
        raise ValueError("Conflicting selected representative identity")
    if tid not in indexed:
        # Historical split-track snapshots may explicitly reference a sibling run.
        references = [
            record.get("trial_result_path"),
            (record.get("final_attempt") or {}).get("trial_result_path"),
            unquote(urlparse(embedded.get("trial_uri", "")).path) + "/result.json",
        ]
        for reference in references:
            if reference and Path(reference).is_file():
                candidate = read_object(Path(reference))
                if candidate.get("id") == tid:
                    indexed[tid] = (Path(reference).resolve(), candidate)
                    break
        if tid not in indexed:
            raise ValueError(f"Selected Trial not found by UUID: {tid}")
    path, trial = indexed[tid]
    if trial["task_name"] != record["task_name"]:
        raise ValueError("Selected Trial task differs from slot")
    if embedded and embedded.get("exception_info") != trial.get("exception_info"):
        raise ValueError("Projection and native exception evidence differ")
    return path, trial


def task_directory(snapshot: Path, trial: dict) -> Path:
    local = snapshot / "tasks" / trial["task_name"]
    saved = Path(trial["config"]["task"]["path"])
    for path in (local, saved):
        if (path / "task.toml").is_file():
            return path.resolve()
    raise ValueError(f"Materialized task unavailable: {trial['task_name']}")


def timeout_evidence(trial: dict, task: Path) -> dict | None:
    ex = trial.get("exception_info") or {}
    if ex.get("exception_type") != "AgentTimeoutError":
        return None
    if not trial.get("finished_at"):
        raise ValueError("Timeout Trial is not terminal")
    config = trial["config"]
    agent = config["agent"]
    task_config = tomllib.loads((task / "task.toml").read_text())
    effective = agent.get("override_timeout_sec") or task_config.get("agent", {}).get("timeout_sec")
    multiplier = config.get("agent_timeout_multiplier")
    multiplier = config.get("timeout_multiplier", 1) if multiplier is None else multiplier
    effective = effective * multiplier if effective is not None else None
    if effective is not None and agent.get("max_timeout_sec") is not None:
        effective = min(effective, agent["max_timeout_sec"])
    if effective != POLICY["source_timeout_sec"]:
        return None
    clocks = trial.get("agent_execution") or {}
    if clocks.get("started_at") and clocks.get("finished_at"):
        duration = (
            datetime.fromisoformat(clocks["finished_at"])
            - datetime.fromisoformat(clocks["started_at"])
        ).total_seconds()
        if not 7195 <= duration <= 7320:
            raise ValueError(f"Timeout clock needs review: {duration}")
        return {
            "kind": "native_agent_timeout",
            "effective_timeout_sec": effective,
            "agent_duration_sec": duration,
        }
    # The accepted repeat1 orphan reconstruction is explicit, not a generic text match.
    if (
        trial["task_name"]
        == (
            "property_calculation_advanced__"
            "property_calculation_advanced_020_azulene_internal_conversion_rate"
        )
        and "no final answer at the 7200 second protocol limit" in ex.get("exception_message", "")
        and "Reconstructed from orphan container evidence" in ex.get("exception_traceback", "")
    ):
        return {
            "kind": "accepted_orphan_timeout_disposition",
            "effective_timeout_sec": effective,
            "authorization": "Included in the user-approved repeat1 12h rerun plan",
        }
    raise ValueError("Agent timeout without clock or accepted disposition needs review")


def inventory(snapshots: list[Path]) -> tuple[list[dict], list[dict]]:
    sources, slots, seen = [], [], set()
    for snapshot in snapshots:
        snapshot = snapshot.resolve()
        match = NAME.fullmatch(snapshot.name)
        if not match:
            raise ValueError(f"Not a repeat1 formal snapshot: {snapshot}")
        harness, provider = match.groups()
        run = f"{harness}-{provider}-repeat1"
        if run in seen:
            raise ValueError(f"Select exactly one final snapshot per combination: {run}")
        seen.add(run)
        envelope = read_object(snapshot / "results.json")
        indexed = native_index(snapshot)
        identities = set()
        for record in envelope["results"]:
            identity = (record["group_id"], record["task_name"])
            if (
                identity in identities
                or record["group_id"] != "skills_off"
                or record.get("repeat_index") not in (None, 0)
            ):
                raise ValueError("Duplicate slot, wrong group or wrong repeat")
            identities.add(identity)
            embedded = record.get("trial_result") or record.get("raw", {}).get(
                "harbor_trial_result", {}
            )
            if "AgentTimeoutError" not in (
                record.get("execution_error_kind"),
                (embedded.get("exception_info") or {}).get("exception_type"),
            ):
                continue
            path, trial = representative(record, indexed)
            if (trial.get("exception_info") or {}).get("exception_type") != "AgentTimeoutError":
                continue
            task = task_directory(snapshot, trial)
            evidence = timeout_evidence(trial, task)
            if evidence is None:
                continue
            key = object_digest([run, *identity, 0])
            slots.append(
                {
                    "slot_id": key,
                    "run": run,
                    "harness": harness,
                    "provider": provider,
                    "task_name": record["task_name"],
                    "group_id": "skills_off",
                    "repeat_index": 0,
                    "source_trial_id": trial["id"],
                    "source_trial_path": str(path),
                    "source_trial_sha256": digest(path),
                    "source_task": str(task),
                    "source_task_files": files(task),
                    "evidence": evidence,
                }
            )
        sources.append(
            {
                "run": run,
                "snapshot": str(snapshot),
                "source_run_id": envelope.get("source_run_id") or envelope["run_id"],
                "results_sha256": digest(snapshot / "results.json"),
                "slots": len(identities),
            }
        )
    return sources, sorted(slots, key=lambda s: (s["run"], s["task_name"]))


def set_toml(text: str, section: str, key: str, value) -> str:
    pattern = rf"(^\[{re.escape(section)}\]\s*\n)(.*?)(?=^\[|\Z)"

    def edit(match):
        body = match[2]
        line = f"{key} = {json.dumps(value)}\n"
        entry = rf"^{re.escape(key)}\s*=.*\n?"
        body = (
            re.sub(entry, lambda _: line, body, flags=re.M)
            if re.search(entry, body, re.M)
            else body + line
        )
        return match[1] + body

    result, count = re.subn(pattern, edit, text, flags=re.M | re.S)
    if count != 1:
        raise ValueError(f"Task needs exactly one [{section}] section")
    return result


def execution_code() -> dict[str, str]:
    workspace = Path(__file__).resolve().parents[3]
    paths = [workspace / "uv.lock", workspace / "src/harbor_agent_infra/harness_runner.py"]
    for directory in (
        "adapters",
        "integrations/vgb",
        "src/harbor_agent_infra/harbor",
        "src/harbor_agent_infra/timeout_rerun",
        "src/harbor_agent_infra/resume",
    ):
        paths.extend(
            p
            for p in (workspace / directory).rglob("*")
            if p.is_file() and p.suffix in {".py", ".js", ".mjs"}
        )
    return {str(p): digest(p) for p in sorted(paths)}


def target_job(slot: dict, root: Path, lock) -> dict:
    trial = read_object(Path(slot["source_trial_path"]))
    config = copy.deepcopy(trial["config"])
    harness = slot["harness"]
    agent = config.pop("agent")
    if agent.get("skills"):
        raise ValueError("Timeout rerun requires skills_off")
    import_paths = {
        "codex": "adapters.preinstalled:CodexAgent",
        "claude-code": "adapters.preinstalled:ClaudeCodeAgent",
        "hermes": "adapters.hermes.adapter:HermesAgent",
        "openclaw": "adapters.openclaw.adapter:OpenClawAgent",
    }
    agent.update(
        name=None,
        import_path=import_paths[harness],
        override_timeout_sec=TIMEOUT,
        max_timeout_sec=TIMEOUT,
    )
    image = lock.execution_image(harness, "preinstalled")
    kwargs = agent.setdefault("kwargs", {})
    kwargs["preinstalled"] = {
        "manifest_sha256": image.manifest_sha256,
        "image": image.immutable_reference,
        "parent_image": lock.agent_base_image.immutable_reference,
        "platform": image.platform,
    }
    if harness == "hermes":
        kwargs.update(
            version=lock.hermes.source_tag,
            source_commit=lock.hermes.source_commit,
            install_branch=lock.hermes.install_branch,
        )
    else:
        kwargs["version"] = getattr(lock, harness.replace("-", "_")).version
    if harness == "openclaw":
        kwargs["timeout"] = TIMEOUT
    task = config.pop("task")
    task["path"] = str(root / "inputs" / slot["slot_id"] / "task" / slot["task_name"])
    job = {k: v for k, v in config.items() if k in JobConfig.model_fields}
    job.update(
        job_name=slot["slot_id"],
        jobs_dir=str(root / "jobs"),
        tasks=[task],
        agents=[agent],
        agent_timeout_multiplier=1,
        n_attempts=1,
        n_concurrent_trials=2,
        retry={"max_retries": 0},
        quiet=True,
    )
    return JobConfig.model_validate(job).model_dump(mode="json")


def create_plan(
    snapshots: list[Path],
    output: Path,
    runtime_lock: Path,
    *,
    baseline_dispositions: Path | None = None,
) -> dict:
    output = output.resolve()
    sources, slots = inventory(snapshots)
    from harbor_agent_infra.timeout_rerun.dispositions import freeze_dispositions

    dispositions = freeze_dispositions(baseline_dispositions, sources, slots)
    if output.exists() or any(
        output.is_relative_to(Path(s["snapshot"])) or Path(s["snapshot"]).is_relative_to(output)
        for s in sources
    ):
        raise ValueError("Campaign output must be new and separate from source snapshots")
    lock = load_runtime_lock(runtime_lock)
    targets = {s["slot_id"]: target_job(s, output, lock) for s in slots}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".timeout-plan-", dir=output.parent))
    try:
        shutil.copy2(runtime_lock, stage / "runtime-lock.json")
        for d in dispositions:
            evidence = stage / "baseline-evidence" / d["evidence_sha256"]
            evidence.parent.mkdir(exist_ok=True)
            shutil.copy2(d["evidence_file"], evidence)
        for slot in slots:
            base = stage / "inputs" / slot["slot_id"]
            task = base / "task" / slot["task_name"]
            shutil.copytree(slot["source_task"], task)
            text = (task / "task.toml").read_text()
            text = set_toml(text, "agent", "timeout_sec", TIMEOUT)
            text = set_toml(
                text,
                "environment",
                "docker_image",
                lock.execution_image(slot["harness"], "preinstalled").immutable_reference,
            )
            (task / "task.toml").write_text(text)
            write_object(base / "job.json", targets[slot["slot_id"]])
            slot["input_files"] = files(base)
            before = read_object(Path(slot["source_trial_path"]))["config"]
            after = targets[slot["slot_id"]]
            slot["condition_change"] = {
                "statistical_role": "timeout_budget_amendment",
                "source_agent": before["agent"],
                "target_agent": after["agents"][0],
                "source_task_sha256": slot["source_task_files"]["task.toml"],
                "target_task_sha256": digest(task / "task.toml"),
            }
        manifest = {
            "schema_version": SCHEMA,
            "root": str(output),
            "created_at": datetime.now(UTC).isoformat(),
            "policy": copy.deepcopy(POLICY),
            "runtime_lock_sha256": digest(stage / "runtime-lock.json"),
            "sources": sources,
            "slots": slots,
            "total_slots": sum(s["slots"] for s in sources),
            "candidate_slots": len(slots),
            "initial_trial_hours": len(slots) * TIMEOUT / 3600,
            "baseline_score_dispositions": dispositions,
            "implementation_files": execution_code(),
        }
        manifest["plan_sha256"] = object_digest(manifest)
        write_object(stage / "manifest.json", manifest)
        lines = ["run\ttask_name\tsource_trial_id\tevidence\tagent_timeout_sec"]
        for slot in slots:
            lines.append(
                "\t".join(
                    [
                        slot["run"],
                        slot["task_name"],
                        slot["source_trial_id"],
                        slot["evidence"]["kind"],
                        str(TIMEOUT),
                    ]
                )
            )
        (stage / "slots.tsv").write_text("\n".join(lines) + "\n")
        write_object(
            stage / "review-decisions.json",
            {"schema_version": "timeout-rerun-review.v1", "decisions": []},
        )
        stage.rename(output)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def load_plan(path: Path) -> dict:
    plan = read_object(path)
    checksum = plan.pop("plan_sha256", None)
    if (
        plan.get("schema_version") != SCHEMA
        or checksum != object_digest(plan)
        or plan.get("policy") != POLICY
    ):
        raise ValueError("Frozen timeout plan identity or policy changed")
    plan["plan_sha256"] = checksum
    if plan.get("implementation_files") != execution_code():
        from harbor_agent_infra.timeout_rerun.scope import validate_implementation_transition

        if not validate_implementation_transition(plan, execution_code()):
            raise ValueError("Execution implementation changed after campaign freeze")
    root = Path(plan["root"])
    for d in plan.get("baseline_score_dispositions", []):
        if digest(root / "baseline-evidence" / d["evidence_sha256"]) != d["evidence_sha256"]:
            raise ValueError("Frozen baseline authorization changed")
    if (
        path.resolve() != root / "manifest.json"
        or digest(root / "runtime-lock.json") != plan["runtime_lock_sha256"]
    ):
        raise ValueError("Campaign moved or frozen runtime lock changed")
    for source in plan["sources"]:
        if digest(Path(source["snapshot"]) / "results.json") != source["results_sha256"]:
            raise ValueError("Source snapshot changed after planning")
    for slot in plan["slots"]:
        if digest(Path(slot["source_trial_path"])) != slot["source_trial_sha256"]:
            raise ValueError("Source Trial changed after planning")
        if files(Path(slot["source_task"])) != slot["source_task_files"]:
            raise ValueError("Source task changed after planning")
        if files(root / "inputs" / slot["slot_id"]) != slot["input_files"]:
            raise ValueError("Frozen execution inputs changed")
    return plan
