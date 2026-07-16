#!/usr/bin/env python

"""Dataset repo_id versioning: ``{user}/so101_bi_{task}_v{NNN}`` (no datetime stamp)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from lerobot.utils.constants import HF_LEROBOT_HOME

_V_RE = re.compile(r"_v(\d+)$")


def next_versioned_repo_id(
    *,
    hf_user: str | None = None,
    task: str = "demo",
    explicit_repo_id: str | None = None,
) -> str:
    """Pick the next free ``…_vNNN`` repo id.

    If ``explicit_repo_id`` is provided, return it unchanged (caller owns uniqueness).
    Does **not** append a datetime — HF upload metadata already carries timestamps.
    """
    if explicit_repo_id:
        return explicit_repo_id

    user = hf_user or os.environ.get("HF_USER") or os.environ.get("HF_USERNAME") or "local"
    task_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", task).strip("_") or "demo"
    prefix = f"{user}/so101_bi_{task_slug}"
    used = _collect_used_versions(prefix)
    next_n = (max(used) + 1) if used else 1
    return f"{prefix}_v{next_n:03d}"


def _collect_used_versions(prefix: str) -> set[int]:
    used: set[int] = set()
    owner, name_prefix = prefix.split("/", 1)

    root = Path(HF_LEROBOT_HOME)
    if root.is_dir():
        # Local layouts: HF_LEROBOT_HOME/owner/name_v001 or HF_LEROBOT_HOME/owner_name_v001
        for path in root.rglob("*"):
            if not path.is_dir():
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel.startswith(prefix + "_v") or path.name.startswith(name_prefix + "_v"):
                m = _V_RE.search(rel if rel.startswith(prefix) else path.name)
                if m:
                    used.add(int(m.group(1)))

    try:
        from huggingface_hub import HfApi

        for info in HfApi().list_datasets(author=owner):
            if info.id.startswith(prefix + "_v"):
                m = _V_RE.search(info.id)
                if m:
                    used.add(int(m.group(1)))
    except Exception:
        pass

    return used
