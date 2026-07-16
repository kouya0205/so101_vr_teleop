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

"""Shared device + control-loop infrastructure for bimanual SO-101 VR teleop.

Adapted from LeRobot ``examples/isaac_teleop_to_so101/common.py`` for
``bi_so_follower`` + ``bi_xr_controller``.
"""

from __future__ import annotations

import json
import logging
import socket
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Protocol

import numpy as np

from lerobot.model.kinematics import RobotKinematics
from lerobot.processor import (
    RobotProcessorPipeline,
    robot_action_observation_to_transition,
    transition_to_robot_action,
)
from lerobot.robots import RobotConfig, make_robot_from_config
from lerobot.robots.bi_so_follower import BiSOFollowerConfig  # noqa: F401
from lerobot.robots.so_follower import SOFollowerConfig  # noqa: F401
from lerobot.robots.so_follower.robot_kinematic_processor import (
    EEBoundsAndSafety,
    InverseKinematicsEEToJoints,
)
from lerobot.types import RobotAction, RobotObservation
from lerobot.utils.constants import HF_LEROBOT_HOME
from lerobot.utils.robot_utils import precise_sleep

from .isaac_teleop import (
    BiXRController,
    BiXRControllerConfig,
    Clutch,
    IsaacTeleopConfig,
    MapXRControllerActionToRobotAction,
)

FPS = 30
CLOUDXR_ENV_FILE = str(files(__package__) / "default.env")

# Unprefixed SO-101 motor names (URDF / per-arm IK).
ARM_MOTOR_NAMES = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]

MAX_EE_STEP_M = 0.1
IK_ORIENTATION_WEIGHT = 0.01
RESET_DURATION_S = 5.0
ALIGN_DURATION_S = 3.0  # unused (no physical leader); kept for LoopConfig compatibility

RESET_POSE_FILE = str(HF_LEROBOT_HOME / "reset_poses" / "{robot_name}" / "{robot_id}.json")

RESET_ORIGIN_DEG: dict[str, float] = {
    "shoulder_pan": -4.0,
    "shoulder_lift": -103.0,
    "elbow_flex": 97.0,
    "wrist_flex": 78.0,
    "wrist_roll": -65.0,
    "gripper": 0.0,
}


class LoopConfig(Protocol):
    teleop: IsaacTeleopConfig
    robot: RobotConfig
    reset_to_origin: bool
    reset_duration: float


@dataclass(frozen=True)
class Device:
    compute: Callable[[RobotObservation | None], RobotAction | None]
    startup: Callable[[], None]
    cleanup: Callable[[], None]


def hold_action(obs: RobotObservation, motor_names: list[str]) -> dict[str, float]:
    return {f"{name}.pos": float(obs[f"{name}.pos"]) for name in motor_names}


class HoldLatch:
    def __init__(self, motor_names: list[str]):
        self._motor_names = motor_names
        self._held: dict[str, float] | None = None

    def resolve(self, action: RobotAction | None, obs: RobotObservation) -> RobotAction:
        if action is not None:
            self._held = None
            return action
        if self._held is None:
            self._held = hold_action(obs, self._motor_names)
        return self._held


def slew(
    robot,
    motor_names: list[str],
    target_fn: Callable[[], dict[str, float]],
    duration_s: float,
) -> None:
    obs = robot.get_observation()
    start = {name: float(obs[f"{name}.pos"]) for name in motor_names}
    n_steps = max(1, int(duration_s * FPS))
    for step in range(1, n_steps + 1):
        alpha = step / n_steps
        target = target_fn()
        action = {f"{name}.pos": start[name] + alpha * (target[name] - start[name]) for name in motor_names}
        robot.send_action(action)
        precise_sleep(1.0 / FPS)


