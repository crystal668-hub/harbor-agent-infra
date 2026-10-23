"""Read-only score diagnostics for explicitly selected formal representatives."""

from collections import defaultdict

DEFAULT_SCORE_BINS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def validate_score_bins(edges: tuple[float, ...]) -> tuple[float, ...]:
    if (len(edges) < 2 or any(type(edge) not in (int, float) for edge in edges)
            or edges[0] != 0 or edges[-1] != 1
            or not all(left < right for left, right in zip(edges, edges[1:]))):
        raise ValueError("score bins must increase strictly from 0 to 1")
    return edges


def _summarize(entries: list[dict], top_n: int, edges: tuple[float, ...]) -> dict:
    scored = []
    unscored = invalid = 0
    for entry in entries:
        record = entry["record"]
        if not record.get("scored"):
            unscored += 1
            continue
        domain = record.get("vgb_domain_result") or {}
        score = (domain.get("scores") or {}).get("score")
        # Exclude booleans, missing values, NaN/infinity and out-of-contract scores.
        if type(score) not in (int, float) or not 0 <= score <= 1:
            invalid += 1
            continue
        final = record.get("final_attempt") or {}
        trial = record.get("trial_result") or {}
        scored.append({
            "source_run_id": entry["run_id"],
            "selected_snapshot": entry["snapshot"],
            "group_id": record["group_id"],
            "task_name": record["task_name"],
            "repeat_index": record.get("repeat_index"),
            "trial_id": final.get("trial_id") or trial.get("id"),
            "trial_result_path": (final.get("trial_result_path")
                                  or record.get("trial_result_path")),
            "score": score,
            "scoring_source": domain.get("scoring_source"),
        })

    def identity(row):
        return (row["source_run_id"], row["group_id"], row["task_name"],
                str(row["repeat_index"]))

    return {
        "records": len(entries),
        "scored": len(scored),
        "unscored": unscored,
        "invalid_scores": invalid,
        "top": sorted(scored, key=lambda row: (-row["score"], identity(row)))[:top_n],
        "bottom": sorted(scored, key=lambda row: (row["score"], identity(row)))[:top_n],
        "bins": [
            {"lower": lower, "upper": upper,
             "count": sum(lower <= row["score"] < upper for row in scored)}
            for lower, upper in zip(edges, edges[1:])
        ],
        "perfect": sum(row["score"] == 1 for row in scored),
    }


def analyze_selected_scores(
    entries: list[dict], *, top_n: int = 10, bin_edges: tuple[float, ...] = DEFAULT_SCORE_BINS,
) -> dict:
    """Keep ranking identities and score provenance without reselecting attempts."""
    if type(top_n) is not int or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    edges = validate_score_bins(bin_edges)
    tracks = defaultdict(list)
    run_tracks = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        track = entry["record"]["task_name"].split("__", 1)[0]
        tracks[track].append(entry)
        run_tracks[entry["run_id"]][track].append(entry)
    return {
        "top_n": top_n,
        "bin_edges": list(edges),
        "summary": _summarize(entries, top_n, edges),
        "track": {track: _summarize(rows, top_n, edges)
                  for track, rows in sorted(tracks.items())},
        "run_track": {
            run: {track: _summarize(rows, top_n, edges)
                  for track, rows in sorted(groups.items())}
            for run, groups in sorted(run_tracks.items())
        },
    }
