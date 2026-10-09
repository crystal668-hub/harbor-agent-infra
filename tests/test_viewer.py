from pathlib import Path

from fastapi.testclient import TestClient

from harbor_agent_infra.viewer import create_multi_run_viewer, discover_artifact_runs


def _make_run(root: Path, name: str, jobs: tuple[str, ...] = ()) -> Path:
    jobs_dir = root / name / "jobs"
    jobs_dir.mkdir(parents=True)
    for job_name in jobs:
        job_dir = jobs_dir / job_name
        job_dir.mkdir()
        (job_dir / "config.json").write_text("{}", encoding="utf-8")
    return jobs_dir


def test_discover_artifact_runs_lists_only_direct_runs_with_jobs(tmp_path) -> None:
    _make_run(tmp_path, "alpha", ("one", "two"))
    (tmp_path / "notes").mkdir()
    _make_run(tmp_path / "nested", "ignored", ("three",))

    runs = discover_artifact_runs(tmp_path)

    assert [(run.name, run.job_count) for run in runs] == [("alpha", 2)]


def test_index_lists_runs_and_escapes_names(tmp_path) -> None:
    _make_run(tmp_path, "alpha & beta", ("one",))
    client = TestClient(create_multi_run_viewer(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "alpha &amp; beta" in response.text
    assert "1 job" in response.text
    assert '/?run=alpha+%26+beta' in response.text


def test_selecting_run_serves_official_viewer_and_dispatches_api(tmp_path) -> None:
    jobs_dir = _make_run(tmp_path, "alpha")
    other_jobs_dir = _make_run(tmp_path, "beta")
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("official viewer", encoding="utf-8")
    client = TestClient(create_multi_run_viewer(tmp_path, static_dir=static_dir))

    selected = client.get("/?run=alpha")
    config = client.get("/api/config")

    assert selected.status_code == 200
    assert selected.text == "official viewer"
    assert client.cookies["hai_view_run"] == "alpha"
    assert config.status_code == 200
    assert config.json()["folder"] == str(jobs_dir)
    assert config.json()["mode"] == "jobs"

    client.get("/?run=beta")
    assert client.get("/api/config").json()["folder"] == str(other_jobs_dir)


def test_unknown_or_unselected_run_cannot_reach_viewer(tmp_path) -> None:
    _make_run(tmp_path, "alpha")
    client = TestClient(create_multi_run_viewer(tmp_path))

    assert client.get("/?run=../alpha").status_code == 404
    response = client.get("/api/config")
    assert response.status_code == 409
    assert response.json() == {"detail": "Select a run-artifacts directory first."}


def test_api_remains_available_when_official_static_files_are_missing(tmp_path) -> None:
    jobs_dir = _make_run(tmp_path, "alpha")
    client = TestClient(create_multi_run_viewer(tmp_path))

    selected = client.get("/?run=alpha")

    assert selected.status_code == 503
    assert client.get("/api/config").json()["folder"] == str(jobs_dir)
