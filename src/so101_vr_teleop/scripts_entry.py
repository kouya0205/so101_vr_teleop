"""Console-script entry points that delegate to scripts/ helpers."""

from __future__ import annotations

import runpy
from pathlib import Path


def _scripts_dir() -> Path:
    # Prefer repo scripts/ when editable; fall back to package-adjacent.
    here = Path(__file__).resolve()
    repo_scripts = here.parents[2] / "scripts"
    if repo_scripts.is_dir():
        return repo_scripts
    return here.parent.parent.parent / "scripts"


def find_cameras_main() -> None:
    runpy.run_path(str(_scripts_dir() / "find_cameras.py"), run_name="__main__")


def check_env_main() -> None:
    runpy.run_path(str(_scripts_dir() / "check_env.py"), run_name="__main__")
