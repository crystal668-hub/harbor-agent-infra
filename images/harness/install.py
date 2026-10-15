"""Build-time installer. Receives only public lock data in an isolated build context."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from preinstalled_probe import (
    SCHEMA,
    actual_identity,
    digest,
    inventory,
    shell,
    shell_prefix,
    verify,
)
from runtime_patches import (
    hermes_model_id_patch_command,
    hermes_output_patch_command,
    openclaw_adaptive_patch_command,
)

ROOT = Path(__file__).parent
DOWNLOADS = Path("/tmp/hai-downloads")


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def fetch(url: str, destination: Path, checksum: str, algorithm: str = "sha256") -> Path:
    if not url.startswith("https://") or "@" in urlsplit(url).netloc:
        raise ValueError("build sources must be public HTTPS URLs")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            hasher = hashlib.new(algorithm)
            with (
                urllib.request.urlopen(url, timeout=120) as source,
                destination.open("wb") as target,
            ):
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    hasher.update(chunk)
            actual = (base64.b64encode(hasher.digest()).decode()
                      if algorithm == "sha512" else hasher.hexdigest())
            if actual != checksum:
                raise ValueError("download checksum mismatch: " + url)
            return destination
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("download failed")


def verified_asset(item: dict, filename: str) -> Path:
    return fetch(item["url"], DOWNLOADS / filename, item["sha256"])


def install_node(inputs: dict) -> list[str]:
    node = inputs["node"]
    nvm_dir = Path.home() / ".nvm"
    nvm_dir.mkdir()
    run(["tar", "-xzf", str(verified_asset(inputs["nvm"], "nvm.tar.gz")),
         "--strip-components=1", "-C", str(nvm_dir)])
    node_dir = nvm_dir / "versions" / "node" / ("v" + node["version"])
    node_dir.mkdir(parents=True)
    run(["tar", "-xJf", str(verified_asset(node, "node.tar.xz")),
         "--strip-components=1", "-C", str(node_dir)])
    alias = nvm_dir / "alias"
    alias.mkdir(exist_ok=True)
    (alias / "default").write_text(node["version"] + "\n")
    return [str(nvm_dir / "nvm.sh"), str(nvm_dir / "nvm-exec"), str(alias), str(node_dir)]


def capture_patches(name: str, roots: list[str], commit: str | None) -> dict:
    commands = {}
    if name == "openclaw":
        commands["openclaw-adaptive"] = openclaw_adaptive_patch_command()
    elif name == "hermes":
        commands["hermes-output"] = hermes_output_patch_command(commit)
        commands["hermes-model-id"] = hermes_model_id_patch_command(commit)
    patches = {}
    for key, command in commands.items():
        original = inventory(roots)
        # Only two small known source locations can be patched; do not retain a
        # second in-memory copy of the full binary/dependency installation.
        candidates = (list(Path(shell(name, "npm root -g")).joinpath("openclaw/dist").glob("*.js"))
                      if name == "openclaw" else
                      [Path("/tmp/hermes/hermes-agent/agent/agent_init.py"),
                       Path("/tmp/hermes/hermes-agent/agent/anthropic_adapter.py"),
                       Path("/tmp/hermes/hermes-agent/hermes_cli/model_normalize.py")])
        snapshots = {str(path): path.read_bytes() for path in candidates}
        try:
            run(["bash", "-c", command], env={**os.environ, "HERMES_HOME": "/tmp/hermes"})
            changed = inventory(roots)
            if changed.keys() != original.keys():
                raise ValueError("patch changed installation file set")
            files = {path: {"before": original[path]["sha256"], "after": state["sha256"]}
                     for path, state in changed.items() if state != original[path]}
            if not files or not set(files) <= snapshots.keys():
                raise ValueError("patch did not match the expected source files")
            patches[key] = {"definition_sha256": digest(command.encode()), "files": files}
        finally:
            for path, content in snapshots.items():
                Path(path).write_bytes(content)
    return patches


def main():
    build = json.loads((ROOT / "build.json").read_text())
    lock = build["lock"]
    inputs = build["inputs"]
    name = build["name"]
    pin = lock[{"claude-code": "claude_code"}.get(name, name)]
    source = {}
    roots = []
    dependencies = {}
    if build.get("reuse_installed"):
        verify({
            "manifest_sha256": build["reuse_installed"]["manifest_sha256"],
            "name": name, "version": pin["package_version"],
            "source_commit": pin["source_commit"], "parent_image": build["parent_image"],
            "platform": inputs["platform"], "patches": {}, "phase": "before",
        })
        original = json.loads(Path("/opt/hai/harness-manifest.json").read_text())
        if original["name"] != name or original["parent_image"] != build["parent_image"]:
            raise ValueError("reused installation identity mismatch")
        roots = original["roots"]
        source = original["source"]
        dependencies = original["dependencies"]
    elif name in {"openclaw", "codex"}:
        roots = install_node(inputs)
        integrity = pin["package_integrity"]
        if not integrity.startswith("sha512-"):
            raise ValueError("unsupported npm integrity")
        tarball = fetch(pin["package_tarball"], DOWNLOADS / "agent.tgz",
                        integrity.removeprefix("sha512-"), "sha512")
        run(["bash", "-c", shell_prefix(name) + "npm install -g " + str(tarball)
             + " --fetch-retries=5"], timeout=1800)
        dependencies = json.loads(shell(name, "npm ls -g --all --json"))
        source = {"url": pin["package_tarball"], "integrity": integrity}
        node_dir = Path(roots[-1])
        # Preserve the paths Harbor's native execution expects.
        for binary in (["node", "codex"] if name == "codex" else []):
            target = Path("/usr/local/bin") / binary
            target.unlink(missing_ok=True)
            target.symlink_to(node_dir / "bin" / binary)
            roots.append(str(target))
    elif name == "claude-code":
        item = inputs["claude_binary"]
        if f"/{pin['version']}/linux-arm64/claude" not in item["url"]:
            raise ValueError("Claude binary URL does not match the runtime lock")
        official = fetch(item["manifest_url"], DOWNLOADS / "claude-manifest.json",
                         item["manifest_sha256"])
        checksum = json.loads(official.read_text())["platforms"]["linux-arm64"]["checksum"]
        if checksum != item["sha256"]:
            raise ValueError("Claude binary checksum differs from the official manifest")
        binary = verified_asset(item, "claude")
        target = Path.home() / ".local/share/claude/versions" / pin["version"]
        target.parent.mkdir(parents=True)
        shutil.move(binary, target)
        target.chmod(0o755)
        if b"DISABLE_AUTOUPDATER" not in target.read_bytes():
            raise ValueError("pinned Claude binary does not support the update-control switch")
        entry = Path.home() / ".local/bin/claude"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.symlink_to(target)
        roots = [str(entry), str(target)]
        source = item
    elif name == "hermes":
        item = inputs["hermes_installer"]
        if f"/{pin['source_commit']}/scripts/install.sh" not in item["url"]:
            raise ValueError("Hermes installer does not match the runtime lock")
        installer = verified_asset(item, "hermes-install.sh")
        for attempt in range(3):
            try:
                run(["bash", str(installer), "--skip-setup", "--branch", pin["install_branch"],
                     "--commit", pin["source_commit"]],
                    env={**os.environ, "HERMES_HOME": "/tmp/hermes", "CI": "1"}, timeout=2400)
                break
            except subprocess.CalledProcessError:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        roots = ["/tmp/hermes/hermes-agent", "/tmp/hermes/tools", "/root/.local/bin/hermes"]
        managed = Path.home() / ".local/share/uv/python"
        if managed.exists():
            roots.append(str(managed))
        source = item
        dependencies = {"pm_lock_sha256": digest(
            Path("/tmp/hermes/hermes-agent/pm/lock.json").read_bytes())}
    else:
        raise ValueError("unsupported harness")
    if name == "hermes":
        os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
        # The pinned release intentionally excludes Anthropic from [all] and
        # otherwise installs it lazily on its first provider request.
        run(["bash", "-c", shell_prefix(name) + "hermes pm install --extra anthropic"],
            timeout=1800)
        if "/tmp/hermes/installs" not in roots:
            roots.append("/tmp/hermes/installs")
        # A metadata-only version probe bypasses normal activation. Exercise
        # a normal command with lazy repair disabled before freezing files.
        shell(name, "hermes sessions --help >/dev/null")
        for facts in Path("/tmp/hermes/installs").glob("*/facts.json"):
            environment = Path(json.loads(facts.read_text())["packages"]["venv"]["environment"])
            run([str(environment / "bin/python"), "-c", "import openai, anthropic"])
        dependencies["provider_modules"] = ["openai", "anthropic"]
    identity = actual_identity(name)
    version = pin["package_version"] if name == "hermes" else pin["version"]
    if identity["version"] != version:
        raise ValueError("installed harness version mismatch")
    if name == "hermes" and identity["source_commit"] != pin["source_commit"]:
        raise ValueError("installed Hermes source mismatch")
    if name in {"openclaw", "codex"} and identity["runtimes"] != {
        "node": "v" + inputs["node"]["version"], "npm": inputs["node"]["npm_version"],
    }:
        raise ValueError("installed Node/npm version mismatch")
    patches = capture_patches(name, roots, pin.get("source_commit"))
    manifest = {
        "schema_version": SCHEMA, "name": name, **identity, "platform": inputs["platform"],
        "parent_image": build["parent_image"], "source": source, "dependencies": dependencies,
        "build_inputs": inputs, "roots": roots, "files": inventory(roots), "patches": patches,
        **({"refined_from": build["reuse_installed"]} if build.get("reuse_installed") else {}),
    }
    Path("/opt/hai/harness-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
