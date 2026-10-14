"""Tests for run artifact categorization in the Viewer."""

from __future__ import annotations

from pathlib import Path

import pytest

from harbor_agent_infra.viewer import ArtifactRun, discover_artifact_runs


@pytest.fixture
def artifacts_dir(tmp_path: Path) -> Path:
    """Create a test artifacts directory with categorized and legacy runs."""
    base = tmp_path / "run-artifacts"
    base.mkdir()

    # Create formal runs
    formal = base / "formal"
    formal.mkdir()
    (formal / "experiment-001" / "jobs" / "job-a").mkdir(parents=True)
    (formal / "experiment-001" / "jobs" / "job-a" / "config.json").touch()
    (formal / "experiment-002" / "jobs" / "job-b").mkdir(parents=True)
    (formal / "experiment-002" / "jobs" / "job-b" / "config.json").touch()
    (formal / "experiment-002" / "jobs" / "job-c").mkdir(parents=True)
    (formal / "experiment-002" / "jobs" / "job-c" / "config.json").touch()

    # Create temporary runs
    temporary = base / "temporary"
    temporary.mkdir()
    (temporary / "smoke-test-123" / "jobs" / "job-x").mkdir(parents=True)
    (temporary / "smoke-test-123" / "jobs" / "job-x" / "config.json").touch()
    (temporary / "debug-run" / "jobs").mkdir(parents=True)

    # Create legacy top-level run
    (base / "old-run" / "jobs" / "job-legacy").mkdir(parents=True)
    (base / "old-run" / "jobs" / "job-legacy" / "config.json").touch()

    # Create same name in different categories (should be distinct)
    (formal / "shared-name" / "jobs" / "job-1").mkdir(parents=True)
    (formal / "shared-name" / "jobs" / "job-1" / "config.json").touch()
    (temporary / "shared-name" / "jobs" / "job-2").mkdir(parents=True)
    (temporary / "shared-name" / "jobs" / "job-2" / "config.json").touch()

    return base


def test_discover_categorized_runs(artifacts_dir: Path) -> None:
    """Test that discover_artifact_runs finds all categorized and legacy runs."""
    runs = discover_artifact_runs(artifacts_dir)

    # Should find 7 total runs (2 formal + 2 temporary + 1 legacy + 2 shared-name)
    assert len(runs) == 7

    # Check formal runs
    formal_runs = [r for r in runs if r.category == "formal"]
    assert len(formal_runs) == 3
    formal_names = {r.name for r in formal_runs}
    assert formal_names == {"experiment-001", "experiment-002", "shared-name"}

    # Check temporary runs
    temporary_runs = [r for r in runs if r.category == "temporary"]
    assert len(temporary_runs) == 3
    temporary_names = {r.name for r in temporary_runs}
    assert temporary_names == {"smoke-test-123", "debug-run", "shared-name"}

    # Check legacy run
    legacy_runs = [r for r in runs if r.category is None]
    assert len(legacy_runs) == 1
    assert legacy_runs[0].name == "old-run"


def test_job_count_correct(artifacts_dir: Path) -> None:
    """Test that job counts are correctly computed for each run."""
    runs = discover_artifact_runs(artifacts_dir)

    run_by_name_category = {(r.name, r.category): r for r in runs}

    assert run_by_name_category[("experiment-001", "formal")].job_count == 1
    assert run_by_name_category[("experiment-002", "formal")].job_count == 2
    assert run_by_name_category[("smoke-test-123", "temporary")].job_count == 1
    assert run_by_name_category[("debug-run", "temporary")].job_count == 0
    assert run_by_name_category[("old-run", None)].job_count == 1


def test_same_name_different_category_distinct(artifacts_dir: Path) -> None:
    """Test that same name in different categories are distinct runs."""
    runs = discover_artifact_runs(artifacts_dir)

    shared_name_runs = [r for r in runs if r.name == "shared-name"]
    assert len(shared_name_runs) == 2

    categories = {r.category for r in shared_name_runs}
    assert categories == {"formal", "temporary"}

    # Verify they point to different directories
    formal_shared = next(r for r in shared_name_runs if r.category == "formal")
    temp_shared = next(r for r in shared_name_runs if r.category == "temporary")
    assert formal_shared.jobs_dir != temp_shared.jobs_dir


