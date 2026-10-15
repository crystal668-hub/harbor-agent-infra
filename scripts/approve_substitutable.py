#!/usr/bin/env python3
"""Auto-approve substitutable failures in recovery manifest."""

import json
import sys
from pathlib import Path


def auto_approve_substitutable(manifest_path: Path, categories: list[str] | None = None):
    """Auto-approve substitutable failures.

    Args:
        manifest_path: Path to recovery-manifest.json
        categories: List of categories to approve (default: ['ENGINEERING'])
    """
    if categories is None:
        categories = ['ENGINEERING']

    with open(manifest_path) as f:
        manifest = json.load(f)

    slots = manifest['slots']
    approved_count = 0

    for slot in slots:
        classification = slot['failure_classification']
        category = classification['category']
        is_substitutable = classification['is_substitutable']

        # Auto-approve if:
        # 1. It's substitutable
        # 2. It's in the approved categories
        if is_substitutable and category in categories:
            slot['approved'] = True
            approved_count += 1

    # Save updated manifest
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"✓ Auto-approved {approved_count} substitutable failures")
    print(f"  Categories: {', '.join(categories)}")
    print(f"\nNext step: Review and manually approve other failures if needed")

    return approved_count


def main():
    if len(sys.argv) < 2:
        print('Usage: approve_substitutable.py <recovery-manifest.json> [categories...]')
        print('       approve_substitutable.py recovery-manifest.json')
        print('       approve_substitutable.py recovery-manifest.json ENGINEERING SCORING')
        sys.exit(1)

    manifest_path = Path(sys.argv[1])

    if not manifest_path.exists():
        print(f'Error: {manifest_path} not found')
        sys.exit(1)

    # Get categories from args, default to ENGINEERING only
    categories = sys.argv[2:] if len(sys.argv) > 2 else None

    approved_count = auto_approve_substitutable(manifest_path, categories)

    if approved_count == 0:
        print("\n⚠ No substitutable failures found to approve")
    else:
        print(f"\n✓ Manifest updated: {manifest_path}")


if __name__ == '__main__':
    main()
