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

"""Configuration dataclasses for NVIDIA Isaac Teleop-backed teleoperators.

Adapted from LeRobot ``examples/isaac_teleop_to_so101`` for bimanual SO-101 VR teleop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from lerobot.teleoperators.config import TeleoperatorConfig


@dataclass(kw_only=True)
class IsaacTeleopConfig(TeleoperatorConfig):
    """Shared config for all Isaac Teleop-backed teleoperators in this package."""

    _choice_registry: ClassVar[dict] = {}

    app_name: str = "SO101VRTeleop"
    """Application name for the OpenXR / Isaac Teleop session."""

    auto_launch_cloudxr: bool = True
    """Auto-launch the CloudXR runtime on connect. Set False (or export
    ``LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH=1``) when CloudXR runs externally.
    """

    cloudxr_env_file: str | None = None
    """Optional CloudXR device-profile ``.env`` passed to ``CloudXRLauncher``."""


# OpenXR (X=Right, Y=Up, Z=Backward) -> robot base (X=Forward, Y=Left, Z=Up).
_DEFAULT_BASE_T_ANCHOR: list[list[float]] = [
    [0.0, 0.0, -1.0, 0.0],
    [-1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


def _copy_anchor() -> list[list[float]]:
    return [row.copy() for row in _DEFAULT_BASE_T_ANCHOR]


@IsaacTeleopConfig.register_subclass("xr_controller")
@dataclass(kw_only=True)
class XRControllerConfig(IsaacTeleopConfig):
    """Single-hand XR controller (kept for debugging; prefer ``bi_xr_controller``)."""

    hand_side: str = "right"
    clutch_threshold: float = 0.5
    base_T_anchor: list[list[float]] = field(default_factory=_copy_anchor)  # noqa: N815

    def __post_init__(self):
        if self.hand_side not in ("left", "right"):
            raise ValueError(f"hand_side must be 'left' or 'right', got {self.hand_side!r}")


@IsaacTeleopConfig.register_subclass("bi_xr_controller")
@dataclass(kw_only=True)
class BiXRControllerConfig(IsaacTeleopConfig):
    """Bimanual XR controllers (left + right) in one Isaac Teleop session."""

    clutch_threshold: float = 0.5
    """Squeeze value above which each arm's clutch engages (independent per hand)."""

    left_base_T_anchor: list[list[float]] = field(default_factory=_copy_anchor)  # noqa: N815
    """4x4 OpenXR-anchor -> left arm base frame."""

    right_base_T_anchor: list[list[float]] = field(default_factory=_copy_anchor)  # noqa: N815
    """4x4 OpenXR-anchor -> right arm base frame."""
