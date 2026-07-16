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

"""Teleoperate a bimanual SO-101 via Quest XR controllers (Isaac Teleop)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from lerobot.cameras import CameraConfig  # noqa: F401
from lerobot.cameras.opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.configs import parser
from lerobot.robots import RobotConfig
from lerobot.robots.bi_so_follower import BiSOFollowerConfig  # noqa: F401
from lerobot.robots.so_follower import SOFollowerConfig  # noqa: F401
from lerobot.utils.robot_utils import precise_sleep

from .common import FPS, RESET_DURATION_S, HoldLatch, build_device
from .isaac_teleop import IsaacTeleopConfig


def _maybe_load_cameras(robot_cfg: RobotConfig) -> None:
    """If ``SO101_CAMERAS_JSON`` points at a file, merge it into top-level cameras."""
    path = Path(__import__("os").environ.get("SO101_CAMERAS_JSON", "configs/cameras.json"))
    if not path.is_file():
        return
    if not hasattr(robot_cfg, "cameras"):
        return
    raw = json.loads(path.read_text())
    cams = {}
    for name, spec in raw.items():
        cams[name] = OpenCVCameraConfig(
            index_or_path=spec["index_or_path"],
            width=spec.get("width", 640),
            height=spec.get("height", 480),
            fps=spec.get("fps", 30),
        )
    robot_cfg.cameras = cams


@dataclass
class TeleoperateConfig:
    teleop: IsaacTeleopConfig
    robot: RobotConfig
    reset_to_origin: bool = True
    reset_duration: float = RESET_DURATION_S


@parser.wrap()
def teleoperate(cfg: TeleoperateConfig):
    _maybe_load_cameras(cfg.robot)
    robot, device, motor_names = build_device(cfg)
    hold = HoldLatch(motor_names)
    try:
        while True:
            t0 = time.perf_counter()
            obs = robot.get_observation()
            action = hold.resolve(device.compute(obs), obs)
            robot.send_action(action)
            precise_sleep(max(1.0 / FPS - (time.perf_counter() - t0), 0.0))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            device.cleanup()
        finally:
            robot.disconnect()


def main():
    teleoperate()


if __name__ == "__main__":
    main()
