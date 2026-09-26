from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from harbor import Job, JobConfig


async def run(config_path: Path) -> int:
    config = JobConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    job = await Job.create(config)
    result = await job.run()
    print(result.model_dump_json(indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Harbor fake-agent smoke")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
