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
from harbor_agent_infra.timeout_rerun.policy import TimeoutPolicy

SCHEMA = "timeout-rerun-plan.v2"
LEGACY_SCHEMA = "timeout-rerun-plan.v1"
# Keep the v1 contract independent of defaults for newly created campaigns.
LEGACY_POLICY = {
    "agent_timeout_sec": 43200, "source_timeout_sec": 7200,
    "engineering_replacements": 2, "scoring_retries": 2,
    "concurrency": 2, "group": "skills_off", "repeat": 1,
}
NAME = re.compile(
    r"^(openclaw|hermes|codex|claude-code)-(openai|anthropic|qwen|deepseek)-"
    r"(open-generation-)?repeat([1-9][0-9]*)(?:-.*)?$"
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


def timeout_evidence(
    trial: dict, task: Path, *, source_timeout_sec: int = 7200
) -> dict | None:
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
    if effective != source_timeout_sec:
        return None
    clocks = trial.get("agent_execution") or {}
    if clocks.get("started_at") and clocks.get("finished_at"):
        duration = (
            datetime.fromisoformat(clocks["finished_at"])
            - datetime.fromisoformat(clocks["started_at"])
        ).total_seconds()
        if not effective - 5 <= duration <= effective + 120:
            raise ValueError(f"Timeout clock needs review: {duration}")
        return {
            "kind": "native_agent_timeout",
            "effective_timeout_sec": effective,
            "agent_duration_sec": duration,
        }
    raise ValueError("Agent timeout without execution clock needs review")


def inventory(
    snapshots: list[Path], *, policy: TimeoutPolicy | None = None
) -> tuple[list[dict], list[dict]]:
    policy = policy or TimeoutPolicy()
    if not snapshots:
        raise ValueError("At least one final snapshot is required")
    sources, slots, seen = [], [], set()
    benchmark = None
    benchmark_seen = False
    for snapshot in snapshots:
        snapshot = snapshot.resolve()
        envelope = read_object(snapshot / "results.json")
        match = NAME.fullmatch(snapshot.name)
        if not match:
            raise ValueError(f"Not a formal repeat snapshot: {snapshot}")
        harness, provider, namespace, repeat_text = match.groups()
        repeat = int(repeat_text)
        if repeat != policy.repeat:
            raise ValueError("Source repeat differs from campaign policy")
        run = f"{harness}-{provider}-{namespace or ''}repeat{repeat}"
        if run in seen:
            raise ValueError(f"Select exactly one final snapshot per combination: {run}")
        seen.add(run)
        protocol_path = snapshot / "protocol.json"
        protocol = read_object(protocol_path) if protocol_path.is_file() else {}
        for identifier in (envelope.get("source_run_id"), envelope.get("run_id"),
                           protocol.get("run_id")):
            declared_run = NAME.fullmatch(str(identifier or ""))
            if declared_run and declared_run.groups() != match.groups():
                raise ValueError("Source run identity differs from snapshot name")
        for key, expected in (("harness", harness), ("provider", provider),
                              ("repeat", repeat), ("repeat_index", repeat - 1)):
            if key in protocol and protocol[key] != expected:
                raise ValueError(f"Frozen protocol {key} differs from source identity")
        identity = envelope.get("benchmark_identity", protocol.get("benchmark_identity"))
        if (protocol.get("benchmark_identity") is not None
                and identity != protocol["benchmark_identity"]):
            raise ValueError("Source benchmark identity differs from frozen protocol")
        if identity is not None:
            if not isinstance(identity, dict) or not all(
                isinstance(identity.get(k), str) and identity[k] for k in ("version", "subset")
            ):
                raise ValueError("Invalid source benchmark identity")
            expected_subset = "open-generation" if namespace else "property-calculation"
            if identity["subset"] != expected_subset:
                raise ValueError("Source namespace differs from benchmark subset")
        elif repeat != 1:
            raise ValueError("Source benchmark identity is required beyond legacy repeat1")
        if benchmark_seen and identity != benchmark:
            raise ValueError("Cannot mix benchmark versions, subsets or views in one campaign")
        benchmark, benchmark_seen = identity, True
        if not envelope.get("results"):
            raise ValueError("Source snapshot has no final records")
        manifest_path = snapshot / "run-manifest.json"
        if manifest_path.is_file():
            manifest = read_object(manifest_path)
            if "finished_at" in manifest and not manifest["finished_at"]:
                raise ValueError("Source run is still active or incomplete")
        indexed = native_index(snapshot)
        identities = set()
        for record in envelope["results"]:
            identity = (record["group_id"], record["task_name"])
            if (
                identity in identities
                or record["group_id"] != "skills_off"
                or (record.get("repeat_index") != repeat - 1
                    and not (repeat == 1 and record.get("repeat_index") is None))
            ):
                raise ValueError("Duplicate slot, wrong group or wrong repeat")
            for key, expected in (("agent_name", harness), ("provider", provider)):
                if record.get(key) is not None and record[key] != expected:
                    raise ValueError(f"Record {key} differs from source identity")
            identities.add(identity)
            embedded = record.get("trial_result") or record.get("raw", {}).get(
                "harbor_trial_result", {}
            )
            path, trial = representative(record, indexed)
            if not trial.get("finished_at"):
                raise ValueError("Source representative is not terminal")
            if "AgentTimeoutError" not in (
                record.get("execution_error_kind"),
                (embedded.get("exception_info") or {}).get("exception_type"),
            ):
                continue
            if (trial.get("exception_info") or {}).get("exception_type") != "AgentTimeoutError":
                continue
            task = task_directory(snapshot, trial)
            evidence = timeout_evidence(trial, task, source_timeout_sec=policy.source_timeout_sec)
            if evidence is None:
                continue
            key = object_digest([run, *identity, repeat - 1])
            slots.append(
                {
                    "slot_id": key,
                    "run": run,
                    "harness": harness,
                    "provider": provider,
                    "task_name": record["task_name"],
                    "group_id": "skills_off",
                    "repeat_index": repeat - 1,
                    "source_trial_id": trial["id"],
                    "source_trial_path": str(path),
                    "source_trial_sha256": digest(path),
                    "source_task": str(task),
                    "source_task_files": files(task),
                    "evidence": evidence,
                }
            )
        slot_path = snapshot / "slots.jsonl"
        if slot_path.is_file():
            declared = [json.loads(line) for line in slot_path.read_text().splitlines()
                        if line.strip()]
            matrix = {(s["group_id"], s["task_name"], s.get("repeat_index")) for s in declared}
            actual = {(row["group_id"], row["task_name"], row.get("repeat_index"))
                      for row in envelope["results"]}
            if len(matrix) != len(declared) or matrix != actual:
                raise ValueError("Source results do not cover the frozen slot matrix")
        sources.append(
            {
                "run": run,
                "snapshot": str(snapshot),
                "source_run_id": envelope.get("source_run_id") or envelope["run_id"],
                "results_sha256": digest(snapshot / "results.json"),
                "slots": len(identities),
                "repeat_index": repeat - 1,
                "benchmark_identity": benchmark,
                "protocol_sha256": digest(protocol_path) if protocol else None,
                "slots_sha256": digest(slot_path) if slot_path.is_file() else None,
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


def target_job(slot: dict, root: Path, lock, *, policy: TimeoutPolicy | None = None) -> dict:
    policy = policy or TimeoutPolicy()
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
        override_timeout_sec=policy.agent_timeout_sec,
        max_timeout_sec=policy.agent_timeout_sec,
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
        kwargs["timeout"] = policy.agent_timeout_sec
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
        n_concurrent_trials=policy.concurrency,
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
    repeat: int = 1,
    source_timeout_sec: int = 7200,
    agent_timeout_sec: int = 43200,
    concurrency: int = 2,
) -> dict:
    policy = TimeoutPolicy(
        repeat=repeat, source_timeout_sec=source_timeout_sec,
        agent_timeout_sec=agent_timeout_sec, concurrency=concurrency,
    )
    output = output.resolve()
    sources, slots = inventory(snapshots, policy=policy)
    from harbor_agent_infra.timeout_rerun.dispositions import freeze_dispositions

    dispositions = freeze_dispositions(baseline_dispositions, sources, slots)
    if output.exists() or any(
        output.is_relative_to(Path(s["snapshot"])) or Path(s["snapshot"]).is_relative_to(output)
        for s in sources
    ):
        raise ValueError("Campaign output must be new and separate from source snapshots")
    lock = load_runtime_lock(runtime_lock)
    targets = {s["slot_id"]: target_job(s, output, lock, policy=policy) for s in slots}
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
            text = set_toml(text, "agent", "timeout_sec", policy.agent_timeout_sec)
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
            "policy": policy.model_dump(),
            "benchmark_identity": sources[0]["benchmark_identity"],
            "runtime_lock_sha256": digest(stage / "runtime-lock.json"),
            "sources": sources,
            "slots": slots,
            "total_slots": sum(s["slots"] for s in sources),
            "candidate_slots": len(slots),
            "initial_trial_hours": len(slots) * policy.agent_timeout_sec / 3600,
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
                        str(policy.agent_timeout_sec),
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
        plan.get("schema_version") not in {SCHEMA, LEGACY_SCHEMA}
        or checksum != object_digest(plan)
    ):
        raise ValueError("Frozen timeout plan identity or policy changed")
    policy = TimeoutPolicy.model_validate(plan.get("policy"))
    if plan["policy"] != policy.model_dump():
        raise ValueError("Frozen timeout policy must declare every field")
    if plan["schema_version"] == LEGACY_SCHEMA and plan["policy"] != LEGACY_POLICY:
        raise ValueError("Frozen legacy timeout plan identity or policy changed")
    if plan["schema_version"] == SCHEMA:
        sources = plan.get("sources", [])
        runs = {source["run"] for source in sources}
        if (not sources or len(runs) != len(sources)
                or any(source.get("repeat_index") != policy.repeat - 1
                       or source.get("benchmark_identity") != plan.get("benchmark_identity")
                       for source in sources)
                or any(slot["run"] not in runs or slot["repeat_index"] != policy.repeat - 1
                       or slot["group_id"] != policy.group for slot in plan["slots"])):
            raise ValueError("Frozen source/slot identity differs from campaign policy")
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
        if source.get("protocol_sha256") and digest(
            Path(source["snapshot"]) / "protocol.json"
        ) != source["protocol_sha256"]:
            raise ValueError("Source protocol changed after planning")
        if source.get("slots_sha256") and digest(
            Path(source["snapshot"]) / "slots.jsonl"
        ) != source["slots_sha256"]:
            raise ValueError("Source slot matrix changed after planning")
    for slot in plan["slots"]:
        if digest(Path(slot["source_trial_path"])) != slot["source_trial_sha256"]:
            raise ValueError("Source Trial changed after planning")
        if files(Path(slot["source_task"])) != slot["source_task_files"]:
            raise ValueError("Source task changed after planning")
        if files(root / "inputs" / slot["slot_id"]) != slot["input_files"]:
            raise ValueError("Frozen execution inputs changed")
    from harbor_agent_infra.timeout_rerun.parallel import parallel_amendment

    parallel_amendment(plan)
    return plan