def _ensure_so101_urdf() -> str:
    dest_dir = HF_LEROBOT_HOME / "robot-urdfs" / "so101"
    urdf_path = dest_dir / "so101_new_calib.urdf"
    marker = dest_dir / ".sync_complete"
    if not marker.exists():
        from huggingface_hub import sync_bucket

        sync_bucket("hf://buckets/lerobot/robot-urdfs/so101", str(dest_dir), quiet=True)
        marker.touch()
    return str(urdf_path)


def _load_reset_target(reset_pose_file: Path, motor_names: list[str]) -> dict[str, float]:
    if reset_pose_file.exists():
        saved = json.loads(reset_pose_file.read_text())
        return {name: float(saved.get(name, RESET_ORIGIN_DEG.get(name.removeprefix("left_").removeprefix("right_"), 0.0))) for name in motor_names}
    out = {}
    for name in motor_names:
        bare = name.removeprefix("left_").removeprefix("right_")
        out[name] = RESET_ORIGIN_DEG.get(bare, 0.0)
    return out


_CLOUDXR_WEB_CLIENT_URL = "https://nvidia.github.io/IsaacTeleop/client"
_CLOUDXR_WSS_PORT = 48322
_XR_CONNECT_REMINDER_S = 15.0
_SKIP_IFACE_PREFIXES = ("docker", "br-", "veth", "virbr", "l4tbr")


def _primary_ipv4() -> str | None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return None


def _candidate_ipv4s() -> list[tuple[str, str]]:
    primary = _primary_ipv4()
    found: list[tuple[str, str]] = []
    try:
        import psutil

        for iface, addrs in psutil.net_if_addrs().items():
            if iface.startswith(_SKIP_IFACE_PREFIXES):
                continue
            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue
                ip = addr.address
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                found.append((iface, ip))
    except Exception:
        if primary:
            found.append(("default", primary))
    found.sort(key=lambda t: t[1] != primary)
    return found


def _print_xr_connect_help() -> None:
    ips = _candidate_ipv4s()
    print("\n" + "=" * 76)
    print("Connect your Quest headset to this workstation over NVIDIA CloudXR:")
    print(f"  1. In the headset, open:  {_CLOUDXR_WEB_CLIENT_URL}")
    print("  2. Enter this workstation's IP:")
    if ips:
        for iface, ip in ips:
            print(f"        {ip:<15}  ({iface})")
        if len(ips) > 1:
            print("     (use the address on the same network as your headset)")
    else:
        print("        <could not determine — check `hostname -I` / `ip addr`>")
    print(f"  3. Accept the self-signed cert at https://<ip>:{_CLOUDXR_WSS_PORT}/ , then Connect.")
    print("=" * 76 + "\n")


def _wait_for_xr_controller(teleop_device: BiXRController) -> None:
    _print_xr_connect_help()
    print("Waiting for headset controllers…  (Ctrl-C to abort)")
    last_reminder = time.time()
    while True:
        teleop_device.get_action()
        if teleop_device.is_tracking:
            print("Headset connected — at least one controller is streaming.")
            return
        if time.time() - last_reminder >= _XR_CONNECT_REMINDER_S:
            print("…still waiting for the headset to connect (Ctrl-C to abort).")
            last_reminder = time.time()
        time.sleep(1.0 / FPS)


def _arm_joint_obs(robot_obs: RobotObservation, side: str) -> RobotObservation:
    """Strip ``{side}_`` prefix and keep only that arm's ``*.pos`` joints (IK-safe)."""
    prefix = f"{side}_"
    out: RobotObservation = {}
    for name in ARM_MOTOR_NAMES:
        key = f"{prefix}{name}.pos"
        if key not in robot_obs:
            raise KeyError(f"Missing observation key {key!r}")
        out[f"{name}.pos"] = robot_obs[key]
    return out


def _prefix_action(action: RobotAction, side: str) -> RobotAction:
    return {f"{side}_{k}": v for k, v in action.items()}


