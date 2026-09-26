#!/bin/sh
set -eu

test -s /logs/agent/agent-output.v1.json
grep -q '"schema_version": "agent-output.v1"' /logs/agent/agent-output.v1.json
printf '1\n' > /logs/verifier/reward.txt
