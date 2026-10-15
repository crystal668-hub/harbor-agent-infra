"""Provider-free real Harbor offline setup gate for a candidate image."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from harbor import Job, JobConfig

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from scripts.build_preinstalled_image import require_idle_docker

NETWORK_PROBE = """
import json, socket
from pathlib import Path
interfaces = {p.name: (p / 'operstate').read_text().strip()
              for p in Path('/sys/class/net').iterdir() if (p / 'operstate').exists()}
assert not any(state == 'up' for name, state in interfaces.items() if name != 'lo'), interfaces
assert len(Path('/proc/net/route').read_text().splitlines()) == 1
try:
    socket.create_connection(('1.1.1.1', 443), timeout=2)
except OSError:
    pass
else:
    raise RuntimeError('offline setup has external network access')
Path('/logs/agent/network-check.json').write_text(json.dumps({
    'interfaces': interfaces, 'external_tcp': 'blocked', 'status': 'passed',
}))
"""


async def verify_image(name: str, lock_path: Path, output: Path, *, concurrent: int = 1) -> dict:
    import shlex

    require_idle_docker()
    if output.exists():
        raise ValueError("verification output must be a new directory")
    output.mkdir(parents=True)
    lock = load_runtime_lock(lock_path)
    image = lock.execution_image(name, "preinstalled")
    task = output / "task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text("Install only; no provider request.\n")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    healthcheck = "python3 -c " + shlex.quote(NETWORK_PROBE)
    # Test-only task networking blocks traffic before Harbor setup without
    # requiring Harbor's separate egress-proxy image to be downloaded.
    (task / "environment/docker-compose.yaml").write_text(
        "services:\n  main:\n    network_mode: none\n"
    )
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n'
        f'docker_image = {json.dumps(image.immutable_reference)}\n'
        '[environment.healthcheck]\n'
        f'command = {json.dumps(healthcheck)}\nretries = 1\n'
    )
    spec = AgentSpec(
        adapter=name, model="anthropic/claude-opus-5.5" if name == "openclaw" else "openai/fixture",
        installation_mode="preinstalled",
        **({"max_output_tokens": 64000} if name == "hermes" else {}),
    )
    agent = harness_runner_for(name).build_agent_config(spec, lock)
    config = JobConfig.model_validate({
        "job_name": name + "-preinstalled-offline", "jobs_dir": str(output / "jobs"),
        "install_only": True, "quiet": True, "n_attempts": 2,
        "n_concurrent_trials": concurrent, "retry": {"max_retries": 0},
        "environment": {"type": "docker", "delete": True, "override_cpus": 1,
                        "override_memory_mb": 2048, "cpu_enforcement_policy": "limit",
                        "memory_enforcement_policy": "limit"},
        "agents": [agent.model_dump(mode="json")], "tasks": [{"path": str(task)}],
    })
    result = await (await Job.create(config)).run()
    trials = result.trial_results
    setup_paths = sorted(output.glob("jobs/*/*/agent/harness-setup.json"))
    network_paths = sorted(output.glob("jobs/*/*/agent/network-check.json"))
    failures = [t.exception_info.model_dump(mode="json") for t in trials if t.exception_info]
    passed = (
        len(trials) == len(setup_paths) == len(network_paths) == 2 and not failures
        and all(json.loads(p.read_text())["status"] == "passed"
                for p in setup_paths + network_paths)
    )
    report = {"schema_version": "preinstalled-offline-gate.v1", "name": name,
              "image": image.immutable_reference, "concurrency": concurrent,
              "trials": len(trials), "failures": failures,
              "status": "passed" if passed else "failed",
              "setup_evidence": [str(p) for p in setup_paths],
              "network_evidence": [str(p) for p in network_paths]}
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not passed:
        raise RuntimeError(f"offline Harbor setup gate failed; inspect {output}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=("openclaw", "hermes", "codex", "claude-code"))
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--concurrent", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify_image(
        args.name, args.lock, args.output_dir.absolute(), concurrent=args.concurrent,
    )), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
