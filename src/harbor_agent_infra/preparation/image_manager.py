from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_POLICIES = {"if_missing", "always", "never"}


class ImageManagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageEvidence:
    schema_version: str
    reference: str
    immutable_reference: str
    digest: str
    platform: str
    image_id: str
    repo_digests: tuple[str, ...]
    pull_policy: str
    pulled: bool
    inspected_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def immutable_reference(reference: str, digest: str) -> str:
    if not _DIGEST.fullmatch(digest):
        raise ImageManagerError(
            "image digest must be sha256 followed by 64 lowercase hex characters"
        )
    base = reference.split("@", 1)[0]
    if not base or "${" in base:
        raise ImageManagerError("image reference must be concrete before Docker access")
    return f"{base}@{digest}"


def _docker_json(
    args: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    result = runner(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ImageManagerError(result.stderr.strip() or f"Docker command failed: {' '.join(args)}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ImageManagerError("Docker inspect returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ImageManagerError("Docker inspect returned a non-object")
    return payload


def inspect_image(
    reference: str,
    *,
    digest: str,
    platform: str,
    pull_policy: str = "never",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ImageEvidence:
    if pull_policy not in _POLICIES:
        raise ImageManagerError(f"unsupported image pull policy: {pull_policy}")
    locked_reference = immutable_reference(reference, digest)
    pulled = False
    if pull_policy == "always":
        pull = runner(
            ["docker", "pull", locked_reference],
            capture_output=True,
            text=True,
            check=False,
        )
        if pull.returncode != 0:
            raise ImageManagerError(pull.stderr.strip() or "Docker image pull failed")
        pulled = True
    try:
        payload = _docker_json(
            ["docker", "image", "inspect", locked_reference, "--format", "{{json .}}"],
            runner=runner,
        )
    except ImageManagerError:
        if pull_policy == "never" or pulled:
            raise
        pull = runner(
            ["docker", "pull", locked_reference],
            capture_output=True,
            text=True,
            check=False,
        )
        if pull.returncode != 0:
            raise ImageManagerError(pull.stderr.strip() or "Docker image pull failed")
        pulled = True
        payload = _docker_json(
            ["docker", "image", "inspect", locked_reference, "--format", "{{json .}}"],
            runner=runner,
        )
    os_name = str(payload.get("Os") or "")
    architecture = str(payload.get("Architecture") or "")
    actual_platform = f"{os_name}/{architecture}"
    if actual_platform != platform:
        raise ImageManagerError(
            f"image platform mismatch: expected {platform}, got {actual_platform}"
        )
    repo_digests = tuple(
        str(item)
        for item in payload.get("RepoDigests", [])
        if isinstance(item, str)
    )
    if not any(item.rsplit("@", 1)[-1] == digest for item in repo_digests):
        raise ImageManagerError("local image RepoDigests do not contain the locked digest")
    return ImageEvidence(
        schema_version="image-evidence.v1",
        reference=reference,
        immutable_reference=locked_reference,
        digest=digest,
        platform=actual_platform,
        image_id=str(payload.get("Id") or ""),
        repo_digests=repo_digests,
        pull_policy=pull_policy,
        pulled=pulled,
        inspected_at=datetime.now(UTC).isoformat(),
    )
