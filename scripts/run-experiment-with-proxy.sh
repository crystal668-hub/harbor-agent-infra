#!/bin/bash
# Run experiment with Docker-compatible proxy settings

set -eo pipefail

# Replace localhost with host.docker.internal for Docker containers (if set)
if [ -n "${HTTP_PROXY:-}" ]; then
  export HTTP_PROXY="${HTTP_PROXY/localhost/host.docker.internal}"
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  export HTTPS_PROXY="${HTTPS_PROXY/localhost/host.docker.internal}"
fi
if [ -n "${http_proxy:-}" ]; then
  export http_proxy="${http_proxy/localhost/host.docker.internal}"
fi
if [ -n "${https_proxy:-}" ]; then
  export https_proxy="${https_proxy/localhost/host.docker.internal}"
fi
if [ -n "${ALL_PROXY:-}" ]; then
  export ALL_PROXY="${ALL_PROXY/localhost/host.docker.internal}"
fi
if [ -n "${all_proxy:-}" ]; then
  export all_proxy="${all_proxy/localhost/host.docker.internal}"
fi
if [ -n "${GRPC_PROXY:-}" ]; then
  export GRPC_PROXY="${GRPC_PROXY/localhost/host.docker.internal}"
fi
if [ -n "${grpc_proxy:-}" ]; then
  export grpc_proxy="${grpc_proxy/localhost/host.docker.internal}"
fi

echo "Starting experiment..."
if [ -n "${HTTP_PROXY:-}" ]; then
  echo "HTTP_PROXY=$HTTP_PROXY"
  echo "HTTPS_PROXY=${HTTPS_PROXY:-}"
  echo "NO_PROXY=${NO_PROXY:-}"
fi
echo ""

# Create log directory
mkdir -p logs/formal-experiments

# Run the experiment
exec env UV_CACHE_DIR="${TMPDIR:-/tmp}/uv-cache-$$" \
  uv run hai run \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml \
  --group skills_off
