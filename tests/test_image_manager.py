from __future__ import annotations

import json
import subprocess

import pytest

from harbor_agent_infra.preparation.image_manager import (
    ImageManagerError,
    immutable_reference,
    inspect_image,
)


def test_immutable_reference_rejects_tag_only_digest() -> None:
    with pytest.raises(ImageManagerError):
        immutable_reference("example/agent:latest", "sha256:bad")


def test_image_inspect_validates_digest_and_platform() -> None:
    payload = {
        "Id": "sha256:" + "b" * 64,
        "RepoDigests": ["example/agent@sha256:" + "a" * 64],
        "Os": "linux",
        "Architecture": "arm64",
    }

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    evidence = inspect_image(
        "example/agent:smoke",
        digest="sha256:" + "a" * 64,
        platform="linux/arm64",
        runner=runner,
    )
    assert evidence.immutable_reference == "example/agent:smoke@sha256:" + "a" * 64
    assert evidence.pulled is False


def test_image_inspect_rejects_platform_mismatch() -> None:
    payload = {
        "Id": "sha256:" + "b" * 64,
        "RepoDigests": ["example/agent@sha256:" + "a" * 64],
        "Os": "linux",
        "Architecture": "amd64",
    }

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    with pytest.raises(ImageManagerError, match="platform mismatch"):
        inspect_image(
            "example/agent:smoke",
            digest="sha256:" + "a" * 64,
            platform="linux/arm64",
            runner=runner,
        )
