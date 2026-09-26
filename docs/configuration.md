# Configuration

Local secrets and resource values belong in untracked files or environment variables.
The committed examples contain no credentials, private image references or machine paths.

To validate and materialize a Harbor JobConfig, provide every value explicitly:

```bash
uv run hai materialize \
  --experiment configs/experiments/openclaw-vgb-smoke.yaml \
  --resource-config configs/resources/local.yaml \
  --output run-artifacts/materialized-job.json
```

The command fails before any trial is allocated when a placeholder, profile, base image
digest, runtime lock or Docker resource capability is invalid. The output records the
experiment and resource configuration hashes plus Harbor's native JobConfig snapshot.

Agent base image references used for execution must include an immutable digest. The image
manager checks the local RepoDigest and OS/architecture before a Harbor job is created;
Harbor then installs the locked OpenClaw npm package in the Trial container. Registry
credentials are consumed by Docker's credential helper and are never written to evidence.
