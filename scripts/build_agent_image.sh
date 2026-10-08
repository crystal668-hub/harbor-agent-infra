#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_reference="${1:?usage: $0 <immutable image tag> [--push]}"
push_image="${2:-}"

if [[ "$image_reference" == *"@"* ]]; then
  echo "pass a tag for the build output; the resulting RepoDigest is the lock identity" >&2
  exit 2
fi

docker build \
  --platform linux/arm64 \
  --tag "$image_reference" \
  "$repo_root/images/openclaw-agent"

if [[ "$push_image" == "--push" ]]; then
  docker push "$image_reference"
fi

digest="$(docker image inspect "$image_reference" --format '{{index .RepoDigests 0}}')"
printf '%s\n' "$digest"
docker run --rm --platform linux/arm64 --entrypoint python3 "$digest" \
  -c 'import sys; print(sys.version.split()[0])'
docker run --rm --platform linux/arm64 --entrypoint pip3 "$digest" --version
docker run --rm --platform linux/arm64 --entrypoint sh "$digest" -lc \
  '! command -v openclaw && command -v bash && command -v curl && command -v git && command -v pgrep && command -v rg && command -v xz && python3 -c "from rdkit import Chem; print(Chem.MolToSmiles(Chem.MolFromSmiles(\"CCO\")))" && xtb --version | grep -q "xtb version 6.5.1"'
