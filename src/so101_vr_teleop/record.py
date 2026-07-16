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

"""Record a LeRobot dataset via bimanual SO-101 + Quest XR (Isaac Teleop).

VR controller poses are **not** stored — only follower joints + cameras.

Dataset naming uses ``{HF_USER}/so101_bi_{task}_v{NNN}`` (no datetime stamp).
Pass ``--dataset.repo_id=...`` to override; we intentionally skip
``DatasetRecordConfig.stamp_repo_id()`` to avoid double-dating with Hub uploads.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pprint import pformat

from lerobot.cameras import CameraConfig  # noqa: F401
from lerobot.cameras.opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.common.control_utils import sanity_check_dataset_robot_compatibility
from lerobot.configs import parser
from lerobot.configs.dataset import DatasetRecordConfig
from lerobot.datasets import (
    LeRobotDataset,
    VideoEncodingManager,
    aggregate_pipeline_dataset_features,
    create_initial_features,
    safe_stop_image_writer,
)
from lerobot.processor import make_default_processors
from lerobot.robots import RobotConfig
from lerobot.robots.bi_so_follower import BiSOFollowerConfig  # noqa: F401
from lerobot.robots.so_follower import SOFollowerConfig  # noqa: F401
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.feature_utils import build_dataset_frame, combine_feature_dicts
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import init_logging

from .common import RESET_DURATION_S, Device, HoldLatch, build_device, init_keyboard_listener
from .dataset_naming import next_versioned_repo_id
from .isaac_teleop import IsaacTeleopConfig
from .teleoperate import _maybe_load_cameras


@dataclass
class RecordConfig:
    robot: RobotConfig
    teleop: IsaacTeleopConfig
    dataset: DatasetRecordConfig = field(default_factory=DatasetRecordConfig)

    reset_to_origin: bool = True
    reset_duration: float = RESET_DURATION_S
    resume: bool = False
    # Task slug for auto repo_id when dataset.repo_id is empty.
    task_slug: str = "demo"


@safe_stop_image_writer
def _record_loop(
    robot,
    device: Device,
    motor_names: list[str],
    events: dict,
    fps: int,
    dataset: LeRobotDataset | None = None,
    control_time_s: float = 0.0,
    single_task: str | None = None,
) -> None:
    control_interval = 1.0 / fps
    timestamp = 0.0
    start_t = time.perf_counter()
    record_frames = dataset is not None
    hold = HoldLatch(motor_names)

    while timestamp < control_time_s:
        loop_start = time.perf_counter()

        if events["exit_early"]:
            events["exit_early"] = False
            break

        obs = robot.get_observation()

        if record_frames:
            observation_frame = build_dataset_frame(dataset.features, obs, prefix=OBS_STR)

        action = hold.resolve(device.compute(obs), obs)
        robot.send_action(action)

        if record_frames:
            action_frame = build_dataset_frame(dataset.features, action, prefix=ACTION)
            dataset.add_frame({**observation_frame, **action_frame, "task": single_task})

        dt_s = time.perf_counter() - loop_start
        precise_sleep(max(control_interval - dt_s, 0.0))
        timestamp = time.perf_counter() - start_t


@parser.wrap()
def record(cfg: RecordConfig) -> LeRobotDataset:
    init_logging()
    _maybe_load_cameras(cfg.robot)

    # Versioned repo_id without datetime stamp (skip stamp_repo_id).
    if not cfg.resume:
        explicit = cfg.dataset.repo_id.strip() or None
        cfg.dataset.repo_id = next_versioned_repo_id(
            task=cfg.task_slug or os.environ.get("SO101_TASK", "demo"),
            explicit_repo_id=explicit,
        )
        logging.info("Dataset repo_id=%s", cfg.dataset.repo_id)

    logging.info(pformat(asdict(cfg)))

    robot, device, motor_names = build_device(cfg)

    teleop_proc, _, obs_proc = make_default_processors()
    dataset_features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=teleop_proc,
            initial_features=create_initial_features(action=robot.action_features),
            use_videos=cfg.dataset.video,
        ),
        aggregate_pipeline_dataset_features(
            pipeline=obs_proc,
            initial_features=create_initial_features(observation=robot.observation_features),
            use_videos=cfg.dataset.video,
        ),
    )

    num_cameras = len(robot.cameras) if hasattr(robot, "cameras") else 0
    image_writer_threads = cfg.dataset.num_image_writer_threads_per_camera * num_cameras

    dataset: LeRobotDataset | None = None
    listener = None
    try:
        if cfg.resume:
            dataset = LeRobotDataset.resume(
                cfg.dataset.repo_id,
                root=cfg.dataset.root,
                batch_encoding_size=cfg.dataset.video_encoding_batch_size,
                rgb_encoder=cfg.dataset.rgb_encoder,
                depth_encoder=cfg.dataset.depth_encoder,
                encoder_threads=cfg.dataset.encoder_threads,
                streaming_encoding=cfg.dataset.streaming_encoding,
                encoder_queue_maxsize=cfg.dataset.encoder_queue_maxsize,
                image_writer_processes=cfg.dataset.num_image_writer_processes if num_cameras > 0 else 0,
                image_writer_threads=image_writer_threads if num_cameras > 0 else 0,
            )
            sanity_check_dataset_robot_compatibility(dataset, robot, cfg.dataset.fps, dataset_features)
        else:
            dataset = LeRobotDataset.create(
                cfg.dataset.repo_id,
                cfg.dataset.fps,
                root=cfg.dataset.root,
                robot_type=robot.name,
                features=dataset_features,
                use_videos=cfg.dataset.video,
                image_writer_processes=cfg.dataset.num_image_writer_processes,
                image_writer_threads=image_writer_threads,
                batch_encoding_size=cfg.dataset.video_encoding_batch_size,
                rgb_encoder=cfg.dataset.rgb_encoder,
                depth_encoder=cfg.dataset.depth_encoder,
                encoder_threads=cfg.dataset.encoder_threads,
                streaming_encoding=cfg.dataset.streaming_encoding,
                encoder_queue_maxsize=cfg.dataset.encoder_queue_maxsize,
            )

        listener, events = init_keyboard_listener()

        loop_kwargs = {
            "robot": robot,
            "device": device,
            "motor_names": motor_names,
            "events": events,
            "fps": cfg.dataset.fps,
            "single_task": cfg.dataset.single_task,
        }

        with VideoEncodingManager(dataset):
            recorded_episodes = 0
            while recorded_episodes < cfg.dataset.num_episodes and not events["stop_recording"]:
                logging.info(f"Recording episode {dataset.num_episodes}")
                _record_loop(
                    **loop_kwargs,
                    dataset=dataset,
                    control_time_s=cfg.dataset.episode_time_s,
                )

                if not events["stop_recording"] and (
                    recorded_episodes < cfg.dataset.num_episodes - 1 or events["rerecord_episode"]
                ):
                    logging.info("Reset the environment")
                    _record_loop(
                        **loop_kwargs,
                        dataset=None,
                        control_time_s=cfg.dataset.reset_time_s,
                    )

                if events["rerecord_episode"]:
                    logging.info("Re-record episode")
                    events["rerecord_episode"] = False
                    events["exit_early"] = False
                    dataset.clear_episode_buffer()
                    continue

                dataset.save_episode()
                recorded_episodes += 1

    finally:
        logging.info("Stop recording")
        try:
            device.cleanup()
        except Exception:
            logging.exception("Device cleanup failed")
        try:
            if robot.is_connected:
                robot.disconnect()
        except Exception:
            logging.exception("Robot disconnect failed")

        if listener is not None:
            try:
                listener.stop()
            except Exception:
                logging.exception("Keyboard listener stop failed")

        if dataset is not None:
            dataset.finalize()

        if cfg.dataset.push_to_hub:
            if dataset is not None and dataset.num_episodes > 0:
                dataset.push_to_hub(tags=cfg.dataset.tags, private=cfg.dataset.private)
            else:
                logging.warning("No episodes saved — skipping push to hub")

        logging.info("Exiting")

    return dataset


def main():
    record()


if __name__ == "__main__":
    main()
