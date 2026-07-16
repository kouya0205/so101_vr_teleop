#!/usr/bin/env bash
# Bootstrap a local venv and install so101-vr-teleop (+ CloudXR EULA hint).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if [[ ! -d .venv ]]; then
  uv venv --python 3.12 .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing package (this may take a while)…"
uv pip install -e ".[teleop]"

echo
echo "One-time CloudXR EULA (interactive):"
echo "  python -m isaacteleop.cloudxr --accept-eula"
echo
echo "Then:"
echo "  cp configs/robot.example.env configs/robot.env"
echo "  cp configs/cameras.example.json configs/cameras.json"
echo "  python scripts/find_cameras.py --write configs/cameras.json"
echo "  python scripts/check_env.py"