def _make_arm_pipeline(kinematics_solver: RobotKinematics) -> RobotProcessorPipeline:
    return RobotProcessorPipeline[tuple[RobotAction, RobotObservation], RobotAction](
        steps=[
            MapXRControllerActionToRobotAction(),
            EEBoundsAndSafety(
                end_effector_bounds={"min": [-1.0, -1.0, 0.0], "max": [1.0, 1.0, 1.0]},
                max_ee_step_m=MAX_EE_STEP_M,
                raise_on_jump=False,
            ),
            InverseKinematicsEEToJoints(
                kinematics=kinematics_solver,
                motor_names=list(ARM_MOTOR_NAMES),
                initial_guess_current_joints=False,
                orientation_weight=IK_ORIENTATION_WEIGHT,
            ),
        ],
        to_transition=robot_action_observation_to_transition,
        to_output=transition_to_robot_action,
    )


def setup_bi_xr(cfg: LoopConfig, robot, motor_names: list[str]) -> Device:
    """Bimanual XR device: independent clutch + IK per arm, one CloudXR session."""
    urdf = _ensure_so101_urdf()
    kin_left = RobotKinematics(urdf_path=urdf, target_frame_name="gripper_frame_link", joint_names=list(ARM_MOTOR_NAMES))
    kin_right = RobotKinematics(urdf_path=urdf, target_frame_name="gripper_frame_link", joint_names=list(ARM_MOTOR_NAMES))
    pipe_left = _make_arm_pipeline(kin_left)
    pipe_right = _make_arm_pipeline(kin_right)

    if not isinstance(cfg.teleop, BiXRControllerConfig):
        raise TypeError(f"Expected BiXRControllerConfig, got {type(cfg.teleop).__name__}")
    teleop_config: BiXRControllerConfig = cfg.teleop
    teleop_device = BiXRController(teleop_config)

    clutch_left: Clutch | None = None
    clutch_right: Clutch | None = None
    prev_enabled = {"left": False, "right": False}

    def startup() -> None:
        nonlocal clutch_left, clutch_right
        teleop_device.connect()
        if not teleop_device.is_connected:
            raise ValueError("Teleop is not connected!")
        _wait_for_xr_controller(teleop_device)

        if cfg.reset_to_origin:
            reset_pose_file = Path(RESET_POSE_FILE.format(robot_name=robot.name, robot_id=robot.id))
            target = _load_reset_target(reset_pose_file, motor_names)
            source = str(reset_pose_file) if reset_pose_file.exists() else "hardcoded defaults"
            print(f"Reset target source: {source}")
            print(f"Resetting both arms over {cfg.reset_duration:.1f} s…")
            slew(robot, motor_names, lambda: target, cfg.reset_duration)
            print("Reset complete.")

        obs0 = robot.get_observation()
        q_left = np.array([float(obs0[f"left_{n}.pos"]) for n in ARM_MOTOR_NAMES], dtype=float)
        q_right = np.array([float(obs0[f"right_{n}.pos"]) for n in ARM_MOTOR_NAMES], dtype=float)
        clutch_left = Clutch(kin_left.forward_kinematics(q_left))
        clutch_right = Clutch(kin_right.forward_kinematics(q_right))
        print("Starting bimanual teleop. Squeeze each controller grip to engage that arm…")

    def _solve_arm(
        side: str,
        *,
        grip_pos,
        grip_quat,
        squeeze: float,
        trigger: float,
        robot_obs: RobotObservation,
        clutch: Clutch,
        kin: RobotKinematics,
        pipe: RobotProcessorPipeline,
    ) -> RobotAction | None:
        enabled = squeeze > teleop_config.clutch_threshold
        is_engage = enabled and not prev_enabled[side]
        if is_engage:
            arm_obs = _arm_joint_obs(robot_obs, side)
            q = np.array([float(arm_obs[f"{n}.pos"]) for n in ARM_MOTOR_NAMES], dtype=float)
            clutch.engage(grip_pos, grip_quat, measured_base_T_ee=kin.forward_kinematics(q))
            pipe.reset()
        prev_enabled[side] = enabled
        if not enabled:
            return None
        ee_pos, ee_quat = clutch.rebase(grip_pos, grip_quat)
        ee_action = {
            "ee_pose": np.concatenate([ee_pos, ee_quat]).astype(np.float32),
            "closedness": trigger,
        }
        arm_obs = _arm_joint_obs(robot_obs, side)
        bare = pipe((ee_action, arm_obs))
        return _prefix_action(bare, side)

    def compute(robot_obs: RobotObservation | None) -> RobotAction | None:
        if clutch_left is None or clutch_right is None:
            raise RuntimeError("compute() called before startup()")
        xr = teleop_device.get_action()
        left_action = _solve_arm(
            "left",
            grip_pos=np.asarray(xr["left_grip_pos"], dtype=float),
            grip_quat=np.asarray(xr["left_grip_quat"], dtype=float),
            squeeze=float(xr["left_squeeze"]),
            trigger=float(xr["left_trigger"]),
            robot_obs=robot_obs,
            clutch=clutch_left,
            kin=kin_left,
            pipe=pipe_left,
        )
        right_action = _solve_arm(
            "right",
            grip_pos=np.asarray(xr["right_grip_pos"], dtype=float),
            grip_quat=np.asarray(xr["right_grip_quat"], dtype=float),
            squeeze=float(xr["right_squeeze"]),
            trigger=float(xr["right_trigger"]),
            robot_obs=robot_obs,
            clutch=clutch_right,
            kin=kin_right,
            pipe=pipe_right,
        )
        if left_action is None and right_action is None:
            return None
        merged: RobotAction = {}
        if left_action is not None:
            merged.update(left_action)
        else:
            merged.update({f"left_{n}.pos": float(robot_obs[f"left_{n}.pos"]) for n in ARM_MOTOR_NAMES})
        if right_action is not None:
            merged.update(right_action)
        else:
            merged.update({f"right_{n}.pos": float(robot_obs[f"right_{n}.pos"]) for n in ARM_MOTOR_NAMES})
        return merged

    return Device(compute=compute, startup=startup, cleanup=teleop_device.disconnect)


