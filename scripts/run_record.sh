#!/usr/bin/env bash
# Record LeRobot dataset via bimanual SO-101 + Quest XR.
#
# Usage:
#   ./scripts/run_record.sh
#   SO101_TASK=pick SO101_NUM_EPISODES=20 ./scripts/run_record.sh
#   ./scripts/run_record.sh --dataset.num_episodes=5   # extra CLI overrides
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/env.sh"

if [[ ! -f "$SO101_CAMERAS_JSON" ]]; then
  echo "ERROR: configs/cameras.json required for data collection." >&2
  exit 1
fi

SINGLE_TASK="${SO101_SINGLE_TASK:-Teleoperate bimanual SO-101: ${SO101_TASK}}"
NUM_EPISODES="${SO101_NUM_EPISODES:-10}"
EPISODE_TIME_S="${SO101_EPISODE_TIME_S:-40}"
RESET_TIME_S="${SO101_RESET_TIME_S:-15}"
PUSH_TO_HUB="${SO101_PUSH_TO_HUB:-false}"
FPS="${SO101_DATASET_FPS:-30}"

echo
echo "========== DATA COLLECTION =========="
echo "  task_slug:     $SO101_TASK"
echo "  single_task:   $SINGLE_TASK"
echo "  episodes:      $NUM_EPISODES"
echo "  episode_time:  ${EPISODE_TIME_S}s"
echo "  reset_time:    ${RESET_TIME_S}s"
echo "  fps:           $FPS"
echo "  push_to_hub:   $PUSH_TO_HUB"
echo "  repo_id:       auto {HF_USER}/so101_bi_${SO101_TASK}_vNNN"
echo "Keyboard: n=end episode  r=re-record  q=stop"
echo "====================================="
echo

exec so101-vr-record \
  --robot.type=bi_so_follower \
  --robot.id="${SO101_ROBOT_ID}" \
  --robot.left_arm_config.port="${SO101_LEFT_PORT}" \
  --robot.right_arm_config.port="${SO101_RIGHT_PORT}" \
  --teleop.type=bi_xr_controller \
  --task_slug="${SO101_TASK}" \
  --dataset.single_task="${SINGLE_TASK}" \
  --dataset.num_episodes="${NUM_EPISODES}" \
  --dataset.episode_time_s="${EPISODE_TIME_S}" \
  --dataset.reset_time_s="${RESET_TIME_S}" \
  --dataset.fps="${FPS}" \
  --dataset.push_to_hub="${PUSH_TO_HUB}" \
  "$@"
