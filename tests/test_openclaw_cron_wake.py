"""Provider-free guards for the pinned explicit-parent cron dispatch patch."""

from __future__ import annotations

import hashlib
import subprocess

from adapters import runtime_patches as patches
from tests.test_openclaw_edit_noop import apply_release_patch


def test_cron_wake_patch_is_idempotent_and_rejects_drift(tmp_path, monkeypatch):
    root = tmp_path / "openclaw"
    (root / "dist").mkdir(parents=True)
    version = root / "package.json"
    version.write_text('{"version":"2026.6.34"}')
    source = patches.OPENCLAW_CRON_WAKE_REPLACEMENTS[0][0]
    target = root / "dist/server-cron-CbQL-0jN.js"
    target.write_text(source)
    other = root / "dist/heartbeat.js"
    other.write_text("periodic scheduling unchanged")
    monkeypatch.setattr(patches, "OPENCLAW_CRON_WAKE_SHA256",
                        hashlib.sha256(source.encode()).hexdigest())
    command = patches.openclaw_cron_wake_patch_command()
    assert apply_release_patch(tmp_path, command).returncode == 0
    once = target.read_text()
    assert apply_release_patch(tmp_path, command).returncode == 0
    assert target.read_text() == once
    assert other.read_text() == "periodic scheduling unchanged"
    for content in (source + "// drift", once + "// drift", once.replace("boundKey", "other", 1)):
        target.write_text(content)
        assert apply_release_patch(tmp_path, command).returncode != 0
        assert target.read_text() == content
    target.write_text(source)
    version.write_text('{"version":"other"}')
    assert "Unexpected OpenClaw version" in apply_release_patch(tmp_path, command).stderr


def test_cron_dispatch_requires_bound_parent_and_preserves_original_job():
    script = """
const assert = require('node:assert/strict');
const resolveAgentIdFromSessionKey = key => key.split(':')[1];
process.env.OPENCLAW_AGENT_ID = 'openclaw';
process.env.OPENCLAW_SESSION_KEY = 'agent:openclaw:explicit:AbC';
""" + patches.OPENCLAW_CRON_WAKE_REPLACEMENTS[0][1] + """
return job;
}
(async () => {
  const job = {sessionTarget: 'main', sessionKey: 'agent:openclaw:explicit:abc',
    payload: {kind: 'systemEvent', text: 'Original reminder'}, state: {nextRunAtMs: 123}};
  const original = JSON.stringify(job);
  const mapped = await executeJobCore({}, job);
  assert.equal(mapped.sessionTarget, 'session:' + job.sessionKey);
  assert.deepEqual(mapped.payload, {kind: 'agentTurn', message: 'Original reminder'});
  assert.deepEqual(mapped.delivery, {mode: 'none'});
  assert.equal(mapped.state, job.state);
  assert.equal(JSON.stringify(job), original);
  for (const override of [{sessionKey: undefined}, {sessionKey: 'agent:openclaw:other'},
    {agentId: 'other'}, {sessionTarget: 'isolated'},
    {payload: {kind: 'systemEvent', text: '  '}}, {payload: {kind: 'agentTurn', message: 'x'}}]) {
    const other = {...job, ...override};
    assert.equal(await executeJobCore({}, other), other);
  }
  delete process.env.OPENCLAW_SESSION_KEY;
  assert.equal(await executeJobCore({}, job), job);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    subprocess.run(["node", "-e", script], check=True, timeout=15)