def test_empty_artifacts_dir(tmp_path: Path) -> None:
    """Test that empty artifacts directory returns no runs."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    runs = discover_artifact_runs(empty_dir)
    assert len(runs) == 0


def test_no_category_dirs(tmp_path: Path) -> None:
    """Test legacy-only layout without formal/temporary directories."""
    base = tmp_path / "legacy-only"
    base.mkdir()

    (base / "run-1" / "jobs" / "job-a").mkdir(parents=True)
    (base / "run-1" / "jobs" / "job-a" / "config.json").touch()
    (base / "run-2" / "jobs" / "job-b").mkdir(parents=True)
    (base / "run-2" / "jobs" / "job-b" / "config.json").touch()

    runs = discover_artifact_runs(base)
    assert len(runs) == 2
    assert all(r.category is None for r in runs)
    assert {r.name for r in runs} == {"run-1", "run-2"}


def test_skip_non_job_directories(tmp_path: Path) -> None:
    """Test that directories without jobs/ are skipped."""
    base = tmp_path / "mixed"
    base.mkdir()

    formal = base / "formal"
    formal.mkdir()

    # Valid run with jobs
    (formal / "valid-run" / "jobs" / "job-1").mkdir(parents=True)
    (formal / "valid-run" / "jobs" / "job-1" / "config.json").touch()

    # Invalid: no jobs directory
    (formal / "no-jobs-dir" / "other").mkdir(parents=True)

    # Valid but empty: jobs exists but has no jobs (still discovered, job_count=0)
    (formal / "empty-jobs" / "jobs").mkdir(parents=True)

    runs = discover_artifact_runs(base)
    assert len(runs) == 2  # Both valid-run and empty-jobs

    run_by_name = {r.name: r for r in runs}
    assert run_by_name["valid-run"].job_count == 1
    assert run_by_name["empty-jobs"].job_count == 0
    assert "no-jobs-dir" not in run_by_name  # Skipped because no jobs/ dir


def test_cache_key_format(artifacts_dir: Path) -> None:
    """Test that _cache_key generates correct format for categorized vs legacy."""
    from harbor_agent_infra.viewer import _RunDispatcher

    dispatcher = _RunDispatcher(artifacts_dir, static_dir=None)

    formal_run = ArtifactRun(
        name="test", jobs_dir=Path("/fake"), job_count=1, modified_at=0.0, category="formal"
    )
    temp_run = ArtifactRun(
        name="test", jobs_dir=Path("/fake"), job_count=1, modified_at=0.0, category="temporary"
    )
    legacy_run = ArtifactRun(
        name="test", jobs_dir=Path("/fake"), job_count=1, modified_at=0.0, category=None
    )

    assert dispatcher._cache_key(formal_run) == "formal/test"
    assert dispatcher._cache_key(temp_run) == "temporary/test"
    assert dispatcher._cache_key(legacy_run) == "test"


def test_find_run_prefers_categorized(artifacts_dir: Path) -> None:
    """Test that find_run prefers categorized runs over legacy when same name exists."""
    from harbor_agent_infra.viewer import _RunDispatcher

    # Create a run with same name in both formal and legacy
    (artifacts_dir / "formal" / "ambiguous" / "jobs" / "job-1").mkdir(parents=True)
    (artifacts_dir / "formal" / "ambiguous" / "jobs" / "job-1" / "config.json").touch()
    (artifacts_dir / "ambiguous" / "jobs" / "job-2").mkdir(parents=True)
    (artifacts_dir / "ambiguous" / "jobs" / "job-2" / "config.json").touch()

    dispatcher = _RunDispatcher(artifacts_dir, static_dir=None)
    found = dispatcher.find_run("ambiguous")

    assert found is not None
    assert found.category == "formal"  # Prefers categorized over legacy


def test_sorted_by_modified_time(tmp_path: Path) -> None:
    """Test that runs are sorted by modification time (newest first)."""
    import time

    base = tmp_path / "sorted"
    formal = base / "formal"
    formal.mkdir(parents=True)

    # Create runs with different timestamps
    (formal / "old" / "jobs").mkdir(parents=True)
    time.sleep(0.01)
    (formal / "newer" / "jobs").mkdir(parents=True)
    time.sleep(0.01)
    (formal / "newest" / "jobs").mkdir(parents=True)

    runs = discover_artifact_runs(base)
    names = [r.name for r in runs]

    # Should be sorted newest first
    assert names[0] == "newest"
    assert names[-1] == "old"
