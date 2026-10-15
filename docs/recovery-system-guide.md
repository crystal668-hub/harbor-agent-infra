# Recovery System User Guide

## Overview

The recovery system enables you to identify, classify, and recover from failures in experimental runs. It follows a three-phase workflow:

1. **Audit**: Scan a completed run for failures and generate a recovery manifest
2. **Recover**: Execute approved recovery attempts
3. **Merge**: Integrate successful recoveries back into the original results

## Quick Start

### 1. Audit a Run

After a run completes, scan it for failures:

```bash
hai audit <run-name> --artifacts-dir run-artifacts
```

This generates a `recovery-manifest.json` in the run directory containing all detected failures.

**Example output:**
```
Auditing run: run-artifacts/formal/exp-2026-10-14

Detected Failures:
  Engineering failures: 3
  Capability failures: 2
  Scoring failures: 1
  Total: 6

Recovery manifest saved to: run-artifacts/formal/exp-2026-10-14/recovery-manifest.json
```

### 2. Review and Approve Failures

Open the generated manifest and review each failure:

```json
{
  "slots": [
    {
      "job_name": "openclaw-opus",
      "task_id": "rdkit_001",
      "failure_classification": {
        "category": "ENGINEERING",
        "reason": "Network timeout during image pull",
        "is_substitutable": true
      },
      "approved": false
    }
  ]
}
```

**Approval Guidelines:**
- **Engineering failures** (network, image, auth): Set `approved: true` - these are substitutable
- **Capability failures** (timeout, wrong answer): Leave `approved: false` - these are valid results
- **Scoring failures** (verifier errors): Review evidence and approve if verifier issue

**Auto-approve option:**
```bash
hai audit <run-name> --auto-approve-substitutable
```

This automatically approves all engineering failures.

### 3. Execute Recovery

Run approved recovery attempts:

```bash
hai recover recovery-manifest.json \
  --config configs/experiment.toml \
  --output-dir run-artifacts/recovery-2026-10-14
```

**Dry run (preview only):**
```bash
hai recover recovery-manifest.json --dry-run
```

For native `hai run` artifacts, add `--config` to validate the actual saved
Harbor JobConfig and task selection without creating a Job or an output directory:

```bash
uv run --locked --python 3.12 hai recover recovery-manifest.json \
  --config configs/experiments/claude-code/vgb-deepseek.config.yaml --dry-run
```

Recovery loads the saved `jobs/<job>/config.json` from the manifest's `run_dir`
or the original run's configured output directory. Historical manifests whose
`original_run` is empty or `unknown` fall back to the manifest's run name.
Each recovery Job selects exactly the failed task and gets its own directory;
the other saved execution settings and original artifacts are preserved. A missing
snapshot or an ambiguous task selection prevents that slot from running.

**Example output:**
```
Recovery Execution Complete: recovery-2026-10-14
======================================================================
Total slots: 3
Executed: 3
Succeeded: 2
Failed: 1
Skipped: 0
======================================================================

Slot Results:
  ✓ openclaw-opus::rdkit_001 - success
  ✓ hermes-qwen::rdkit_005 - success
  ✗ codex-gpt::xtb_002 - failed
```

### 4. Merge Results

Merge successful recoveries back into the original run:

```bash
hai merge \
  run-artifacts/formal/exp-2026-10-14 \
  run-artifacts/recovery-2026-10-14 \
  --output-dir run-artifacts/formal/exp-2026-10-14-merged
```

**Example output:**
```
Merge Complete
======================================================================
Original run: exp-2026-10-14
Recovery runs: 1
Total recovery slots: 3
Successfully merged: 2
Conflicts: 0
======================================================================

✓ Merged results saved to: run-artifacts/formal/exp-2026-10-14-merged
```

### 5. Analyze Results

Generate recovery statistics:

```bash
hai analyze run-artifacts/recovery-2026-10-14
```

**Example output:**
```
======================================================================
Recovery Analysis Report
======================================================================

Failure Overview:
  Total failures: 6
  Engineering: 3
  Capability: 2
  Scoring: 1
  Substitutable: 4

Recovery Execution:
  Approved for recovery: 3
  Successfully recovered: 2
  Failed to recover: 1
  Overall recovery rate: 66.7%
  Engineering recovery rate: 66.7%

Top Failure Reasons:
  Network timeout: 2
  Image pull error: 1
  Agent timeout: 2
  Verifier runtime error: 1

Failures by Job:
  openclaw-opus: 2
  hermes-qwen: 2
  codex-gpt: 1
  claude-code-deepseek: 1
======================================================================
```

**Save statistics as JSON:**
```bash
hai analyze run-artifacts/recovery-2026-10-14 \
  --output stats.json
```

## Workflow Details

### Failure Classification

The audit system automatically classifies failures into three categories:

#### 1. Engineering Failures (Substitutable)
Infrastructure and tooling issues that don't reflect agent capability:
- Network timeouts
- Docker image pull failures
- Authentication errors
- Registry connectivity issues

**Action**: Approve for recovery

#### 2. Capability Failures (Non-substitutable)
Legitimate agent performance issues:
- Agent timeouts
- Wrong answers
- Low scores
- Task refusal

**Action**: Keep as-is (valid result)

#### 3. Scoring Failures (Case-by-case)
Verifier or scoring system issues:
- Verifier crashes
- Runtime errors in scoring
- Invalid expected outputs

**Action**: Review evidence and approve if verifier issue

### Recovery Limits

