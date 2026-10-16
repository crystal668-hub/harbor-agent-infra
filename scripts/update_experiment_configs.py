#!/usr/bin/env python3
"""
Update experiment configuration templates to match formal experiment plan.

Ensures all 16 harness×model configs use the formal experiment contract:
- Agent timeout: 7200s (2 hours)
- Resources: 4 CPU / 6144 MB
- Concurrent trials: 2
- max_retries: 0
- Groups: skills_off only
- The main workspace runtime-lock.preinstalled.json and matching harness image
- Output dir: run-artifacts/formal/<experiment-id>
"""

import sys
from pathlib import Path

import yaml

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def update_config(config_path: Path, lock_path: Path, lock) -> bool:
    """Update a single config file with unified parameters."""
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Track changes
        changes = []

        # Formal experiments declare only the authorized skills_off group.
        groups = [{
            'id': 'skills_off',
            'label': 'benchmark skills disabled',
            'skills_enabled': False,
        }]
        if config['experiment'].get('groups') != groups:
            config['experiment']['groups'] = groups
            changes.append('groups: skills_off only')

        experiment = config['experiment']
        harness = experiment['agent']['adapter']
        image = lock.execution_image(harness, 'preinstalled')
        if experiment['benchmark'].get('package_lock') != str(lock_path):
            experiment['benchmark']['package_lock'] = str(lock_path)
            changes.append('package_lock: main workspace runtime-lock.preinstalled.json')
        if experiment['agent'].get('installation_mode') != 'preinstalled':
            experiment['agent']['installation_mode'] = 'preinstalled'
            changes.append('installation_mode: preinstalled')
        locked_image = {
            'reference': image.reference,
            'digest': image.digest,
            'platform': image.platform,
            'pull_policy': 'never',
        }
        if experiment.get('image') != locked_image:
            experiment['image'] = locked_image
            changes.append(f'image: {image.immutable_reference}')

        # Update task timeouts
        if config.get('task', {}).get('agent_timeout_sec') != 7200:
            config.setdefault('task', {})['agent_timeout_sec'] = 7200
            changes.append('agent_timeout_sec: 7200')

        if config.get('task', {}).get('verifier_timeout_sec') != 120:
            config.setdefault('task', {})['verifier_timeout_sec'] = 120
            changes.append('verifier_timeout_sec: 120')

        # Update resources
        profiles = config.get('resources', {}).get('profiles', {})
        for profile_name, profile in profiles.items():
            if profile.get('cpus') != 4:
                profile['cpus'] = 4
                changes.append(f'{profile_name}.cpus: 4')
            if profile.get('memory_mb') != 6144:
                profile['memory_mb'] = 6144
                changes.append(f'{profile_name}.memory_mb: 6144')

        # Update concurrent trials
        capacity = config.get('resources', {}).get('capacity', {})
        if capacity.get('max_concurrent_trials') != 2:
            capacity['max_concurrent_trials'] = 2
            changes.append('max_concurrent_trials: 2')

        # Ensure max_retries is 0
        retry = config.get('experiment', {}).get('retry', {})
        if retry.get('max_retries') != 0:
            retry['max_retries'] = 0
            changes.append('max_retries: 0')

        # Update output_dir to formal path
        output_dir = config.get('run', {}).get('output_dir', '')
        if (
            output_dir.startswith('run-artifacts/')
            and not output_dir.startswith('run-artifacts/formal/')
        ):
            # Extract experiment ID from current path
            old_dir = output_dir.replace('run-artifacts/', '')
            new_dir = f'run-artifacts/formal/{old_dir}'
            config['run']['output_dir'] = new_dir
            changes.append(f'output_dir: {new_dir}')

        # Write back if changes made
        if changes:
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            print(f"✓ {config_path.relative_to(Path.cwd())}")
            for change in changes:
                print(f"  - {change}")
            return True
        else:
            print(f"  {config_path.relative_to(Path.cwd())} (no changes needed)")
            return False

    except Exception as e:
        print(f"✗ {config_path.relative_to(Path.cwd())}: {e}", file=sys.stderr)
        raise


def main():
    """Update all experiment configs."""
    repo_root = Path(__file__).parent.parent
    configs_dir = repo_root / 'configs' / 'experiments'
    lock_path = (repo_root / 'runtime-lock.preinstalled.json').resolve()
    lock = load_runtime_lock(lock_path)

    harnesses = ['openclaw', 'hermes', 'codex', 'claude-code']
    models = ['gpt', 'claude', 'qwen', 'deepseek']

    total = 0
    updated = 0

    print("Updating experiment configuration templates...\n")

    for harness in harnesses:
        harness_dir = configs_dir / harness
        if not harness_dir.exists():
            print(f"⚠ {harness_dir} does not exist, skipping")
            continue

        for model in models:
            config_file = harness_dir / f'vgb-{model}.config.yaml'
            if config_file.exists():
                total += 1
                if update_config(config_file, lock_path, lock):
                    updated += 1
            else:
                raise FileNotFoundError(f"formal config is missing: {config_file}")

    print(f"\n{'='*60}")
    print(f"Summary: {updated}/{total} configs updated")

    if updated > 0:
        print("\nNext steps:")
        print("1. Validate all configs: bash scripts/run_formal_experiments.sh --dry-run")
        print("2. Run tests: uv run --locked --python 3.12 pytest -m 'not integration'")

    return 0 if total == len(harnesses) * len(models) else 1


if __name__ == '__main__':
    sys.exit(main())
