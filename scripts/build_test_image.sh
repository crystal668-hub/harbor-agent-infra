#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build \
  --tag hai-fake-agent:acceptance \
  "$repo_root/tests/fixtures/fake-agent/task/environment"
