#!/bin/bash
set -euo pipefail
exec uv run --locked --python 3.12 python scripts/run_formal_matrix.py --interactive "$@"
