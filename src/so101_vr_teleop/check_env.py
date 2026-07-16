#!/usr/bin/env python
"""Quick environment diagnostics for SO-101 VR teleop."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=10)
    except Exception as e:
        return f"(failed: {e})"


def main() -> None:
    print("=== so101_vr_teleop check_env ===\n")

    print(f"OS: {platform.platform()}")
    rel = Path("/etc/os-release")
    if rel.is_file():
        text = rel.read_text()
        ver = re.search(r'VERSION_ID="?([^"\n]+)"?', text)
        name = re.search(r'PRETTY_NAME="?([^"\n]+)"?', text)
        print(f"  {name.group(1) if name else '?'}")
        if ver:
            v = ver.group(1)
            if v.startswith("22.") or v.startswith("24."):
                print(f"  Ubuntu {v}: OK (Isaac Teleop supports 22.04 and 24.04)")
            else:
                print(f"  WARNING: Ubuntu {v} is outside documented 22.04/24.04")

    print("\nNVIDIA:")
    smi = _run(["nvidia-smi"])
    if "CUDA Version" in smi:
        m = re.search(r"CUDA Version:\s*([\d.]+)", smi)
        d = re.search(r"Driver Version:\s*([\d.]+)", smi)
        print(f"  Driver: {d.group(1) if d else '?'}")
        print(f"  CUDA (driver capability): {m.group(1) if m else '?'}")
        if m:
            major_minor = tuple(int(x) for x in m.group(1).split(".")[:2])
            if major_minor >= (12, 8):
                print("  CUDA capability >= 12.8: OK")
            else:
                print("  WARNING: Isaac Teleop wants CUDA 12.8+ (nvidia-smi CUDA Version)")
        if d:
            # rough compare as strings of major
            print("  Driver >= 580.95 recommended")
    else:
        print(smi[:400])

    print("\nPython / packages:")
    print(f"  python: {platform.python_version()}")
    for pkg in ("lerobot", "isaacteleop", "cv2", "numpy"):
        try:
            mod = __import__(pkg if pkg != "cv2" else "cv2")
            ver = getattr(mod, "__version__", "?")
            print(f"  {pkg}: {ver}")
        except ImportError:
            print(f"  {pkg}: NOT INSTALLED")

    print("\nSerial ports:")
    ports = sorted(Path("/dev").glob("ttyACM*")) + sorted(Path("/dev").glob("ttyUSB*"))
    if ports:
        for p in ports:
            print(f"  {p}")
    else:
        print("  (none found — plug in SO-101 USB and re-check)")

    left = os.environ.get("SO101_LEFT_PORT")
    right = os.environ.get("SO101_RIGHT_PORT")
    if left or right:
        print(f"  env LEFT={left} RIGHT={right}")

    print("\nTools:")
    for t in ("uv", "gh", "ffmpeg"):
        print(f"  {t}: {shutil.which(t) or 'missing'}")

    print("\nDone.")


if __name__ == "__main__":
    main()
