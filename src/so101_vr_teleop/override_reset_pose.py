#!/usr/bin/env python

# Copyright 2026 NVIDIA Corporation and The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Save current left/right SO-101 joint poses as the reset-origin override."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lerobot.robots.bi_so_follower import BiSOFollower, BiSOFollowerConfig
from lerobot.robots.so_follower import SOFollowerConfig

from .common import RESET_POSE_FILE


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--left-port", default="/dev/ttyACM0")
    p.add_argument("--right-port", default="/dev/ttyACM1")
    p.add_argument("--id", default="bi_so101")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = BiSOFollowerConfig(
        id=args.id,
        left_arm_config=SOFollowerConfig(port=args.left_port, use_degrees=True),
        right_arm_config=SOFollowerConfig(port=args.right_port, use_degrees=True),
    )
    robot = BiSOFollower(cfg)
    robot.connect()
    try:
        obs = robot.get_observation()
        motor_names = [k.removesuffix(".pos") for k in robot.action_features if k.endswith(".pos")]
        pose = {name: float(obs[f"{name}.pos"]) for name in motor_names}
    finally:
        robot.disconnect()

    print("Current joint positions:")
    for name, val in pose.items():
        print(f"  {name:28s}: {val:.2f}")

    reset_pose_file = Path(RESET_POSE_FILE.format(robot_name=robot.name, robot_id=robot.id))
    reset_pose_file.parent.mkdir(parents=True, exist_ok=True)
    reset_pose_file.write_text(json.dumps(pose, indent=2))
    print(f"\nSaved to {reset_pose_file}")


if __name__ == "__main__":
    main()
