"""Exercise the real driver shutdown with only its SDK and Gateway boundary faked."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_driver_keeps_interrupted_when_sdk_stop_rejects_request(tmp_path, signum):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "openclaw-run.json").write_text(json.dumps({
        "sessionId": "fixture", "sessionKey": "agent:openclaw:fixture", "agentId": "openclaw",
        "idempotencyKey": "fixture", "message": "test",
    }))
    source = Path("adapters/openclaw")
    driver = (source / "gateway_driver.mjs").read_text().replace(
        'const logs = "/logs/agent";', "const logs = " + json.dumps(str(logs)) + ";"
    )
    (logs / "gateway_driver.mjs").write_text(driver)
    shutil.copyfile(source / "gateway_session.mjs", logs / "gateway_session.mjs")
    runtime = tmp_path / "runtime"
    sdk = runtime / "dist/plugin-sdk"
    sdk.mkdir(parents=True)
    (runtime / "package.json").write_text('{"type":"module"}')
    entry = runtime / "openclaw.mjs"
    entry.write_text("setInterval(() => {}, 1000);\n")
    pending = tmp_path / "pending"
    (sdk / "gateway-runtime.js").write_text(
        "import fs from 'node:fs';\n"
        "export class GatewayClient {\n"
        "  constructor(options) {this.options = options;}\n"
        "  start() {queueMicrotask(() => this.options.onHelloOk());}\n"
        "  request() {return new Promise((resolve, reject) => {\n"
        "    this.reject = reject; fs.writeFileSync(" + json.dumps(str(pending)) + ", 'ready');\n"
        "  });}\n"
        "  stop() {this.reject?.(new Error('gateway client stopped'));}\n"
        "}\n"
    )
    process = subprocess.Popen(
        ["node", str(logs / "gateway_driver.mjs"), str(entry)],
        env={**os.environ, "OPENCLAW_STATE_DIR": str(tmp_path / "state")},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not pending.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pending.exists(), "driver did not submit the SDK request"
        process.send_signal(signum)
        stdout, stderr = process.communicate(timeout=6)
        assert process.returncode == 130, (stdout, stderr)
        status = json.loads((logs / "openclaw-status.json").read_text())
        assert status["state"] == "interrupted"
        assert "error" not in status
        assert not (logs / "openclaw-driver.pid").exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=6)
