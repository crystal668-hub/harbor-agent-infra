"""Validate frozen accepted selections and average metrics by task, then track."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from math import isfinite
from pathlib import Path
from statistics import fmean

from harbor_agent_infra.timeout_rerun.dispositions import scoring_records

METRICS = ("score", "tokens", "agent_seconds")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def agent_seconds(trial: dict) -> tuple[float | None, str | None]:
    """Use the native Agent phase only; never substitute Trial lifecycle time."""
    phase = trial.get("agent_execution") or {}
    start, end = phase.get("started_at"), phase.get("finished_at")
    if not start or not end:
        return None, "missing_agent_clock"
    try:
        seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None, "invalid_agent_clock"
    if not isfinite(seconds) or seconds < 0:
        return None, "invalid_agent_clock"
    return seconds, None


def tokens(trial: dict) -> tuple[int | None, str | None]:
    usage = trial.get("agent_result") or {}
    values = [usage.get(k) for k in ("n_input_tokens", "n_output_tokens")]
    if any(v is None for v in values):
        return None, "missing_token_usage"
    if any(type(v) is not int or v < 0 for v in values):
        return None, "invalid_token_usage"
    # Input already includes cache reads. Cache/reasoning must not be added again.
    return sum(values), None


def average_tasks(observations: list[dict], repeats: list[int]) -> list[dict]:
    grouped = defaultdict(list)
    for row in observations:
        grouped[tuple(row[k] for k in ("harness", "model", "track", "task_id"))].append(row)
    result = []
    for key, rows in sorted(grouped.items()):
        if sorted(r["repeat"] for r in rows) != sorted(repeats):
            raise ValueError(f"Missing or duplicate repeat for task: {key}")
        item = dict(zip(("harness", "model", "track", "task_id"), key, strict=True))
        for metric in METRICS:
            known = [r[metric] for r in rows if r[metric] is not None]
            item[metric] = fmean(known) if known else None
            item[metric + "_n"] = len(known)
        result.append(item)
    return result


def summarize(tasks: list[dict], observations: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in tasks:
        grouped[tuple(row[k] for k in ("harness", "model", "track"))].append(row)
    result = []
    for key, rows in sorted(grouped.items()):
        item = dict(zip(("harness", "model", "track"), key, strict=True))
        item["tasks"] = len(rows)
        for metric in METRICS:
            known = [r[metric] for r in rows if r[metric] is not None]
            item[metric] = fmean(known) if known else None
            item[metric + "_tasks"] = len(known)
            item[metric + "_observations"] = sum(r[metric + "_n"] for r in rows)
            item[metric + "_repeat_coverage"] = dict(sorted(Counter(
                r[metric + "_n"] for r in rows
            ).items()))
        item["repeat_scores"] = {
            repeat: fmean(r["score"] for r in observations if
                          (r["harness"], r["model"], r["track"]) == key
                          and r["repeat"] == repeat)
            for repeat in sorted({r["repeat"] for r in observations})
        }
        result.append(item)
    return result


def collect(manifest: dict, workspace: Path) -> tuple[list[dict], dict]:
    """The manifest pins reviewed sources; this is not a new experiment acceptance."""
    def bound(spec: dict) -> Path:
        path = workspace / spec["path"]
        if digest(path) != spec["sha256"]:
            raise ValueError(f"Changed frozen input: {path}")
        return path

    if manifest["schema_version"] != "result-pipeline-input.v1":
        raise ValueError("Unknown pipeline input schema")
    if manifest["view"] != "baseline-2h" or manifest["agent_budget_seconds"] != 7200:
        raise ValueError("This pipeline requires the accepted baseline-2h view")
    acceptance = manifest["acceptance"]
    if acceptance["status"] != "accepted" or not acceptance["evidence"]:
        raise ValueError("Reviewed acceptance evidence is required")
    for evidence in acceptance["evidence"]:
        bound(evidence)
    inventory = read(bound(manifest["inventory"]))
    lock = read(bound(manifest["runtime_lock"]))
    if (manifest["inventory"]["sha256"] != lock["vgb"]["task_inventory_sha256"]
            or inventory["package_version"] != manifest["benchmark_version"]):
        raise ValueError("Task inventory differs from locked benchmark")
    expected_tasks = {
        (track, task)
        for track in manifest["tracks"]
        for task in inventory["tracks"][track]["task_ids"]
    }
    combinations = {(c["harness"], c["model"]) for c in manifest["combinations"]}
    if len(combinations) != len(manifest["combinations"]):
        raise ValueError("Duplicate combination")
    repeats = [r["repeat"] for r in manifest["repeats"]]
    if len(set(repeats)) != len(repeats) or not repeats:
        raise ValueError("Duplicate or empty repeat selection")
    mappings = [(Path(old), Path(new)) for old, new in manifest.get("path_mappings", [])]

    def relocate(path: str) -> Path:
        original = Path(path)
        for old, new in mappings:
            if original.is_relative_to(old):
                return workspace / new / original.relative_to(old)
        return workspace / original

    observations, seen_trials, checks, sources = [], set(), [], []
    for repeat in manifest["repeats"]:
        number = repeat["repeat"]
        selection_path = bound(repeat["selection"])
        selection = read(selection_path)
        if selection["view"] != f"repeat{number}-2h":
            raise ValueError("Wrong repeat/view in selection")
        selected = [relocate(p).resolve() for p in selection["snapshots"]]
        pinned = [(workspace / s["path"]).resolve().parent for s in repeat["sources"]]
        if (len(set(selected)) != len(selected) or len(set(pinned)) != len(pinned)
                or set(selected) != set(pinned)):
            raise ValueError("Pinned sources differ from selected snapshots")
        seen_combinations = set()
        begin = len(observations)
        for source in repeat["sources"]:
            path = bound(source)
            payload = read(path)
            identity = payload["benchmark_identity"]
            if (identity["version"] != manifest["benchmark_version"]
                    or identity["subset"] != "property-calculation"
                    or identity["view"] not in ("native", "baseline-2h")):
                raise ValueError(f"Wrong benchmark/view: {path}")
            rows = scoring_records(payload)
            task_set, combination = set(), None
            for row in rows:
                track, task = row["task_name"].split("__", 1)
                trial = row["trial_result"]
                final = row.get("final_attempt") or {}
                trial_id = trial["id"]
                current = (row["agent_name"], trial["agent_info"]["model_info"]["name"])
                if (row["group_id"] != "skills_off" or row.get("skills_enabled") is True
                        or row.get("repeat_index") not in (None, number - 1)
                        or row.get("task_id", task) != task
                        or current not in combinations
                        or (combination is not None and combination != current)):
                    raise ValueError(f"Conflicting slot identity: {path}: {task}")
                combination = current
                if ((track, task) in task_set or trial_id in seen_trials
                        or final.get("trial_id", trial_id) != trial_id):
                    raise ValueError(f"Duplicate slot/Trial or conflicting final attempt: {task}")
                if not trial_id or not trial.get("finished_at"):
                    raise ValueError(f"Nonterminal Trial: {trial_id}")
                task_set.add((track, task))
                seen_trials.add(trial_id)
                score = ((row.get("vgb_domain_result") or {}).get("scores") or {}).get("score")
                if (row.get("scored") is not True or type(score) not in (int, float)
                        or not isfinite(score) or not 0 <= score <= 1):
                    raise ValueError(f"Missing/invalid accepted score: {trial_id}")
                seconds, timing_reason = agent_seconds(trial)
                count, token_reason = tokens(trial)
                observations.append({
                    "repeat": number, "harness": current[0], "model": current[1],
                    "track": track, "task_id": task, "trial_id": trial_id,
                    "score": score, "tokens": count, "agent_seconds": seconds,
                    "tokens_missing_reason": token_reason,
                    "agent_seconds_missing_reason": timing_reason,
                    "scoring_source": row["vgb_domain_result"].get("scoring_source", "vgb"),
                    "snapshot": str(path.parent),
                    "execution_version": (row.get("benchmark_migration") or {}).get(
                        "execution_version", manifest["benchmark_version"]),
                })
            if task_set != expected_tasks or combination in seen_combinations:
                raise ValueError(f"Incomplete task coverage or duplicate combination: {path}")
            seen_combinations.add(combination)
            sources.append({"repeat": number, **source})
        if seen_combinations != combinations:
            raise ValueError(f"Incomplete combinations for repeat {number}")
        current_rows = observations[begin:]
        checks.append({
            "repeat": number, "combinations": len(seen_combinations),
            "accepted_slots": len(current_rows),
            "expected_slots": len(expected_tasks) * len(combinations),
            "score_observations": len(current_rows),
            "token_observations": sum(r["tokens"] is not None for r in current_rows),
            "agent_time_observations": sum(r["agent_seconds"] is not None for r in current_rows),
        })
    return observations, {"repeats": checks, "sources": sources}


def markdown(summary: list[dict], checks: dict, manifest: dict) -> str:
    lines = [
        "# Property Calculation：2h 正式轮最终结果", "",
        f"日期：{manifest['report_date']}（Asia/Shanghai）  ",
        "类型：analysis  ",
        "状态：已验收代表的离线统计完成；12h 补跑视图未纳入。", "",
        "每个 repeat 覆盖：" + "；".join(
            f"Repeat{r['repeat']} {r['accepted_slots']}/{r['expected_slots']} slots，"
            f"{r['combinations']} 组合" for r in checks["repeats"]
        ) + "。", "",
        "先对同一 harness × model × task 的三次 repeat 取算术平均，再对 track 内任务等权平均。"
        "得分为 VGB 分数 × 100；已批准协议零分与能力零分均保留。"
        "Token = 原生 input + output（含已记录缓存输入，不再叠加 cache 或 reasoning）。"
        "时间 = agent_execution.finished_at − started_at，单位分钟，"
        "排除环境准备、Verifier及离线等待。",
        "Token/时间独立忽略缺失或无效的那次观测；每题有效次数写入 task-means.csv。"
        "表中括号是有效观测数/该 track 的三次预期观测数；每题仍等权，不按有效次数加权。"
        "如某题所有 repeat 均缺失，该题均值为空，track 均值只覆盖已知题，并单列覆盖。", "",
    ]
    keyed = {(r["harness"], r["model"], r["track"]): r for r in summary}
    repeats = len(manifest["repeats"])
    for metric, title, scale, digits in (
        ("score", "得分（0–100）", 100, 4),
        ("tokens", "Token（input + output / task）", 1, 2),
        ("agent_seconds", "Agent 执行时间（分钟 / task）", 1 / 60, 4),
    ):
        lines.extend([f"## {title}", "", "| Harness | Model | Advanced（19题） | Basic（51题） |",
                      "| --- | --- | ---: | ---: |"])
        for c in manifest["combinations"]:
            cells = []
            for track in manifest["tracks"]:
                row = keyed[c["harness"], c["model"], track]
                value = row[metric]
                cell = "—" if value is None else f"{value * scale:,.{digits}f}"
                cell += f"（{row[metric + '_observations']}/{row['tasks'] * repeats}）"
                if row[metric + "_tasks"] != row["tasks"]:
                    cell += f"；题目覆盖 {row[metric + '_tasks']}/{row['tasks']}"
                cells.append(cell)
            lines.append(f"| {c['harness']} | {c['model']} | {' | '.join(cells)} |")
        lines.append("")
    lines.extend(["## 覆盖与边界", ""])
    for r in checks["repeats"]:
        lines.append(f"- Repeat{r['repeat']}：得分 {r['score_observations']}/"
                     f"{r['expected_slots']}；token {r['token_observations']}/"
                     f"{r['expected_slots']}；Agent 时间 {r['agent_time_observations']}/"
                     f"{r['expected_slots']}。")
    for note in manifest.get("notes", []):
        lines.extend(["", note])
    lines.extend(["", "## 可重建产物", "",
                  "- [逐 Trial 观测](observations.csv)及[缺失项](missing.csv)。",
                  "- [逐任务跨 repeat 均值与有效次数](task-means.csv)。",
                  "- [分轨汇总](summary.json)、[覆盖与冻结来源](validation.json)。",
                  "- [冻结输入清单](input-manifest.json)；每个来源按 SHA256 校验。", ""])
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(manifest_path: Path, workspace: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    observations, checks = collect(manifest, workspace)
    tasks = average_tasks(observations, [r["repeat"] for r in manifest["repeats"]])
    summary = summarize(tasks, observations)
    checks["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    checks["implementation_sha256"] = digest(Path(__file__))
    checks["unique_tasks_across_repeats"] = len(tasks)
    output.mkdir(parents=True)
    (output / "input-manifest.json").write_bytes(manifest_bytes)
    for name, value in (("validation.json", checks), ("summary.json", summary)):
        (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    write_csv(output / "observations.csv", observations, list(observations[0]))
    write_csv(output / "task-means.csv", tasks, list(tasks[0]))
    write_csv(output / "missing.csv", [r for r in observations if
              r["tokens"] is None or r["agent_seconds"] is None], list(observations[0]))
    (output / "REPORT.md").write_text(markdown(summary, checks, manifest), encoding="utf-8")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="hash-bound accepted selection manifest")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True, help="new local artifact directory")
    args = parser.parse_args()
    checks = run(args.manifest.resolve(), args.workspace.resolve(), args.output.resolve())
    print(json.dumps(checks["repeats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