To prevent infinite retry loops, the system enforces limits:
- Maximum 2 substitution attempts per slot
- Recovery manifest tracks `n_previous_attempts`
- Slots exceeding limit are marked non-substitutable

### Merged Run Structure

After merging, the output directory contains:

```
exp-2026-10-14-merged/
├── jobs/
│   └── openclaw-opus/
│       └── trials/
│           ├── rdkit_001__trial-0/          # Recovered trial
│           │   ├── result.json
│           │   ├── recovery-marker.json     # Recovery metadata
│           │   └── ...
│           └── rdkit_001__trial-0__replaced/  # Original failed trial (backup)
│               ├── result.json
│               └── ...
└── merge-metadata.json  # Merge audit trail
```

**Recovery marker format:**
```json
{
  "recovered": true,
  "recovery_job": "openclaw-opus-recovery",
  "recovery_run": "recovery-2026-10-14",
  "merged_at": "2026-10-14T10:30:00Z",
  "original_trial_backup": "rdkit_001__trial-0__replaced"
}
```

## Best Practices

### 1. Always Audit First
Don't manually edit manifests - let the audit system detect failures automatically.

### 2. Review Before Recovery
Check the manifest's failure classifications. Auto-approval is convenient but review recommended for production runs.

### 3. Use Dry Run
Test recovery plans with `--dry-run` before executing, especially for large runs.

### 4. Preserve Original Runs
Never merge directly into the original run directory. Always use a new output directory.

### 5. Keep Recovery Runs
Don't delete recovery run directories - they're needed for traceability and future merges.

### 6. Check Statistics
Run `hai analyze` after recovery to verify success rates and identify persistent issues.

### 7. Multiple Recovery Passes
You can run multiple recovery passes if initial attempts fail:

```bash
# First pass
hai recover manifest-1.json --output-dir recovery-pass-1

# Audit the recovery run itself
hai audit recovery-pass-1 --output-dir recovery-pass-1

# Second pass
hai recover recovery-pass-1/recovery-manifest.json \
  --output-dir recovery-pass-2

# Merge all passes
hai merge original-run recovery-pass-1 recovery-pass-2 \
  --output-dir merged
```

## Troubleshooting

### Issue: "Original job not found" during merge

**Cause**: The recovery manifest references a job that doesn't exist in the original run.

**Solution**: Verify the original run directory path and ensure the job name matches.

### Issue: Recovery fails with same error

**Cause**: The failure wasn't actually an engineering issue, or the underlying problem persists.

**Solution**: 
1. Review the recovery logs
2. Reclassify as capability failure if it's a persistent agent issue
3. Fix the underlying infrastructure problem if it's environmental

### Issue: Merge conflicts reported

**Cause**: Recovery trial doesn't match expected structure or original trial missing.

**Solution**: Check merge-metadata.json for conflict details and resolve manually if needed.

### Issue: Recovery rate lower than expected

**Cause**: Some approved failures are still failing on recovery.

**Solution**:
1. Run `hai analyze` to see failure breakdown
2. Review recovery logs for the failing slots
3. Consider if more attempts are needed or if reclassification is required

## Integration with Main Workflow

### Standard Experiment Workflow

```bash
# 1. Run experiment
hai run --config configs/experiment.toml \
  --output run-artifacts/formal/exp-2026-10-14

# 2. Wait for completion, then audit
hai audit exp-2026-10-14 --artifacts-dir run-artifacts/formal

# 3. Review and approve failures (edit manifest)

# 4. Execute recovery
hai recover run-artifacts/formal/exp-2026-10-14/recovery-manifest.json \
  --config configs/experiment.toml \
  --output-dir run-artifacts/recovery-2026-10-14

# 5. Merge results
hai merge \
  run-artifacts/formal/exp-2026-10-14 \
  run-artifacts/recovery-2026-10-14 \
  --output-dir run-artifacts/formal/exp-2026-10-14-final

# 6. Analyze final results
hai analyze run-artifacts/formal/exp-2026-10-14-final

# 7. Generate final report with merged results
# (use your normal reporting tools on the merged directory)
```

## Advanced Topics

### Custom Failure Classification

If the automatic classification is incorrect, you can manually edit the manifest:

```json
{
  "failure_classification": {
    "category": "CAPABILITY",  # Changed from ENGINEERING
    "reason": "Agent consistently fails this task type",
    "is_substitutable": false,
    "evidence": {
      "error_message": "...",
      "logs_snippet": "..."
    }
  },
  "approved": false  # Reject recovery
}
```

### Selective Recovery

Approve only specific failures by editing the manifest:

```bash
# Audit generates manifest with all failures
hai audit run-name

# Edit manifest: set approved=true only for specific slots
# Then recover only approved slots
hai recover manifest.json --config ...
```

### Batch Operations

Recover multiple runs:

```bash
for run in run-artifacts/formal/*; do
  hai audit "$run"
  # Review and approve...
  hai recover "$run/recovery-manifest.json" \
    --config configs/experiment.toml \
    --output-dir "run-artifacts/recovery-$(basename $run)"
done
```

## Exit Codes

All recovery commands return standard exit codes:

- `0`: Success
- `1`: Error (failure reported in output)
- `2`: Invalid arguments

Use these for scripting and automation:

```bash
if hai recover manifest.json --config experiment.toml; then
  echo "Recovery succeeded"
  hai merge original recovery --output-dir merged
else
  echo "Recovery failed, check logs"
  exit 1
fi
```
