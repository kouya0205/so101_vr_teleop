#!/usr/bin/env bash
# Smoke-test VR teleop (no dataset). Practice clutch / motion before recording.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/env.sh"

echo
echo "Quest: open CloudXR client, enter THIS PC LAN IP, accept :48322 cert, Connect."
echo "Controls: grip=engage arm, trigger=gripper. Ctrl-C to stop."
echo

exec so101-vr-teleop \
  --robot.type=bi_so_follower \
  --robot.id="${SO101_ROBOT_ID}" \
  --robot.left_arm_config.port="${SO101_LEFT_PORT}" \
  --robot.right_arm_config.port="${SO101_RIGHT_PORT}" \
  --teleop.type=bi_xr_controller \
  "$@"
