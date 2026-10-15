#!/usr/bin/env python3
"""Audit VGB experiment results and generate recovery manifest.

This script analyzes results.json from a VGB experiment run and identifies
failed tasks that should be retried, classifying them by failure type.
"""

import json
import sys
from pathlib import Path
from typing import Any


def classify_failure(result: dict[str, Any]) -> tuple[str, str, bool]:
    """Classify a failure and determine if it's substitutable.

    Returns:
        (category, reason, is_substitutable)
    """
    failure_mode = result.get('failure_mode')
    execution_error = result.get('execution_error_kind')
    trial_result = result.get('trial_result', {})
    exception_info = trial_result.get('exception_info') if trial_result else None

    # Check for agent timeout
    if failure_mode == 'agent_timeout':
        return ('CAPABILITY', 'Agent exceeded time limit', False)

    # Check for network/infrastructure errors
    if execution_error:
        if 'network' in execution_error.lower():
            return ('ENGINEERING', f'Network error: {execution_error}', True)
        if 'docker' in execution_error.lower() or 'container' in execution_error.lower():
            return ('ENGINEERING', f'Container error: {execution_error}', True)

    # Check for exceptions in trial execution
    if exception_info:
        exc_type = exception_info.get('exception_type', 'Unknown')
        exc_msg = exception_info.get('exception_message', '')

        # Network/infrastructure exceptions
        if any(term in exc_type.lower() or term in exc_msg.lower()
               for term in ['network', 'connection', 'timeout', 'refused']):
            return ('ENGINEERING', f'{exc_type}: {exc_msg[:100]}', True)

        # Environment/setup exceptions
        if any(term in exc_type.lower() or term in exc_msg.lower()
               for term in ['docker', 'container', 'image', 'registry']):
            return ('ENGINEERING', f'{exc_type}: {exc_msg[:100]}', True)

        # Other exceptions - likely not substitutable
        return ('SCORING', f'{exc_type}: {exc_msg[:100]}', False)

    # Score is zero but no clear error - likely capability issue
    if result.get('scored') and result.get('vgb_domain_result', {}).get('score') == 0.0:
        return ('CAPABILITY', 'Zero score - agent failed task', False)

    # No score at all - likely scoring/verifier issue
    if not result.get('scored'):
        return ('SCORING', 'Task not scored - verifier issue', True)

    return ('UNKNOWN', 'Unclassified failure', False)


def audit_vgb_run(results_json_path: Path) -> dict[str, Any]:
    """Audit a VGB run and generate recovery manifest.

    Args:
        results_json_path: Path to results.json file

    Returns:
        Recovery manifest dict
    """
    with open(results_json_path) as f:
        data = json.load(f)

    results = data.get('results', [])
    run_metadata = data.get('metadata', {})

    slots = []
    stats = {
        'total': len(results),
        'scored': 0,
        'failed': 0,
        'engineering': 0,
        'capability': 0,
        'scoring': 0,
        'unknown': 0,
        'substitutable': 0,
    }

    for result in results:
        task_name = result.get('task_name', 'unknown')
        trial_name = result.get('trial_name', 'unknown')
        scored = result.get('scored', False)

        stats['scored'] += int(scored)

        # Determine if this is a failure
        is_failure = False
        score = None

        # Check for score
        vgb_result = result.get('vgb_domain_result', {})
        if vgb_result:
            score = vgb_result.get('score')

        # Also check trial_result.verifier_result
        trial_result = result.get('trial_result', {})
        if trial_result and score is None:
            verifier_result = trial_result.get('verifier_result', {})
            rewards = verifier_result.get('rewards', {}) if verifier_result else {}
            score = rewards.get('vgb_score')

        # Failure conditions:
        # 1. Not scored at all
        # 2. Scored but zero
        # 3. Has exception_info
        # 4. Has failure_mode
        if not scored:
            is_failure = True
        elif score is not None and score == 0.0:
            is_failure = True
        elif trial_result and trial_result.get('exception_info'):
            is_failure = True
        elif result.get('failure_mode'):
            is_failure = True

        if is_failure:
            stats['failed'] += 1

            # Classify the failure
            category, reason, is_substitutable = classify_failure(result)

            stats[category.lower()] += 1
            if is_substitutable:
                stats['substitutable'] += 1

            slot = {
                'job_name': f"claude-code-vgb-deepseek-cross-provider-skills_off",
                'task_id': task_name,
                'task_name': task_name,
                'trial_name': trial_name,
                'original_trial_id': trial_result.get('id', 'unknown') if trial_result else 'unknown',
                'failure_classification': {
                    'category': category,
                    'reason': reason,
                    'is_substitutable': is_substitutable,
                },
                'substitution_count': 0,
                'original_run': run_metadata.get('run_name', 'unknown'),
                'approved': False,  # Require manual approval
                'score': score,
                'failure_mode': result.get('failure_mode'),
                'execution_error_kind': result.get('execution_error_kind'),
            }

            slots.append(slot)

    manifest = {
        'version': '1.0',
        'original_run': run_metadata.get('run_name', results_json_path.parent.name),
        'audit_timestamp': '2026-10-15T00:00:00Z',  # Current time in practice
        'stats': stats,
        'slots': slots,
    }

    return manifest


def main():
    if len(sys.argv) < 2:
        print('Usage: audit_vgb_results.py <path-to-results.json>')
        print('       audit_vgb_results.py <run-directory>')
        sys.exit(1)

    input_path = Path(sys.argv[1])

    # Handle both results.json file and directory paths
    if input_path.is_dir():
        results_json_path = input_path / 'results.json'
    else:
        results_json_path = input_path

    if not results_json_path.exists():
        print(f'Error: {results_json_path} not found')
        sys.exit(1)

    # Generate manifest
    manifest = audit_vgb_run(results_json_path)

    # Save manifest
    output_path = results_json_path.parent / 'recovery-manifest.json'
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    # Print summary
    stats = manifest['stats']
    print(f"\n{'='*70}")
    print(f"VGB Run Audit Complete")
    print(f"{'='*70}")
    print(f"Run: {manifest['original_run']}")
    print(f"\nOverall Statistics:")
    print(f"  Total tasks: {stats['total']}")
    print(f"  Scored tasks: {stats['scored']}")
    print(f"  Failed tasks: {stats['failed']}")
    print(f"\nFailure Breakdown:")
    print(f"  Engineering failures: {stats['engineering']} (substitutable)")
    print(f"  Capability failures: {stats['capability']} (not substitutable)")
    print(f"  Scoring failures: {stats['scoring']} (substitutable)")
    print(f"  Unknown failures: {stats['unknown']}")
    print(f"\nSubstitutable: {stats['substitutable']}/{stats['failed']}")
    print(f"\n✓ Recovery manifest saved to: {output_path}")
    print(f"\nNext steps:")
    print(f"  1. Review manifest: {output_path}")
    print(f"  2. Approve failures for recovery (set approved: true)")
    print(f"  3. Run recovery: hai recover {output_path}")


if __name__ == '__main__':
    main()