def build_device(cfg: LoopConfig) -> tuple:
    if cfg.teleop.cloudxr_env_file is None:
        cfg.teleop.cloudxr_env_file = CLOUDXR_ENV_FILE

    if cfg.robot.type != "bi_so_follower":
        raise ValueError(
            f"This package expects --robot.type=bi_so_follower, got --robot.type={cfg.robot.type}."
        )
    if not isinstance(cfg.teleop, BiXRControllerConfig):
        raise ValueError(
            "Use --teleop.type=bi_xr_controller (physical SO-101 leader is out of scope for this package)."
        )

    robot = make_robot_from_config(cfg.robot)
    robot.connect()
    device: Device | None = None
    try:
        motor_names = [key.removesuffix(".pos") for key in robot.action_features if key.endswith(".pos")]
        device = setup_bi_xr(cfg, robot, motor_names)
        device.startup()
    except BaseException:
        if device is not None:
            with suppress(Exception):
                device.cleanup()
        robot.disconnect()
        raise
    return robot, device, motor_names


def init_keyboard_listener():
    if not (sys.stdin is not None and sys.stdin.isatty()):
        from lerobot.utils.keyboard_input import init_keyboard_listener as _upstream

        return _upstream()

    from lerobot.utils.keyboard_input import TerminalKeyListener, apply_recording_control

    events = {"exit_early": False, "rerecord_episode": False, "stop_recording": False}

    def on_key(name: str) -> None:
        key = name.lower()
        if key in ("right", "n"):
            apply_recording_control("right", events)
        elif key in ("left", "r"):
            apply_recording_control("left", events)
        elif key in ("esc", "q"):
            apply_recording_control("esc", events)

    listener = TerminalKeyListener(on_key)
    listener.start()
    logging.info(
        "Keyboard control via terminal — keep this terminal focused: "
        "Right/n = end episode early, Left/r = re-record, Esc/q = stop."
    )
    return listener, events
