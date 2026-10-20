"""Guarded compatibility edits for the immutable installed harness releases."""

from __future__ import annotations

import json
import shlex

OPENCLAW_TRANSPORT_SHA256 = "03f9d627b15e955ab3143310ea9f6dbdfb15bedcf0a7b8dad0e30d3226300d20"

# Embedded into one existing release file; also executed directly by the contract tests.
OPENCLAW_NETWORK_RETRY_JS = r"""
// HAI bounded pre-response Anthropic network retry, version 1.
let haiNetworkRequestSequence = 0;
function haiNetworkErrorCode(error) {
  const seen = new Set();
  let code = null;
  for (let depth = 0; error && typeof error === 'object'; depth++) {
    if (depth === 8 || seen.has(error)) return null;
    seen.add(error);
    if (error.name === 'AbortError' || error.name === 'SsrFBlockedError') return null;
    const connectionCodes = ['ENOTFOUND', 'EAI_AGAIN', 'ECONNREFUSED', 'UND_ERR_CONNECT_TIMEOUT'];
    if (connectionCodes.includes(error.code) ||
        (error.code === 'ETIMEDOUT' && error.syscall === 'connect')) code ??= error.code;
    error = error.cause;
  }
  return code;
}
function haiNetworkDelay(retry) {
  return Math.min(5000, Math.round(1000 * 2 ** retry * (0.8 + 0.4 * Math.random())));
}
function haiNetworkSleep(ms, signal) {
  signal?.throwIfAborted();
  return new Promise((resolve, reject) => {
    const cleanup = () => { clearTimeout(timer); signal?.removeEventListener('abort', abort); };
    const abort = () => { cleanup(); reject(signal.reason); };
    const timer = setTimeout(() => { cleanup(); resolve(); }, ms);
    signal?.addEventListener('abort', abort, {once: true});
  });
}
async function haiFetchWithNetworkRetry(fetch, url, init, context) {
  const requestId = `${process.pid}-${++haiNetworkRequestSequence}`;
  const record = (event, details) => console.warn('[provider-network-retry] ' + JSON.stringify({
    event, request_id: requestId, provider: context?.provider, model: context?.model,
    session_id: context?.session_id, max_attempts: 4, ...details
  }));
  for (let attempt = 1; ; attempt++) {
    init.signal?.throwIfAborted();
    try {
      const response = await fetch(url, init);
      if (attempt > 1) record('response', {attempt, status: response.status});
      return response;
    } catch (error) {
      init.signal?.throwIfAborted();
      const code = haiNetworkErrorCode(error);
      if (!code) throw error;
      if (attempt === 4) {
        record('exhausted', {attempt, code});
        throw error;
      }
      const delayMs = haiNetworkDelay(attempt - 1);
      record('retry', {attempt, code, delay_ms: delayMs});
      await haiNetworkSleep(delayMs, init.signal);
      init.signal?.throwIfAborted();
    }
  }
}
"""


def openclaw_network_retry_patch_command() -> str:
    """Patch only the exact pinned native Anthropic pre-response fetch boundary."""
    anchor = "function createAnthropicMessagesClient(params) {"
    before = (
        "const response = await params.fetch(url, {\n"
        '\t\t\tmethod: "POST",\n\t\t\theaders,\n'
        "\t\t\tbody: JSON.stringify(body),\n\t\t\tsignal: options?.signal\n\t\t});"
    )
    after = before.replace("params.fetch(url,", "haiFetchWithNetworkRetry(params.fetch, url,")
    after = after.removesuffix("});") + "}, params.retryContext);"
    patches = [(anchor, OPENCLAW_NETWORK_RETRY_JS + anchor, 1), (before, after, 1)]
    for tabs, count in (("\t\t\t\t", 3), ("\t\t\t", 1)):
        before = f"{tabs}fetch\n{tabs[:-1]}}}),"
        after = (f"{tabs}fetch,\n{tabs}retryContext: {{provider: model.provider, "
                 f"model: model.id, session_id: options?.sessionId}}\n{tabs[:-1]}}}),")
        patches.append((before, after, count))
    script = r"""
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const npmRoot = require('node:child_process').execSync('npm root -g').toString().trim();
const root = path.join(npmRoot, 'openclaw');
if (JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version !== '2026.6.34')
  throw new Error('Unexpected OpenClaw version');
const replacements = PATCHES;
const hash = text => crypto.createHash('sha256').update(text).digest('hex');
const anchor = 'function createAnthropicMessagesClient(params) {';
const files = fs.readdirSync(path.join(root, 'dist')).filter(name => name.endsWith('.js'))
  .map(name => path.join(root, 'dist', name))
  .filter(file => fs.readFileSync(file, 'utf8').includes(anchor));
if (files.length !== 1) throw new Error('Expected one Anthropic transport contract');
const original = fs.readFileSync(files[0], 'utf8');
let baseline = original;
if (original.includes('// HAI bounded pre-response Anthropic network retry, version 1.'))
  for (const [before, after, count] of [...replacements].reverse()) {
    if (baseline.split(after).length !== count + 1) throw new Error('Network retry patch drift');
    baseline = baseline.split(after).join(before);
  }
if (hash(baseline) !== BASELINE_HASH) throw new Error('Unexpected OpenClaw transport checksum');
let patched = baseline;
for (const [before, after, count] of replacements) {
  if (patched.split(before).length !== count + 1)
    throw new Error('Unexpected Anthropic fetch anchor');
  patched = patched.split(before).join(after);
}
if (patched !== original) fs.writeFileSync(files[0], patched);
""".replace("PATCHES", json.dumps(patches)).replace(
        "BASELINE_HASH", json.dumps(OPENCLAW_TRANSPORT_SHA256)
    )
    return ". ~/.nvm/nvm.sh && nvm use 22 && node -e " + shlex.quote(script)


