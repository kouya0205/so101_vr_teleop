"""Console-script entry points."""

from __future__ import annotations


def find_cameras_main() -> None:
    from .find_cameras import main

    main()


def check_env_main() -> None:
    from .check_env import main

    main()
