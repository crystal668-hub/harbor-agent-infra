"""Publish task-set projections without rewriting execution or scoring evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from harbor_agent_infra.formal import HARNESSES, PROVIDERS, aggregate_formal_snapshots
from harbor_agent_infra.recovery.native_snapshot import score_summary
from harbor_agent_infra.timeout_rerun.dispositions import scoring_records


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def project(
    payload: dict,
    *,
    mapping: dict,
    retired: set,
    target: dict,
    source: dict,
    version: str,
    view: str,
    scoring_rows: list | None = None,
) -> tuple[dict, list]:
    """Apply approved scoring decisions before changing public task identity."""
    rows = scoring_records(payload) if scoring_rows is None else scoring_rows
    kept, excluded, seen = [], [], set()
    for original, scored in zip(payload["results"], rows, strict=True):
        track, old = original["task_name"].split("__", 1)
        if original.get("task_id", old) != old:
            raise ValueError("Conflicting source task identity")
        if original.get("group_id") != "skills_off" or original.get("repeat_index") not in (
            None,
            0,
        ):
            raise ValueError("Migration requires skills_off repeat1")
        if old in retired:
            excluded.append(copy.deepcopy(original))
            continue
        new = mapping.get(old, old)
        identity = (track, new)
        if new not in target.get(track, []) or identity in seen:
            raise ValueError(f"Unknown task or mapping collision: {old} -> {new}")
        seen.add(identity)
        row = copy.deepcopy(scored)
        row.update(task_id=new, task_name=f"{track}__{new}", track=track)
        row["benchmark_migration"] = {
            "source_task_id": old,
            "target_task_id": new,
            "source_task_name": original["task_name"],
            "source_slot_id": original.get("slot_id"),
            "source_record_sha256": hashlib.sha256(
                json.dumps(original, sort_keys=True).encode()
            ).hexdigest(),
            "source_snapshot": source["snapshot"],
            "source_results_sha256": source["results_sha256"],
            "execution_version": "0.10.0",
            "scoring_version": "0.10.0",
            "target_version": version,
            "view": view,
            "rescored": False,
            "identity_only_projection": True,
        }
        kept.append(row)
    expected = {(track, task) for track, tasks in target.items() for task in tasks}
    if seen != expected:
        raise ValueError("Missing target task coverage")
    # Deliberately do not copy stale summaries/groups/override lookups into the new view.
    # The entire original payload is preserved separately, with its bound checksum.
    result = {
        "schema_version": payload.get("schema_version", 5),
        "run_id": source["run"],
        "source_run_id": source["run"],
        "source_execution_run_id": payload.get("run_id"),
        "records": len(kept),
        "results": kept,
        "summary": score_summary(kept),
        "benchmark_identity": {"version": version, "subset": "property-calculation", "view": view},
        "migration": {
            "source": source,
            "execution_version": "0.10.0",
            "rescored": False,
            "excluded_records": len(excluded),
        },
    }
    return result, excluded


def migrate(
    selection: Path,
    lock: Path,
    migration: Path,
    inventory: Path,
    output: Path,
    *,
    dry_run: bool = False,
) -> dict:
    selection, lock, migration, inventory, output = (
        p.resolve() for p in (selection, lock, migration, inventory, output)
    )
    config, locked, ids, inv = read(selection), read(lock)["vgb"], read(migration), read(inventory)
    if (
        digest(migration) != locked["task_id_migration_sha256"]
        or digest(inventory) != locked["task_inventory_sha256"]
        or inv["package_version"] != locked["version"]
    ):
        raise ValueError("Target release hashes or version mismatch")
    if config["view"] not in ("baseline-2h", "amended-12h"):
        raise ValueError("Unknown migration view")
    sources = config["sources"]
    expected = {f"{h}-{p}-repeat1" for h in HARNESSES for p in PROVIDERS}
    if len(sources) != 16 or {s["run"] for s in sources} != expected:
        raise ValueError("Expected exactly the 16 repeat1 combinations")
    targets = {
        t: inv["tracks"][t]["task_ids"]
        for t in ("property_calculation_advanced", "property_calculation_basic")
    }
    bound = {str(p): digest(p) for p in (selection, lock, migration, inventory)}
    for path, checksum in config.get("evidence", {}).items():
        if digest(Path(path)) != checksum:
            raise ValueError(f"Selection evidence changed: {path}")
        bound[path] = checksum
    baseline_plan = None
    if config["view"] == "baseline-2h":
        manifest = config.get("campaign_manifest")
        if not manifest or manifest not in bound:
            raise ValueError("Baseline requires a hash-bound campaign manifest")
        baseline_plan = read(Path(manifest))
        if any(s not in baseline_plan["sources"] for s in sources):
            raise ValueError("Baseline selection differs from frozen campaign sources")
    prepared = []
    for source in sources:
        path = Path(source["snapshot"]).resolve() / "results.json"
        if (
            output.is_relative_to(path.parent)
            or path.parent.is_relative_to(output)
            or any(p.is_relative_to(output) for p in (selection, lock, migration, inventory))
        ):
            raise ValueError("Output must be separate from inputs")
        if digest(path) != source["results_sha256"]:
            raise ValueError(f"Source hash changed: {path}")
        bound[str(path)] = source["results_sha256"]
        original = read(path)
        payload = copy.deepcopy(original)
        if source.get("baseline_score_dispositions"):
            if payload.get("baseline_score_dispositions"):
                raise ValueError("Duplicate scoring disposition sources")
            payload["baseline_score_dispositions"] = source["baseline_score_dispositions"]
        baseline_rows = None
        if baseline_plan is not None:
            from harbor_agent_infra.timeout_rerun.merge import before_rows

            baseline_rows = before_rows(baseline_plan, source)
        result, excluded = project(
            payload,
            mapping=ids["id_mapping"],
            retired=set(ids["retired_task_ids"]),
            target=targets,
            source=source,
            version=locked["version"],
            view=config["view"],
            scoring_rows=baseline_rows,
        )
        prepared.append((source, original, result, excluded))
    fingerprint = hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()
    receipt_path = output / "migration-receipt.json"
    if output.exists():
        receipt = read(receipt_path) if receipt_path.is_file() else {}
        if (
            receipt.get("input_fingerprint") != fingerprint
            or not receipt.get("outputs")
            or any(
                not (output / p).is_file() or digest(output / p) != h
                for p, h in receipt.get("outputs", {}).items()
            )
        ):
            raise ValueError("Output exists with different or incomplete content")
        return {**receipt, "already_published": True}
    report = {
        "view": config["view"],
        "input_fingerprint": fingerprint,
        "inputs": bound,
        "runs": len(prepared),
        "source_records": sum(len(x[1]["results"]) for x in prepared),
        "target_records": sum(len(x[2]["results"]) for x in prepared),
        "excluded_records": sum(len(x[3]) for x in prepared),
        "rescored": False,
    }
    if dry_run:
        return {**report, "dry_run": True}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".migration-", dir=output.parent))
    try:
        snapshots = []
        for source, original, result, excluded in prepared:
            run = source["run"]
            write(stage / run / "results.json", result)
            write(stage / run / "source-results.json", original)
            write(stage / run / "excluded-results.json", excluded)
            snapshots.append(stage / run)
        summary = aggregate_formal_snapshots(snapshots, top_n=10)
        # References must point to the published paths, never temporary staging directories.
        summary = json.loads(json.dumps(summary).replace(str(stage), str(output)))
        write(stage / "summary.json", summary)
        write(
            stage / "formal-selected-snapshots.json",
            {
                "schema_version": "formal-snapshot-selection.v1",
                "benchmark_identity": prepared[0][2]["benchmark_identity"],
                "snapshots": [str(output / s["run"]) for s in sources],
            },
        )
        ranks = []
        for source, _, result, _ in prepared:
            stats = result["summary"]
            ranks.append({"run": source["run"], **stats})
        ranks.sort(key=lambda r: (-(r["mean_vgb_score"] or 0), r["run"]))
        write(stage / "rankings.json", ranks)
        failures = Counter(
            str(r.get("execution_error_kind") or r.get("failure_mode") or "none")
            for _, _, p, _ in prepared
            for r in p["results"]
        )
        write(stage / "failure-counts.json", dict(failures))
        write(
            stage / "historical-usage.json",
            {
                "scope": "Original historical evidence, includes retired tasks; not RC execution",
                "evidence": config.get("evidence", {}),
                "usage": config.get("historical_usage", {}),
                "selected_source_timing": {
                    s["run"]: score_summary(
                        scoring_records(
                            {
                                **o,
                                "baseline_score_dispositions": s.get(
                                    "baseline_score_dispositions",
                                    o.get("baseline_score_dispositions", []),
                                ),
                            }
                        )
                    )["timing"]
                    for s, o, _, _ in prepared
                },
            },
        )
        lines = [
            "# Repeat1 RC task-set projection",
            "",
            f"View: {config['view']}",
            "Execution/scoring: VGB 0.10.0; target task set: 1.0.0rc1; no rescoring.",
            "Original evidence and retired-task attempts remain preserved.",
            "",
            "| Run | Tasks | Scored | Mean | Errors |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        lines.extend(
            f"| {r['run']} | {r['records']} | {r['scored']} | "
            f"{r['mean_vgb_score']:.6f} | {r['errors']} |"
            for r in ranks
        )
        lines += [
            "",
            "summary.json: retained-task statistics, distributions and Top/Bottom.",
            "historical-usage.json: source timing and all-attempt usage evidence; "
            "do not interpret it as retained-task cost.",
        ]
        (stage / "REPORT.md").write_text("\n".join(lines) + "\n")
        for p, h in bound.items():
            if digest(Path(p)) != h:
                raise ValueError("Input changed during publication")
        report["outputs"] = {
            str(p.relative_to(stage)): digest(p) for p in stage.rglob("*") if p.is_file()
        }
        write(stage / "migration-receipt.json", report)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("selection", "lock", "migration", "inventory", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = migrate(
        args.selection, args.lock, args.migration, args.inventory, args.output, dry_run=args.dry_run
    )
    print(json.dumps({k: v for k, v in report.items() if k not in ("inputs", "outputs")}, indent=2))


if __name__ == "__main__":
    main()