def openclaw_adaptive_patch_command() -> str:
    # Opus 5.5 requires adaptive thinking but is absent from this release's
    # model predicate. Extend the predicate without changing the wire model ID.
    script = r"""
const fs = require('node:fs');
const path = require('node:path');
const globalRoot = require('node:child_process').execSync('npm root -g').toString().trim();
const root = path.join(globalRoot, 'openclaw');
const version = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version;
if (version !== '2026.6.34') throw new Error('Unexpected OpenClaw version');
const before = 'claude-(?:fable-5|mythos-preview|opus-4-(?:6|7|8)|sonnet-4-6)';
const after = 'claude-(?:opus-5-5|fable-5|mythos-preview|opus-4-(?:6|7|8)|sonnet-4-6)';
let found = 0;
for (const entry of fs.readdirSync(path.join(root, 'dist'))) {
  if (!entry.endsWith('.js')) continue;
  const file = path.join(root, 'dist', entry);
  const text = fs.readFileSync(file, 'utf8');
  if (!text.includes('function supportsClaudeAdaptiveThinking(ref)')) continue;
  if (text.includes(after)) { found++; continue; }
  if (text.split(before).length !== 2) throw new Error('Unexpected adaptive predicate');
  fs.writeFileSync(file, text.replace(before, after));
  found++;
}
if (found !== 1) throw new Error('Expected one adaptive model contract');
"""
    return ". ~/.nvm/nvm.sh && nvm use 22 && node -e " + shlex.quote(script)


def hermes_output_patch_command(source_commit: str) -> str:
    # Both CLI constructors omit AIAgent(max_tokens). Feed the explicit cap
    # into initialization, before the normal adapters and session capture consume it.
    script = r"""
import os, subprocess
from pathlib import Path
root = Path(os.environ.get("HERMES_HOME", "/tmp/hermes")) / "hermes-agent"
expected = SOURCE_COMMIT
actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True)
if actual.strip() != expected:
    raise RuntimeError("Unexpected Hermes source commit")
file = root / "agent/agent_init.py"
text = file.read_text()
before = '    _params = locals()'
after = ('    if max_tokens is None and os.environ.get("HAI_MAX_OUTPUT_TOKENS"):\n'
         '        max_tokens = int(os.environ["HAI_MAX_OUTPUT_TOKENS"])\n'
         '    _params = locals()')
if after not in text:
    if text.count(before) != 1:
        raise RuntimeError("Unexpected Hermes session output-cap initializer")
    file.write_text(text.replace(before, after))
""".replace("SOURCE_COMMIT", json.dumps(source_commit))
    return "python3 -c " + shlex.quote(script)


def hermes_model_id_patch_command(source_commit: str) -> str:
    """Preserve the gateway's exact Opus 5.5 ID on custom Anthropic endpoints."""
    script = r"""
import os, subprocess
from pathlib import Path
root = Path(os.environ.get('HERMES_HOME', '/tmp/hermes')) / 'hermes-agent'
actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
if actual != SOURCE_COMMIT:
    raise RuntimeError('Unexpected Hermes source commit')
file = root / 'hermes_cli/model_normalize.py'
text = file.read_text()
before = '    provider = _normalize_provider_alias(target_provider)'
after = (before + '\n'
         '    import os\n'
         '    from urllib.parse import urlsplit\n'
         '    endpoint = os.environ.get("ANTHROPIC_BASE_URL", "")\n'
         '    if (provider == "anthropic" and name == "claude-opus-5.5"\n'
         '            and endpoint and urlsplit(endpoint).hostname != "api.anthropic.com"):\n'
         '        return name')
if after not in text:
    if text.count(before) != 1:
        raise RuntimeError('Unexpected Hermes model normalization contract')
    file.write_text(text.replace(before, after))
file = root / 'agent/anthropic_adapter.py'
text = file.read_text()
before = '        model = normalize_model_name(model, preserve_dots=preserve_dots)'
after = ('        preserve_dots = preserve_dots or (model == "claude-opus-5.5"\n'
         '            and _is_third_party_anthropic_endpoint(base_url))\n' + before)
if after not in text:
    if text.count(before) != 1:
        raise RuntimeError('Unexpected Hermes Anthropic request contract')
    file.write_text(text.replace(before, after))
""".replace("SOURCE_COMMIT", json.dumps(source_commit))
    return "python3 -c " + shlex.quote(script)
