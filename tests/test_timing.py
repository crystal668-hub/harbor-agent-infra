from __future__ import annotations

import copy

import pytest

from harbor_agent_infra.timing import SlotTiming, slot_timing, summarize_slot_timing


def native(**overrides):
    return {
        "id": "selected",
        "started_at": "2026-10-23T00:00:00Z",
        "finished_at": "2026-10-23T00:01:00Z",
        **overrides,
    }


@pytest.mark.parametrize("embedded", [True, False])
def test_native_timing_precedes_cached_elapsed_and_ignores_attempts(embedded):
    record = {
        "elapsed_seconds": 999,
        "final_attempt": {"trial_id": "selected"},
        "attempts": [{"trial_id": "old", "elapsed_seconds": 3000}],
        "observability": {"totals": {"timing": {"elapsed_seconds": 999}}},
    }
    if embedded:
        record["trial_result"] = native()
        record["raw"] = {"harbor_trial_result": native(id="old")}
    else:
        record["raw"] = {"harbor_trial_result": native()}
    before = copy.deepcopy(record)
    assert slot_timing(record) == SlotTiming(60.0, "timed")
    assert record == before


@pytest.mark.parametrize(("start", "end", "seconds"), [
    ("2026-10-23T00:00:00Z", "2026-10-23T08:01:00+08:00", 60.0),
    ("2026-10-23T00:00:00", "2026-10-23T00:01:00", 60.0),
    ("2026-10-23T00:00:00.123456Z", "2026-10-23T00:00:01.123457Z", 1.000001),
    ("2026-10-23T00:00:00Z", "2026-10-23T00:00:00Z", 0.0),
])
def test_timezone_precision_and_zero_duration(start, end, seconds):
    result = slot_timing({"trial_result": native(started_at=start, finished_at=end)})
    assert result.status == "timed"
    assert result.seconds == seconds


@pytest.mark.parametrize("timestamps", [
    {"started_at": None},
    {"finished_at": None},
])
def test_missing_endpoint_does_not_fall_back_to_cached_elapsed(timestamps):
    record = {"trial_result": native(**timestamps), "elapsed_seconds": 60}
    assert slot_timing(record) == SlotTiming(None, "missing")


@pytest.mark.parametrize("timestamps", [
    {"started_at": "invalid"},
    {"finished_at": ""},
    {"started_at": True},
    {"finished_at": []},
    {"started_at": "2026-10-23T00:02:00Z"},
    {"finished_at": "2026-10-23T00:01:00"},
])
def test_invalid_native_timing_does_not_fall_back(timestamps):
    record = {"trial_result": native(**timestamps), "elapsed_seconds": 60}
    assert slot_timing(record) == SlotTiming(None, "invalid")


@pytest.mark.parametrize("embedded", [True, False])
def test_conflicting_representative_identity_is_invalid(embedded):
    record = {"final_attempt": {"trial_id": "other"}, "elapsed_seconds": 60}
    if embedded:
        record["trial_result"] = native()
    else:
        record["raw"] = {"harbor_trial_result": native()}
    assert slot_timing(record) == SlotTiming(None, "invalid")


@pytest.mark.parametrize("record", [
    {"trial_result": "invalid"},
    {"raw": "invalid"},
    {"trial_result": native(), "final_attempt": "invalid"},
])
def test_malformed_native_metadata_is_invalid(record):
    assert slot_timing(record) == SlotTiming(None, "invalid")


@pytest.mark.parametrize("metadata", [
    {}, {"trial_result": {}}, {"trial_result": None},
    {"trial_result": {"started_at": None, "finished_at": None}},
    {"raw": {"harbor_trial_result": {"id": "selected"}}},
])
def test_legacy_fallback_requires_absent_native_timestamps(metadata):
    assert slot_timing({**metadata, "elapsed_seconds": 12.5}) == SlotTiming(12.5, "timed")
    assert slot_timing(metadata) == SlotTiming(None, "missing")


@pytest.mark.parametrize("elapsed", [True, False, -1, "60", float("nan"),
                                     float("inf"), -float("inf"), {}, []])
def test_invalid_legacy_values_are_not_zero_filled(elapsed):
    assert slot_timing({"elapsed_seconds": elapsed}) == SlotTiming(None, "invalid")


def test_partial_coverage_keeps_known_subtotal_and_unknown_total():
    result = summarize_slot_timing([
        {"trial_result": native(), "scored": False, "run_lifecycle_status": "failed"},
        {"elapsed_seconds": 0, "scored": True, "vgb_domain_result": {"scores": {"score": 0}}},
        {}, {"elapsed_seconds": -1},
    ])
    assert result == {
        "method": "selected_slot_sum", "total_seconds": None, "known_seconds": 60.0,
        "selected_slots": 4, "timed_slots": 2, "missing_slots": 1, "invalid_slots": 1,
        "complete": False,
    }


def test_empty_and_all_unknown_are_distinct_from_measured_zero():
    empty = summarize_slot_timing([])
    assert empty == {
        "method": "selected_slot_sum", "total_seconds": None, "known_seconds": 0.0,
        "selected_slots": 0, "timed_slots": 0, "missing_slots": 0, "invalid_slots": 0,
        "complete": False,
    }
    unknown = summarize_slot_timing([{}, {"elapsed_seconds": -1}])
    assert unknown["total_seconds"] is None and unknown["known_seconds"] == 0
    assert unknown["timed_slots"] == 0 and unknown["selected_slots"] == 2
    zero = summarize_slot_timing([{"elapsed_seconds": 0}])
    assert zero["total_seconds"] == 0 and zero["complete"] is True


def test_overlapping_trials_are_added_without_concurrency_division():
    records = [{"trial_result": native(id=str(i))} for i in range(20)]
    result = summarize_slot_timing(records)
    assert result["total_seconds"] == 1200
    assert result["selected_slots"] == 20 and result["complete"] is True


def test_sum_does_not_lose_small_durations_or_round_early():
    result = summarize_slot_timing({"elapsed_seconds": value} for value in (1e16, 1, 1))
    assert result["total_seconds"] == 10000000000000002.0
