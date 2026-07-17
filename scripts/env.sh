#!/usr/bin/env bash
# Shared environment for teleop / record. Source from repo root:
#   source scripts/env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ ! -f configs/robot.env ]]; then
  echo "Missing configs/robot.env — copy from configs/robot.example.env and edit ports." >&2
  return 1 2>/dev/null || exit 1
fi
# shellcheck disable=SC1091
set -a && source configs/robot.env && set +a

if [[ -f configs/record.env ]]; then
  # shellcheck disable=SC1091
  set -a && source configs/record.env && set +a
fi

export SO101_CAMERAS_JSON="${SO101_CAMERAS_JSON:-$ROOT/configs/cameras.json}"
if [[ ! -f "$SO101_CAMERAS_JSON" ]]; then
  echo "WARNING: cameras file not found: $SO101_CAMERAS_JSON" >&2
  echo "  cp configs/cameras.example.json configs/cameras.json && edit indices" >&2
fi

# Reuse CloudXR if already running (avoids port 49100 conflict).
export LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH="${LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH:-1}"
if [[ "${LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH}" == "1" ]]; then
  if [[ -f "${HOME}/.cloudxr/run/cloudxr.env" ]]; then
    # shellcheck disable=SC1091
    source "${HOME}/.cloudxr/run/cloudxr.env"
  else
    echo "WARNING: LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH=1 but ~/.cloudxr/run/cloudxr.env missing." >&2
    echo "  Start once: python -m isaacteleop.cloudxr --accept-eula" >&2
  fi
fi

: "${SO101_LEFT_PORT:?SO101_LEFT_PORT empty — check configs/robot.env}"
: "${SO101_RIGHT_PORT:?SO101_RIGHT_PORT empty — check configs/robot.env}"
: "${SO101_ROBOT_ID:=bi_so101}"
: "${SO101_TASK:=demo}"
: "${HF_USER:=local}"

echo "env ready:"
echo "  robot.id=$SO101_ROBOT_ID"
echo "  left=$SO101_LEFT_PORT  right=$SO101_RIGHT_PORT"
echo "  cameras=$SO101_CAMERAS_JSON"
echo "  task=$SO101_TASK  HF_USER=$HF_USER"
echo "  CLOUDXR_SKIP=$LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH"
