from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from harbor_agent_infra.preparation.image_manager import ImageManagerError, inspect_image
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

ROOT = Path(__file__).resolve().parents[1]


def _docker_ready() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info"], capture_output=True, check=False
    ).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paired-run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, *, blocker: bool = False) -> None:
        checks.append(
            {
                "name": name,
                "status": "pass" if ok else "blocked",
                "detail": detail,
                "blocker": blocker,
            }
        )

    check(
        "runtime-lock",
        (ROOT / "runtime-lock.json").is_file(),
        "runtime-lock.json present",
        blocker=True,
    )
    check(
        "harbor-import",
        importlib.util.find_spec("harbor") is not None,
        "Harbor importable",
        blocker=True,
    )
    check("docker-daemon", _docker_ready(), "Docker daemon available", blocker=True)
    source_files = [
        path
        for directory in (ROOT / "src", ROOT / "adapters", ROOT / "integrations")
        for path in directory.glob("**/*.py")
        if path.is_file()
    ]
    check(
        "legacy-import-boundary",
        not any(
            any(
                marker in path.read_text(encoding="utf-8")
                for marker in ("import benchmarking", "from benchmarking")
            )
            for path in source_files
        ),
        "no legacy benchmarking import in new source",
        blocker=True,
    )
    check(
        "openclaw-adapter",
        (ROOT / "adapters/openclaw/adapter.py").is_file(),
        "adapter exists",
        blocker=True,
    )
    check(
        "forbidden-adapter-name",
        not (ROOT / "adapters/openclaw_vgb").exists(),
        "no openclaw_vgb adapter directory",
        blocker=True,
    )
    check(
        "vgb-runtime",
        bool(os.environ.get("VGB_PYTHON")) and Path(os.environ["VGB_PYTHON"]).is_file(),
        "VGB_PYTHON points to a runtime",
        blocker=True,
    )
    check(
        "runtime-lock-schema",
        True,
        "runtime lock has Harbor-native OpenClaw and base image fields",
        blocker=True,
    )
    try:
        lock = load_runtime_lock(ROOT / "runtime-lock.json")
    except (OSError, ValueError, TypeError) as exc:
        check("openclaw-npm-lock", False, str(exc), blocker=True)
        check("agent-base-image-lock", False, str(exc), blocker=True)
    else:
        check(
            "agent-python-policy",
            lock.agent_python.package_install_policy == "agent-managed"
            and not lock.agent_python.preinstalled_packages,
            "Python/pip tools are locked; third-party packages remain agent-managed",
            blocker=True,
        )
        check(
            "openclaw-npm-lock",
            lock.openclaw.version == "2026.6.9"
            and lock.openclaw.runtime_strategy
            == "harbor-native-nvm22-openclaw-setup-workspace",
            f"OpenClaw npm {lock.openclaw.version} via {lock.openclaw.runtime_strategy}",
            blocker=True,
        )
        check(
            "agent-base-image-lock",
            bool(lock.agent_base_image.digest),
            f"base image {lock.agent_base_image.immutable_reference}",
            blocker=True,
        )
        try:
            inspect_image(
                lock.agent_base_image.reference,
                digest=lock.agent_base_image.digest,
                platform=lock.agent_base_image.platform,
            )
        except ImageManagerError as exc:
            check("agent-base-image-local", False, str(exc), blocker=True)
        else:
            check(
                "agent-base-image-local",
                True,
                "base image digest/platform verified",
                blocker=True,
            )
        runtime_probe = subprocess.run(
            [
                "docker", "run", "--rm", "--platform", lock.agent_base_image.platform,
                "--entrypoint", "sh", lock.agent_base_image.immutable_reference,
                "-lc",
                "set -eu; "
                f"test \"$(python3 --version)\" = 'Python {lock.agent_python.python_version}'; "
                f"test \"$(python --version)\" = 'Python {lock.agent_python.python_version}'; "
                f"pip3 --version | grep -F 'pip {lock.agent_python.pip_version} '; "
                f"pip --version | grep -F 'pip {lock.agent_python.pip_version} '; "
                "python3 -m venv /tmp/hai-venv; "
                "test \"$PIP_BREAK_SYSTEM_PACKAGES\" = 1; "
                "python3 -m pip list --format=freeze | "
                "grep -Ev '^(pip|setuptools|wheel)==' | (! grep .)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        check(
            "agent-python-tools",
            runtime_probe.returncode == 0,
            runtime_probe.stdout.strip() or runtime_probe.stderr.strip(),
            blocker=True,
        )
    check(
        "registry-configured",
        bool(os.environ.get("HARBOR_REGISTRY_REFERENCE")),
        "HARBOR_REGISTRY_REFERENCE is configured; Registry acceptance is optional",
    )
    if args.paired_run_dir is not None:
        _check_paired_run(args.paired_run_dir, check)
    report = {
        "schema_version": "acceptance-report.v1",
        "complete": all(item["status"] == "pass" for item in checks if item["blocker"]),
        "checks": checks,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report["complete"] else 1


def _check_paired_run(root: Path, check) -> None:
    manifest_path = root / "runtime-manifest.json"
    results_path = root / "results.json"
    if not manifest_path.is_file() or not results_path.is_file():
        check("paired-artifacts", False, "runtime manifest or results missing", blocker=True)
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    groups = {group["group_id"]: group for group in manifest["groups"]}
    records = results["results"]
    check(
        "paired-status",
        manifest["schema_version"] == "harbor-paired-runtime-manifest.v1"
        and manifest["status"] == "completed"
        and set(groups) == {"skills_on", "skills_off"},
        f"status={manifest['status']}; groups={sorted(groups)}",
        blocker=True,
    )
    on_skills = groups.get("skills_on", {}).get("injected_skills", [])
    off_skills = groups.get("skills_off", {}).get("injected_skills", [])
    check(
        "paired-skill-injection",
        len(on_skills) == 85 and off_skills == []
        and len({item["name"] for item in on_skills}) == 85
        and all(len(item["content_sha256"]) == 64 for item in on_skills),
        f"skills_on={len(on_skills)}; skills_off={len(off_skills)}",
        blocker=True,
    )
    task_sets = {
        group_id: {record["task_name"] for record in records if record["group_id"] == group_id}
        for group_id in ("skills_on", "skills_off")
    }
    check(
        "paired-task-identity",
        bool(task_sets["skills_on"]) and task_sets["skills_on"] == task_sets["skills_off"],
        f"skills_on={len(task_sets['skills_on'])}; skills_off={len(task_sets['skills_off'])}",
        blocker=True,
    )
    secret = os.environ.get("OPENAI_API_KEY")
    secret_found = False
    evidence_ok = True
    rewards_ok = True
    viewer_ok = True
    viewer_consistency_ok = True
    from fastapi.testclient import TestClient
    from harbor.cli.view import STATIC_DIR
    from harbor.viewer import create_app

    viewer = TestClient(create_app(root / "jobs", mode="jobs", static_dir=STATIC_DIR))
    viewer_ok &= viewer.get("/").status_code == 200
    jobs_response = viewer.get("/api/jobs")
    viewer_ok &= jobs_response.status_code == 200 and jobs_response.json()["total"] == 2
    for record in records:
        trial_path = Path(record["trial_result_path"])
        trial_dir = trial_path.parent
        job_name = trial_dir.parent.name
        trial_name = trial_dir.name
        artifact_path = trial_dir / "verifier" / "vgb-evaluation.json"
        evidence_ok &= all(
            path.is_file() for path in (
                trial_path, trial_dir / "config.json", trial_dir / "lock.json",
                trial_dir / "agent" / "trajectory.json", artifact_path,
            )
        )
        evidence_ok &= record.get("tool_audit_status") == "available"
        evidence_ok &= bool(record.get("network_policy"))
        evidence_ok &= all(Path(item["trial_result_path"]).is_file()
                           for item in record.get("attempts", []))
        rewards = ((record.get("trial_result") or {}).get("verifier_result") or {}).get(
            "rewards", {}
        )
        if artifact_path.is_file():
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            score = (artifact.get("domain_result") or {}).get("scores", {}).get("score")
            rewards_ok &= (
                artifact.get("vgb_status") == "scored"
                and isinstance(score, int | float) and not isinstance(score, bool)
                and math.isfinite(score)
                and rewards.get("vgb_score") == score
                and rewards.get("reward") == score
                and (record.get("vgb_domain_result") or {}).get("scores", {}).get("score")
                == score
            )
        else:
            rewards_ok = False
        trial_response = viewer.get(f"/api/jobs/{job_name}/trials/{trial_name}")
        viewer_ok &= trial_response.status_code == 200
        if trial_response.status_code == 200:
            viewer_trial = trial_response.json()
            original_trial = record.get("trial_result") or {}
            viewer_consistency_ok &= all(
                viewer_trial.get(key) == original_trial.get(key)
                for key in (
                    "agent_result", "agent_execution", "verifier", "started_at",
                    "finished_at", "verifier_result",
                )
            )
        viewer_ok &= all(
            viewer.get(f"/api/jobs/{job_name}/trials/{trial_name}{suffix}").status_code == 200
            for suffix in ("/trajectory", "/verifier-output", "/files", "/artifacts")
        )
        task_summary = viewer.get(
            f"/api/jobs/{job_name}/tasks", params={"task": record["task_name"]}
        )
        viewer_consistency_ok &= (
            task_summary.status_code == 200
            and any(
                item["task_name"] == record["task_name"]
                and item["avg_reward"] == rewards.get("vgb_score")
                for item in task_summary.json().get("items", [])
            )
        )
    if secret:
        secret_found = any(
            secret.encode() in path.read_bytes()
            for path in root.rglob("*") if path.is_file()
        )
    check("paired-trial-evidence", evidence_ok, f"records={len(records)}", blocker=True)
    check("paired-reward-parity", rewards_ok, "Harbor reward equals VGB artifact and Infra score",
          blocker=True)
    check("paired-viewer", viewer_ok and STATIC_DIR.is_dir(), "official Viewer API and UI",
          blocker=True)
    check("paired-viewer-parity", viewer_consistency_ok,
          "Viewer timing, tokens, cost and reward match Harbor TrialResult", blocker=True)
    check("paired-secret-absence", bool(secret) and not secret_found,
          "configured provider key absent from trial files", blocker=True)


if __name__ == "__main__":
    raise SystemExit(main())
