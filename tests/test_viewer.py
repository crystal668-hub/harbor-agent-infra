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
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert "alpha &amp; beta" in response.text
    assert "1 job" in response.text
    assert '/?run=alpha+%26+beta' in response.text


def test_selecting_run_serves_official_viewer_and_dispatches_api(tmp_path) -> None:
    jobs_dir = _make_run(tmp_path, "alpha")
    other_jobs_dir = _make_run(tmp_path, "beta")
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<html><head></head><body>official viewer</body></html>", encoding="utf-8"
    )
    client = TestClient(create_multi_run_viewer(tmp_path, static_dir=static_dir))

    selected = client.get("/?run=alpha")
    config = client.get("/api/config")

    assert selected.status_code == 200
    assert selected.headers["cache-control"] == "no-store, max-age=0"
    assert "official viewer" in selected.text
    assert "new MutationObserver(mountNav)" in selected.text
    assert "searchParams.set('hai_run', run)" in selected.text
    assert "All runs" in selected.text
    assert 'const run = "alpha"' in selected.text
    assert "window.fetch = (input, init)" in selected.text
    assert client.cookies["hai_view_run"] == "alpha"
    assert config.status_code == 200
    assert config.json()["folder"] == str(jobs_dir)
    assert config.json()["mode"] == "jobs"

    client.get("/?run=beta")
    assert client.get("/api/config").json()["folder"] == str(other_jobs_dir)


def test_run_query_routes_api_without_shared_cookie(tmp_path) -> None:
    alpha_jobs = _make_run(tmp_path, "alpha")
    beta_jobs = _make_run(tmp_path, "beta")
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<html><head></head><body>official viewer</body></html>", encoding="utf-8"
    )
    client = TestClient(create_multi_run_viewer(tmp_path, static_dir=static_dir))

    client.get("/?run=alpha")
    alpha = client.get("/api/config?hai_run=alpha")
    beta = client.get("/api/config?hai_run=beta")

    assert alpha.json()["folder"] == str(alpha_jobs)
    assert beta.json()["folder"] == str(beta_jobs)

    landing = client.get("/?hai_run=beta")
    assert 'const run = "beta"' in landing.text


def test_referer_routes_each_tab_independently_of_shared_cookie(tmp_path) -> None:
    alpha_jobs = _make_run(tmp_path, "alpha")
    beta_jobs = _make_run(tmp_path, "beta")
    client = TestClient(create_multi_run_viewer(tmp_path))

    client.get("/?run=alpha")
    client.get("/?run=beta")
    alpha = client.get(
        "/api/config", headers={"referer": "http://testserver/jobs/example?hai_run=alpha"}
    )
    beta = client.get(
        "/api/config", headers={"referer": "http://testserver/jobs/example?hai_run=beta"}
    )

    assert alpha.json()["folder"] == str(alpha_jobs)
    assert beta.json()["folder"] == str(beta_jobs)


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
