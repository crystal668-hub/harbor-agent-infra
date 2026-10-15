"""Guarded compatibility edits for the immutable installed harness releases."""

from __future__ import annotations

import json
import shlex


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
""".replace("SOURCE_COMMIT", json.dumps(source_commit))
    return "python3 -c " + shlex.quote(script)
