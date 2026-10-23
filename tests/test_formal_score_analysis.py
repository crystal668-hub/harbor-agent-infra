from __future__ import annotations

import json

import pytest

from harbor_agent_infra.cli import main
from harbor_agent_infra.formal import aggregate_formal_snapshots
from harbor_agent_infra.score_analysis import analyze_selected_scores


def record(task, score, *, scored=True, source=None):
    return {
        "group_id": "skills_off", "task_name": task, "repeat_index": 0,
        "scored": scored, "run_lifecycle_status": "completed",
        "vgb_domain_result": {"scores": {"score": score}, "scoring_source": source},
        "final_attempt": {"trial_id": task + "-selected"},
    }


def snapshot(path, run_id, records):
    path.mkdir()
    (path / "results.json").write_text(json.dumps({
        "run_id": path.name, "source_run_id": run_id, "results": records,
    }))
    return path


def test_analysis_preserves_selected_scores_provenance_and_input(tmp_path):
    rows = [record(f"basic__task-{i}", score)
            for i, score in enumerate((0, 0.2, 0.4, 0.6, 0.8, 1))]
    rows[0]["run_lifecycle_status"] = "failed"
    rows[0]["vgb_domain_result"]["scoring_source"] = "operator_capability_zero"
    rows[0]["attempts"] = [{"score": 1.0, "trial_id": "unselected"}]
    rows.append(record("basic__missing", None, scored=False))
    root = snapshot(tmp_path / "merged", "original", rows)
    before = (root / "results.json").read_bytes()
    baseline = aggregate_formal_snapshots([root])
    assert "score_analysis" not in baseline
    extended = aggregate_formal_snapshots([root], top_n=3)
    analysis = extended.pop("score_analysis")
    assert extended == baseline
    stats = analysis["run_track"]["original"]["basic"]
    assert [r["score"] for r in stats["top"]] == [1, 0.8, 0.6]
    assert [r["score"] for r in stats["bottom"]] == [0, 0.2, 0.4]
    assert [b["count"] for b in stats["bins"]] == [1, 1, 1, 1, 1]
    assert stats["perfect"] == 1
    assert stats["scored"] == 6 and stats["unscored"] == 1
    assert sum(b["count"] for b in stats["bins"]) + stats["perfect"] == 6
    zero = stats["bottom"][0]
    assert zero["source_run_id"] == "original"
    assert zero["trial_id"] == "basic__task-0-selected"
    assert zero["selected_snapshot"] == str(root.resolve())
    assert zero["scoring_source"] == "operator_capability_zero"
    assert (root / "results.json").read_bytes() == before


def test_ties_are_stable_and_tracks_runs_stay_separate(tmp_path):
    paths = [snapshot(tmp_path / run, run, [
        record("basic__b", 0.5), record("basic__a", 0.5),
        record("advanced__a", 1),
    ]) for run in ("run-b", "run-a")]
    first = aggregate_formal_snapshots(paths, score_bins=(0, 0.5, 1))["score_analysis"]
    second = aggregate_formal_snapshots(paths[::-1], score_bins=(0, 0.5, 1))["score_analysis"]
    assert first == second
    assert first["top_n"] == 10
    assert first["track"]["basic"]["scored"] == 4
    assert first["track"]["advanced"]["scored"] == 2
    basic = first["run_track"]["run-a"]["basic"]
    assert [r["task_name"] for r in basic["top"]] == ["basic__a", "basic__b"]
    assert basic["bins"][0]["count"] == 0 and basic["bins"][1]["count"] == 2


def test_unscored_and_invalid_scores_are_not_zero_filled():
    entries = [{"run_id": "run", "snapshot": "snapshot",
                "record": record(f"basic__{i}", score)}
               for i, score in enumerate((None, True, "0.5", float("nan"),
                                          float("inf"), -0.1, 1.1))]
    result = analyze_selected_scores(entries)["summary"]
    assert result["scored"] == 0 and result["invalid_scores"] == 7
    assert result["top"] == result["bottom"] == []
    assert result["perfect"] == sum(b["count"] for b in result["bins"]) == 0
    empty = analyze_selected_scores([])
    assert empty["track"] == empty["run_track"] == {}
    assert empty["summary"]["records"] == 0


def test_analysis_still_rejects_duplicate_views_and_slots(tmp_path):
    root = snapshot(tmp_path / "original", "run", [record("basic__a", 0)])
    merged = snapshot(tmp_path / "merged", "run", [record("basic__a", 1)])
    with pytest.raises(ValueError, match="exactly one snapshot"):
        aggregate_formal_snapshots([root, merged], top_n=1)
    duplicate = snapshot(tmp_path / "duplicate", "other", [
        record("basic__a", 0), record("basic__a", 1),
    ])
    with pytest.raises(ValueError, match="Duplicate formal slot"):
        aggregate_formal_snapshots([duplicate], top_n=1)


@pytest.mark.parametrize("args", [
    ["--top-n", "0"], ["--top-n", "-1"], ["--top-n", "1.5"],
    ["--score-bins", "0,0.5,0.5,1"], ["--score-bins", "0,0.8,0.2,1"],
    ["--score-bins", "0,nan,1"], ["--score-bins", "0,inf,1"],
    ["--score-bins", "0,0.5"], ["--score-bins", "0.1,1"],
    ["--score-bins", "0,,1"],
])
def test_cli_rejects_invalid_analysis_options_before_reading_files(args):
    with pytest.raises(SystemExit) as exc:
        main(["summary", "nonexistent", *args])
    assert exc.value.code == 2


def test_summary_cli_outputs_analysis_json(tmp_path, capsys):
    root = snapshot(tmp_path / "run", "run", [record("basic__a", 0.75)])
    assert main(["summary", str(root), "--top-n", "1",
                 "--score-bins", "0,0.5,1"]) == 0
    result = json.loads(capsys.readouterr().out)
    analysis = result["score_analysis"]
    assert analysis["top_n"] == 1 and analysis["bin_edges"] == [0, 0.5, 1]
    assert analysis["summary"]["top"][0]["score"] == 0.75
    assert analysis["summary"]["bins"][1]["count"] == 1


@pytest.mark.parametrize("top_n", [0, -1, True, 1.5])
def test_python_api_validates_ranking_limit(top_n):
    with pytest.raises(ValueError, match="positive integer"):
        aggregate_formal_snapshots([], top_n=top_n)
