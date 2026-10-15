from __future__ import annotations

import json
import os
import shlex
import subprocess

import pytest

from adapters.runtime_patches import hermes_output_patch_command, openclaw_adaptive_patch_command


def test_hermes_model_id_patch_preserves_only_exact_id_for_custom_endpoint(tmp_path, monkeypatch):
    from adapters.runtime_patches import hermes_model_id_patch_command

    root = tmp_path / "hermes-agent"
    (root / "hermes_cli").mkdir(parents=True)
    (root / "agent").mkdir()
    wire = root / "agent/anthropic_adapter.py"
    wire.write_text(
        "def _is_third_party_anthropic_endpoint(url): return url == 'https://gateway.example'\n"
        "def normalize_model_name(model, preserve_dots=False):\n"
        "    return model if preserve_dots else model.replace('.', '-')\n"
        "def build_anthropic_kwargs(model, base_url, preserve_dots=False):\n"
        "    if True:\n"
        "        model = normalize_model_name(model, preserve_dots=preserve_dots)\n"
        "    return {'model': model}\n"
    )
    file = root / "hermes_cli/model_normalize.py"
    file.write_text(
        "def _normalize_provider_alias(provider): return provider\n"
        "def normalize_model_for_provider(model_input, target_provider):\n"
        "    name = model_input\n"
        "    provider = _normalize_provider_alias(target_provider)\n"
        "    return name.replace('.', '-') if provider == 'anthropic' else name\n"
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.org",
        "commit", "-qm", "fixture",
    ], check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
    ).strip()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    script = shlex.split(hermes_model_id_patch_command(commit))[2]
    exec(script)
    once = file.read_text()
    exec(script)
    assert file.read_text() == once
    namespace = {}
    exec(once, namespace)
    normalize = namespace["normalize_model_for_provider"]
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.example")
    assert normalize("claude-opus-5.5", "anthropic") == "claude-opus-5.5"
    assert normalize("claude-sonnet-4.6", "anthropic") == "claude-sonnet-4-6"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    assert normalize("claude-opus-5.5", "anthropic") == "claude-opus-5-5"
    wire_namespace = {}
    exec(wire.read_text(), wire_namespace)
    build = wire_namespace["build_anthropic_kwargs"]
    assert build("claude-opus-5.5", "https://gateway.example")["model"] == "claude-opus-5.5"
    assert build("claude-opus-5.5", "https://api.anthropic.com")["model"] == "claude-opus-5-5"
    assert build("claude-sonnet-4.6", "https://gateway.example")["model"] == "claude-sonnet-4-6"
    monkeypatch.delenv("ANTHROPIC_BASE_URL")
    assert normalize("claude-opus-5.5", "anthropic") == "claude-opus-5-5"
    with pytest.raises(RuntimeError, match="source commit"):
        exec(shlex.split(hermes_model_id_patch_command("0" * 40))[2])


def test_hermes_patch_sets_live_cap_and_preserves_explicit_constructor_value(tmp_path, monkeypatch):
    root = tmp_path / "hermes-agent"
    (root / "agent").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    file = root / "agent/agent_init.py"
    file.write_text(
        "import os\n"
        "def initialize(agent, max_tokens=None):\n"
        "    _params = locals()\n"
        "    agent.max_tokens = _params['max_tokens']\n"
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.org",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    script = shlex.split(hermes_output_patch_command(commit))[2]
    exec(script)
    once = file.read_text()
    exec(script)
    assert file.read_text() == once
    namespace = {}
    exec(once, namespace)
    from types import SimpleNamespace

    monkeypatch.setenv("HAI_MAX_OUTPUT_TOKENS", "64000")
    agent = SimpleNamespace()
    namespace["initialize"](agent)
    assert agent.max_tokens == 64_000
    namespace["initialize"](agent, 1024)
    assert agent.max_tokens == 1024
    with pytest.raises(RuntimeError, match="source commit"):
        exec(shlex.split(hermes_output_patch_command("0" * 40))[2])


def test_openclaw_patch_preserves_manual_models_and_is_idempotent(tmp_path):
    root = tmp_path / "openclaw"
    (root / "dist").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"version": "2026.6.34"}))
    contract = root / "dist/contract.js"
    contract.write_text(
        "function supportsClaudeAdaptiveThinking(ref) {\n"
        "const modelId = ref.id.replaceAll('.', '-');\n"
        "return /(?:^|-)claude-(?:fable-5|mythos-preview|opus-4-(?:6|7|8)|sonnet-4-6)"
        "(?=$|[^a-z0-9])/.test(modelId);\n}\n"
        "module.exports = supportsClaudeAdaptiveThinking;\n"
    )
    npm = tmp_path / "npm"
    npm.write_text("#!/bin/sh\n" + "echo " + shlex.quote(str(tmp_path)) + "\n")
    npm.chmod(0o755)
    script = shlex.split(openclaw_adaptive_patch_command().split("node -e ", 1)[1])[0]
    env = dict(os.environ, PATH=str(tmp_path) + ":" + os.environ["PATH"])
    for _ in range(2):
        subprocess.run(["node", "-e", script], env=env, check=True)
    output = subprocess.check_output(
        [
            "node",
            "-e",
            "const fn=require(" + json.dumps(str(contract)) + ");"
            "console.log(JSON.stringify(['claude-opus-5.5','claude-opus-4-6','claude-opus-4-5']"
            ".map(id=>fn({id}))));",
        ],
        text=True,
    )
    assert json.loads(output) == [True, True, False]
    (root / "package.json").write_text(json.dumps({"version": "2026.9.5"}))
    result = subprocess.run(["node", "-e", script], env=env, capture_output=True)
    assert result.returncode != 0
    assert b"Unexpected OpenClaw version" in result.stderr
