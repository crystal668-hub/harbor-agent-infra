"""Run a trial-scoped OpenClaw Gateway, retaining the parent through yielded turns."""

from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path

from adapters.openclaw.failure import OpenClawAgentIncompleteError

_SOURCE_DIR = Path(__file__).parent
_LOGS = "/logs/agent"
_NODE = ". ~/.nvm/nvm.sh && nvm use 22 >/dev/null && "


async def run_gateway(agent, instruction, environment) -> None:
    identity = agent.session_identity()
    env = identity.environment()
    if not agent.model_name or "/" not in agent.model_name:
        raise ValueError("Model name must be in the format provider/model_name")
    provider, _, _ = agent.model_name.partition("/")
    agent._validate_provider(provider)
    for key in agent._provider_env_keys(provider):
        if value := agent._get_env(key):
            env[key] = value
    env["OPENCLAW_CONFIG_PATH"] = str(identity.state_dir / "openclaw.json")
    config = agent._build_full_openclaw_config()
    config["gateway"] = {"mode": "local", "bind": "loopback", "auth": {"mode": "token"}}
    defaults = config["agents"]["defaults"]
    defaults["heartbeat"] = {"every": "0m"}
    config["discovery"] = {"mdns": {"mode": "off"}}
    config["update"] = {"checkOnStart": False}
    if agent.options.timeout is not None:
        defaults["timeoutSeconds"] = agent.options.timeout
    request = {
        "message": instruction,
        "agentId": identity.agent_id,
        "sessionKey": identity.session_key,
        "sessionId": identity.session_id,
        "idempotencyKey": identity.session_id,
        "deliver": False,
    }
    if agent.options.thinking is not None:
        request["thinking"] = agent.options.thinking
    if agent.options.timeout is not None:
        request["timeout"] = agent.options.timeout
    agent.logs_dir.mkdir(parents=True, exist_ok=True)
    (agent.logs_dir / "instruction.txt").write_text(instruction)
    for name, content in {
        "openclaw.upload.json": json.dumps(config),
        "openclaw-run.json": json.dumps(request),
        "gateway_driver.mjs": (_SOURCE_DIR / "gateway_driver.mjs").read_text(),
        "gateway_session.mjs": (_SOURCE_DIR / "gateway_session.mjs").read_text(),
    }.items():
        await agent._upload_config_text(
            environment, content=content, remote_path=f"{_LOGS}/{name}", filename=name
        )
    await agent.exec_as_agent(
        environment,
        command=(
            f"mkdir -p {shlex.quote(str(identity.state_dir))} && "
            f"cp {_LOGS}/openclaw.upload.json {shlex.quote(env['OPENCLAW_CONFIG_PATH'])}"
        ),
        env=env,
    )
    skills = agent._build_register_skills_command()
    if skills:
        await agent.exec_as_agent(environment, command=skills, env=env)
    driver_finished = False
    try:
        # Use environment.exec directly: a driver error must escape Harbor's
        # NonZeroAgentExitCodeError catch, which would otherwise proceed to scoring.
        result = await environment.exec(
            command=_NODE + f'node {_LOGS}/gateway_driver.mjs "$(command -v openclaw)"',
            env=env,
        )
        driver_finished = True
        await environment.download_file(
            source_path=f"{_LOGS}/openclaw-status.json",
            target_path=agent.logs_dir / "openclaw-status.json",
        )
        state = json.loads((agent.logs_dir / "openclaw-status.json").read_text())
        if result.return_code or state.get("state") != "completed":
            raise OpenClawAgentIncompleteError(
                "OpenClaw parent did not complete: "
                + state.get("error", state.get("state", "unknown"))
            )
    finally:
        # Cancelling an exec request need not kill its container-side process.
        # Signal only our driver; it snapshots the transcript and stops its Gateway.
        if not driver_finished:
            try:
                await asyncio.wait_for(
                    environment.exec(
                        command=_NODE + 'node -e \'const fs=require("fs");'
                        f'const p="{_LOGS}/openclaw-driver.pid";'
                        'if(fs.existsSync(p)){try{process.kill(Number(fs.readFileSync(p,"utf8")),"SIGTERM");}'
                        'catch(e){if(e.code!=="ESRCH")throw e;}'
                        'const end=Date.now()+5000;'
                        'const timer=setInterval(()=>{if(!fs.existsSync(p)||Date.now()>end)'
                        'clearInterval(timer);},50);}\'',
                        env=env,
                    ),
                    timeout=10,
                )
            except Exception:
                agent.logger.debug("Gateway driver cleanup deferred to Harbor", exc_info=True)
