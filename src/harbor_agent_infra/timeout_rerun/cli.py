"""CLI for explicitly frozen timeout campaigns."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


def register(subparsers):
    parser = subparsers.add_parser(
        "timeout-rerun", help="plan, run and merge repeat1 timeout amendments"
    )
    commands = parser.add_subparsers(dest="timeout_command", required=True)
    plan = commands.add_parser(
        "plan", help="freeze selected final snapshots and 12h execution inputs"
    )
    plan.add_argument("snapshots", type=Path, nargs="+")
    plan.add_argument("--output-dir", type=Path, required=True)
    plan.add_argument("--runtime-lock", type=Path, default=Path("runtime-lock.json"))
    run = commands.add_parser("run", help="execute or reconcile a frozen campaign")
    run.add_argument("manifest", type=Path)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--reviews", type=Path)
    run.add_argument("--env-file", type=Path)
    merge = commands.add_parser("merge", help="publish complete revised formal snapshots")
    merge.add_argument("manifest", type=Path)
    merge.add_argument("--output-dir", type=Path, required=True)
    merge.add_argument("--dry-run", action="store_true")
    merge.add_argument("--reviews", type=Path)


def dispatch(args):
    try:
        if args.timeout_command == "plan":
            from harbor_agent_infra.timeout_rerun.plan import create_plan

            plan = create_plan(args.snapshots, args.output_dir, args.runtime_lock)
            result = {
                k: plan[k]
                for k in (
                    "root",
                    "total_slots",
                    "candidate_slots",
                    "initial_trial_hours",
                    "plan_sha256",
                )
            }
        elif args.timeout_command == "run":
            from harbor_agent_infra.timeout_rerun.execution import run_campaign

            result = asyncio.run(
                run_campaign(
                    args.manifest,
                    dry_run=args.dry_run,
                    reviews=args.reviews,
                    env_file=args.env_file,
                )
            )
        else:
            from harbor_agent_infra.timeout_rerun.merge import merge_campaign

            result = merge_campaign(
                args.manifest, args.output_dir, dry_run=args.dry_run, reviews=args.reviews
            )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 2 if result.get("complete") is False and not getattr(args, "dry_run", False) else 0
    except (ValueError, OSError) as exc:
        print(f"Timeout rerun blocked: {exc}")
        return 1
