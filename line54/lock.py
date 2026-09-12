"""The selection lock: estimation cannot run on an unverified boundary set.

This is the mechanism behind "my selection rule predates my results". The lock
is written by a person after checking every provenance row against its source,
and it pins the exact bytes of provenance.csv that were checked.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config


class SelectionNotLocked(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    # Normalise line endings so a git autocrlf checkout does not break the lock.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=config.ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_lock(verified_by: str, selected_urns: list[str], provenance: Path = config.PROVENANCE_FILE,
               lock: Path = config.SELECTION_LOCK) -> dict:
    payload = {
        "provenance_sha256": file_sha256(provenance),
        "selected_urns": sorted(selected_urns),
        "verified_by": verified_by,
        "locked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head_at_lock": _git_head(),
    }
    lock.write_text(json.dumps(payload, indent=2))
    return payload


def require_lock(provenance: Path = config.PROVENANCE_FILE, lock: Path = config.SELECTION_LOCK) -> dict:
    if not lock.exists():
        raise SelectionNotLocked(
            f"{lock.name} does not exist. Verify every row of {provenance.name} against its source, "
            "then run: python -m pipeline.lock_selection --verified-by \"Your Name\""
        )
    payload = json.loads(lock.read_text())
    actual = file_sha256(provenance)
    if payload["provenance_sha256"] != actual:
        raise SelectionNotLocked(
            f"{provenance.name} changed since it was locked ({payload['provenance_sha256'][:12]} -> {actual[:12]}). "
            "Record the change in DEVIATIONS.md and re-lock."
        )
    return payload
