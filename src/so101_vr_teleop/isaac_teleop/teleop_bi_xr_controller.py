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

"""Bimanual XR controller device: left + right grips in one TeleopSession."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from lerobot.types import RobotAction

from .base import IsaacTeleopTeleoperator, _isaacteleop_available
from .config_isaac_teleop import BiXRControllerConfig

if TYPE_CHECKING or _isaacteleop_available:
    from isaacteleop.retargeting_engine.deviceio_source_nodes import ControllersSource
    from isaacteleop.retargeting_engine.interface import OutputCombiner, TensorGroup, ValueInput
    from isaacteleop.retargeting_engine.tensor_types import TransformMatrix
    from isaacteleop.retargeting_engine.tensor_types.indices import ControllerInputIndex
else:
    ControllersSource = None
    OutputCombiner = None
    TensorGroup = None
    ValueInput = None
    TransformMatrix = None
    ControllerInputIndex = None

_LEFT_ANCHOR = "base_T_anchor_left"
_RIGHT_ANCHOR = "base_T_anchor_right"


class BiXRController(IsaacTeleopTeleoperator):
    """Raw left/right XR grip poses in each arm's base frame (no clutch)."""

    config_class = BiXRControllerConfig
    name = "isaac_teleop_bi_xr_controller"

    def __init__(self, config: BiXRControllerConfig):
        super().__init__(config)
        self.config: BiXRControllerConfig = config
        self._external_inputs: dict[str, Any] | None = None
        self._is_tracking_left = False
        self._is_tracking_right = False

    def _build_pipeline(self) -> OutputCombiner:
        controllers = ControllersSource(name="controllers")
        xform_l = ValueInput(_LEFT_ANCHOR, TransformMatrix())
        xform_r = ValueInput(_RIGHT_ANCHOR, TransformMatrix())
        left = controllers.transformed(xform_l.output("value")).output("controller_left")
        right = controllers.transformed(xform_r.output("value")).output("controller_right")
        return OutputCombiner({"controller_left": left, "controller_right": right})

    def _build_external_inputs(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, mat in (
            (_LEFT_ANCHOR, self.config.left_base_T_anchor),
            (_RIGHT_ANCHOR, self.config.right_base_T_anchor),
        ):
            tg = TensorGroup(TransformMatrix())
            tg[0] = np.asarray(mat, dtype=np.float32)
            out[name] = {"value": tg}
        return out

    def connect(self, calibrate: bool = True) -> None:
        super().connect(calibrate=calibrate)
        try:
            self._external_inputs = self._build_external_inputs()
        except Exception:
            self.disconnect()
            raise

    @property
    def action_features(self) -> dict:
        feat = {
            "grip_pos": {"dtype": "float32", "shape": (3,), "names": {"x": 0, "y": 1, "z": 2}},
            "grip_quat": {
                "dtype": "float32",
                "shape": (4,),
                "names": {"qx": 0, "qy": 1, "qz": 2, "qw": 3},
            },
            "squeeze": {"dtype": "float32", "shape": (), "names": None},
            "trigger": {"dtype": "float32", "shape": (), "names": None},
        }
        out = {}
        for side in ("left", "right"):
            for k, v in feat.items():
                out[f"{side}_{k}"] = v
        return out

    @property
    def feedback_features(self) -> dict:
        return {}

    @property
    def is_tracking(self) -> bool:
        """True when at least one controller was tracked on the last step."""
        return self._is_tracking_left or self._is_tracking_right

    @property
    def is_tracking_both(self) -> bool:
        return self._is_tracking_left and self._is_tracking_right

    def _read_controller(self, controller) -> tuple[bool, np.ndarray, np.ndarray, float, float]:
        grip_pos = np.zeros(3, dtype=np.float32)
        grip_quat = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        squeeze = 0.0
        trigger = 0.0
        tracking = not getattr(controller, "is_none", False)
        if not tracking:
            return False, grip_pos, grip_quat, squeeze, trigger
        try:
            pos = np.asarray(controller[ControllerInputIndex.GRIP_POSITION], dtype=np.float32)
            quat = np.asarray(controller[ControllerInputIndex.GRIP_ORIENTATION], dtype=np.float32)
            squeeze_val = float(controller[ControllerInputIndex.SQUEEZE_VALUE])
            trigger_val = float(controller[ControllerInputIndex.TRIGGER_VALUE])
        except (IndexError, KeyError, TypeError, ValueError):
            return False, grip_pos, grip_quat, squeeze, trigger
        return True, pos, quat, squeeze_val, trigger_val

    def get_action(self) -> RobotAction:
        result = self._step(execution_events=self._running_events(), external_inputs=self._external_inputs)

        left_ok, lpos, lquat, lsq, ltr = self._read_controller(result["controller_left"])
        right_ok, rpos, rquat, rsq, rtr = self._read_controller(result["controller_right"])
        self._is_tracking_left = left_ok
        self._is_tracking_right = right_ok

        return {
            "left_grip_pos": lpos,
            "left_grip_quat": lquat,
            "left_squeeze": lsq,
            "left_trigger": ltr,
            "right_grip_pos": rpos,
            "right_grip_quat": rquat,
            "right_squeeze": rsq,
            "right_trigger": rtr,
        }
