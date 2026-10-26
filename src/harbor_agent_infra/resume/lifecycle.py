from __future__ import annotations

import fcntl
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from harbor.trial.hooks import TrialEvent

from harbor_agent_infra.resume.io import write_object


@contextmanager
def run_lock(root: Path, *, create=True):
    """Stable sibling inode also protects a formal run before its directory exists."""
    root = root.resolve()
    path = root.parent / f".{root.name}.hai.lock"
    if not create and not path.exists():
        yield
        return
    if create:
        root.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+" if create else "r") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("This hai run is active; refusing concurrent resume") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
    # Never unlink: waiters/new callers must lock the same inode.


def guarded_run(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        with run_lock(kwargs["output_root"]):
            return await function(*args, **kwargs)
    return wrapped


def attach_checkpoints(job):
    async def checkpoint(event):
        # Captures the original UUID before a hard kill can prevent result.json.
        directory = Path(event.config.trials_dir) / event.trial_name
        write_object(directory / "resume-checkpoint.json", event.result.model_dump(mode="json"))

    for event in (TrialEvent.START, TrialEvent.AGENT_START, TrialEvent.AGENT_END):
        job.add_hook(event, checkpoint)


def ensure_inactive(context, plan):
    """Catch legacy writers that predate the shared hai lock; never kill them."""
    identifiers = {str(context.root), *(c.job_name for c in context.jobs.values())}
    if context.config_path:
        identifiers.add(str(context.config_path))
        identifiers.add(str(context.config_path.relative_to(context.workspace))
                        if context.config_path.is_relative_to(context.workspace)
                        else str(context.config_path))
    processes = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True,
                               text=True, check=True).stdout
    for line in processes.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or int(parts[0]) in {os.getpid(), os.getppid()}:
            continue
        command = parts[1]
        if (re.search(r"(?:^|[/\s])(hai|harbor)\s+(run|job\s+(start|resume))\b", command)
                and any(identifier in command for identifier in identifiers)):
            raise ValueError(f"Original experiment process is still active (pid {parts[0]})")
    # Harbor publishes finished_at only after stopping the environment. A finalized
    # cancellation can be scored offline without requiring a running Docker daemon.
    interrupted = [i for i in plan if i.action in {"rerun", "score"}
                   and (i.result is None or i.result.finished_at is None)]
    if not interrupted:
        return
    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("Cannot verify interrupted Docker Trial inactivity: docker unavailable")
    result = subprocess.run([docker, "ps", "--format", "{{.Names}}"],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError("Cannot verify interrupted Trial inactivity: Docker is unavailable")
    names = result.stdout.lower()
    for item in interrupted:
        name = re.sub(r"[^a-z0-9_-]", "-", item.directory.name.lower())
        if name in names:
            raise ValueError(f"Trial environment is still active: {item.directory.name}")
