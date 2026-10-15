"""Build one candidate harness image without modifying the active runtime lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from harbor_agent_infra.preparation.image_manager import inspect_image
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

ROOT = Path(__file__).resolve().parents[1]


def require_idle_docker() -> None:
    active = subprocess.check_output(["docker", "ps", "-q"], text=True).strip()
    if active:
        raise RuntimeError("Docker has active containers; defer image validation until they finish")


def require_new_reference(reference: str) -> None:
    if not reference or "@" in reference or any(character.isspace() for character in reference):
        raise ValueError("candidate build reference must be a concrete local build handle")
    found = subprocess.run(
        ["docker", "image", "inspect", reference], capture_output=True, check=False,
    )
    if found.returncode == 0:
        raise ValueError("candidate build reference already exists; choose a new handle")


def build_context(directory: Path, name: str, lock_path: Path, inputs_path: Path) -> dict:
    lock = load_runtime_lock(lock_path)
    inputs = json.loads(inputs_path.read_text())
    if inputs.get("schema_version") != "harness-build-inputs.v1":
        raise ValueError("unsupported harness build inputs")
    if inputs["platform"] != lock.agent_base_image.platform:
        raise ValueError("build input platform differs from runtime lock")
    build = {"name": name, "lock": json.loads(lock_path.read_text()), "inputs": inputs,
             "parent_image": lock.agent_base_image.immutable_reference}
    (directory / "build.json").write_text(json.dumps(build, sort_keys=True))
    for source, destination in (
        (ROOT / "images/harness/Dockerfile", "Dockerfile"),
        (ROOT / "images/harness/install.py", "install.py"),
        (ROOT / "adapters/preinstalled_probe.py", "preinstalled_probe.py"),
        (ROOT / "adapters/runtime_patches.py", "runtime_patches.py"),
    ):
        shutil.copyfile(source, directory / destination)
    return build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=("openclaw", "hermes", "codex", "claude-code"))
    parser.add_argument("--lock", type=Path, default=ROOT / "runtime-lock.json")
    parser.add_argument("--inputs", type=Path, default=ROOT / "images/harness/build-inputs.json")
    parser.add_argument("--reference", required=True, help="Unique local candidate build handle")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reuse-installed", action="store_true",
                        help="Reseal the locked Hermes candidate without reinstalling")
    args = parser.parse_args()
    # This entry point deliberately has no implicit push or default-config mutation.
    require_idle_docker()
    require_new_reference(args.reference)
    lock = load_runtime_lock(args.lock)
    output = args.output_dir.absolute()
    output.mkdir(parents=True, exist_ok=True)
    metadata = output / (args.name + "-build-metadata.json")
    if any((output / (args.name + suffix)).exists() for suffix in (
        "-build-metadata.json", "-installation.json", "-runtime-lock.json",
    )):
        raise ValueError("candidate artifacts already exist; choose a new output directory")
    base = lock.agent_base_image
    if args.reuse_installed:
        if args.name != "hermes":
            raise ValueError("installation reuse is only supported for the Hermes refinement")
        base = lock.execution_image(args.name, "preinstalled")
    parent = inspect_image(
        base.reference, digest=base.digest, platform=base.platform,
    )
    # BuildKit may resolve a local RepoDigest remotely. A unique private build
    # handle refers to the verified image ID; it is never a runtime identity.
    parent_handle = "hai-build-parent-" + uuid.uuid4().hex
    subprocess.run(["docker", "tag", parent.image_id, parent_handle], check=True)
    try:
        with tempfile.TemporaryDirectory(prefix="hai-harness-build-") as temp:
            directory = Path(temp)
            build = build_context(directory, args.name, args.lock, args.inputs)
            if args.reuse_installed:
                build["reuse_installed"] = {
                    "manifest_sha256": base.manifest_sha256,
                    "image": base.immutable_reference,
                }
                (directory / "build.json").write_text(json.dumps(build, sort_keys=True))
            subprocess.run([
                "docker", "buildx", "build", "--load", "--platform", lock.agent_base_image.platform,
                "--build-arg", "BASE_IMAGE=" + parent_handle,
                "--metadata-file", str(metadata), "--tag", args.reference, str(directory),
            ], check=True)
        found = subprocess.check_output(
            ["docker", "image", "inspect", parent_handle, "--format", "{{.Id}}"], text=True,
        ).strip()
        if found != parent.image_id:
            raise ValueError("local build parent identity changed")
    finally:
        subprocess.run(["docker", "image", "rm", parent_handle], check=True)
    image_digest = json.loads(metadata.read_text())["containerimage.digest"]
    immutable = args.reference.split("@", 1)[0] + "@" + image_digest
    inspect_image(args.reference, digest=image_digest, platform=lock.agent_base_image.platform)
    require_idle_docker()
    data = subprocess.check_output([
        "docker", "run", "--rm", "--pull=never", "--network=none", "--cpus=1", "--memory=2g",
        "--entrypoint", "cat", immutable, "/opt/hai/harness-manifest.json",
    ])
    manifest = json.loads(data)
    (output / (args.name + "-installation.json")).write_bytes(data)
    item = {
        "reference": args.reference, "digest": image_digest,
        "platform": lock.agent_base_image.platform, "version": lock.harness_version(args.name),
        "manifest_sha256": hashlib.sha256(data).hexdigest(),
        **({"source_commit": lock.hermes.source_commit} if args.name == "hermes" else {}),
    }
    if manifest["version"] != item["version"] or manifest["name"] != args.name:
        raise ValueError("build manifest differs from runtime lock")
    candidate = json.loads(args.lock.read_text())
    candidate.setdefault("harness_images", {})[args.name] = item
    candidate_path = output / (args.name + "-runtime-lock.json")
    candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    load_runtime_lock(candidate_path)
    print(json.dumps({"candidate_lock": str(candidate_path), "image": immutable}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
