#!/usr/bin/env python
"""List OpenCV camera indices that open successfully."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def find_cameras(max_index: int = 10) -> list[int]:
    try:
        import cv2
    except ImportError as e:
        raise SystemExit("opencv-python is required (comes with lerobot).") from e

    found: list[int] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        ok = cap.isOpened()
        if ok:
            ret, _ = cap.read()
            ok = bool(ret)
        cap.release()
        if ok:
            found.append(i)
            print(f"  [{i}] OK")
        else:
            print(f"  [{i}] —")
    return found


def write_example(found: list[int], out: Path) -> None:
    keys = ["left_wrist", "right_wrist", "side", "front"]
    cams = {}
    for i, key in enumerate(keys):
        idx = found[i] if i < len(found) else i
        cams[key] = {
            "type": "opencv",
            "index_or_path": idx,
            "width": 640,
            "height": 480,
            "fps": 30,
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cams, indent=2) + "\n")
    print(f"Wrote draft config to {out} (edit indices to match your mounting).")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-index", type=int, default=10)
    p.add_argument("--write", type=Path, default=None, help="Write configs/cameras.json draft")
    args = p.parse_args(argv)
    print("Probing cameras…")
    found = find_cameras(args.max_index)
    print(f"Found {len(found)} camera(s): {found}")
    if args.write is not None:
        write_example(found, args.write)


if __name__ == "__main__":
    main()
