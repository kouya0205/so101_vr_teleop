# SO-101 VR Teleop

Bimanual **real-robot** SO-101 teleoperation and LeRobot dataset recording with a **Meta Quest** headset, using [NVIDIA Isaac Teleop](https://huggingface.co/docs/lerobot/isaac_teleop) (LeRobot ≥ 0.6) over CloudXR.

No Isaac Lab / Isaac Sim. Physical leader arms are out of scope — **VR controllers are the leader** (poses are **not** written into the dataset).

## Requirements

| Item | Notes |
|------|--------|
| OS | Ubuntu **22.04 or 24.04** (both supported by Isaac Teleop) |
| GPU | NVIDIA GPU; Driver **≥ 580.95**; `nvidia-smi` CUDA Version **≥ 12.8** |
| Headset | Meta Quest 3 / 3S (CloudXR WebXR client) |
| Robot | Calibrated dual SO-101 followers (Feetech) |
| Cameras | `left_wrist`, `right_wrist`, `side`, `front` (scene cams opposite the arms) |
| Python | 3.10–3.13 (3.12 recommended) |

Validated reference machine: Ubuntu 24.04, Driver 580.x, CUDA capability 13.0, RTX 5080.

## Install

```bash
git clone https://github.com/kouya0205/so101_vr_teleop.git
cd so101_vr_teleop
bash scripts/bootstrap.sh
source .venv/bin/activate
python -m isaacteleop.cloudxr --accept-eula   # once
```

Firewall (CloudXR / Quest): allow UDP `47998` and TCP `49100,48322` (see [Isaac Teleop Quick Start](https://nvidia.github.io/IsaacTeleop/main/getting_started/quick_start.html)).

## Configure

```bash
cp configs/robot.example.env configs/robot.env
cp configs/cameras.example.json configs/cameras.json
# edit ports / camera indices
python scripts/find_cameras.py --write configs/cameras.json
python scripts/check_env.py
set -a && source configs/robot.env && set +a
export SO101_CAMERAS_JSON="$PWD/configs/cameras.json"
```

### Camera layout

| Key | Role |
|-----|------|
| `left_wrist` | Left arm wrist cam |
| `right_wrist` | Right arm wrist cam |
| `side` | Fixed side view of the workspace (**facing the arms**, not from behind them) |
| `front` | Fixed front / slightly top-down view from the **opposite** side of the dual-arm mount |

## Teleoperate

```bash
so101-vr-teleop \
  --robot.type=bi_so_follower \
  --robot.id="${SO101_ROBOT_ID:-bi_so101}" \
  --robot.left_arm_config.port="${SO101_LEFT_PORT}" \
  --robot.right_arm_config.port="${SO101_RIGHT_PORT}" \
  --teleop.type=bi_xr_controller
```

In the headset: open https://nvidia.github.io/IsaacTeleop/client , enter this PC’s LAN IP, accept the cert, Connect. **Squeeze grip** to engage each arm independently; **trigger** closes that gripper.

## Record a dataset

```bash
so101-vr-record \
  --robot.type=bi_so_follower \
  --robot.id="${SO101_ROBOT_ID:-bi_so101}" \
  --robot.left_arm_config.port="${SO101_LEFT_PORT}" \
  --robot.right_arm_config.port="${SO101_RIGHT_PORT}" \
  --teleop.type=bi_xr_controller \
  --task_slug="${SO101_TASK:-demo}" \
  --dataset.single_task="Pick the object with both arms" \
  --dataset.num_episodes=3 \
  --dataset.episode_time_s=30 \
  --dataset.reset_time_s=10 \
  --dataset.push_to_hub=false
```

- Auto `repo_id`: `{HF_USER}/so101_bi_{task}_v{NNN}` (next free index). **No datetime stamp** (Hub upload already carries time metadata).
- Override with `--dataset.repo_id=user/name_v042` if you want a fixed id.
- Dataset contains follower joints + cameras only (no XR poses).

Keyboard (TTY): `n` end episode, `r` re-record, `q` stop.

## Override reset pose

Torque off, pose both arms, then:

```bash
so101-vr-override-reset --left-port "$SO101_LEFT_PORT" --right-port "$SO101_RIGHT_PORT" --id "$SO101_ROBOT_ID"
```

## License

TBD (upstream LeRobot / Isaac Teleop example code retains NVIDIA & Hugging Face Apache-2.0 headers).

## References

- [LeRobot Isaac Teleop](https://huggingface.co/docs/lerobot/isaac_teleop)
- [Isaac Teleop system requirements](https://nvidia.github.io/IsaacTeleop/main/references/requirements.html)
- Upstream example: `examples/isaac_teleop_to_so101` in [huggingface/lerobot](https://github.com/huggingface/lerobot)
