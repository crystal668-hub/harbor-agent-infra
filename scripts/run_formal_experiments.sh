#!/bin/bash
set -euo pipefail
# One canonical original directory per harness/provider/repeat; no implicit resume.
exec uv run --locked --python 3.12 python scripts/run_formal_matrix.py "$@"
