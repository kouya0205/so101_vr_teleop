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
python -m isaacteleop.cloudxr --accept-eula   # once (interactive EULA)
```

Firewall (CloudXR / Quest): allow UDP `47998` and TCP `49100,48322` (see [Isaac Teleop Quick Start](https://nvidia.github.io/IsaacTeleop/main/getting_started/quick_start.html)).

### Find arm serial ports

```bash
ls -l /dev/serial/by-id/
# or
ls /dev/ttyACM* /dev/ttyUSB*
python -m serial.tools.list_ports -v
```

Unplug one arm and re-list to map left vs right. Prefer stable `by-id` paths when possible.

## Configure

Always activate the venv first (`opencv` / `so101-vr-*` live there):

```bash
source .venv/bin/activate
cp configs/robot.example.env configs/robot.env
cp configs/cameras.example.json configs/cameras.json
# edit ports in configs/robot.env
python scripts/find_cameras.py --write configs/cameras.json
# edit index_or_path in configs/cameras.json to match mounts
python scripts/check_env.py
```

**Every new terminal:**

```bash
source .venv/bin/activate
set -a && source configs/robot.env && set +a
export SO101_CAMERAS_JSON="$PWD/configs/cameras.json"
echo "L=$SO101_LEFT_PORT R=$SO101_RIGHT_PORT"   # must not be empty
```

If ports print empty, teleop fails with `Could not connect on port ''`.

### Camera layout

Camera USB mapping is **only** in [`configs/cameras.json`](configs/cameras.json) (`index_or_path` per key).

| Key | Role |
|-----|------|
| `left_wrist` | Left arm wrist cam |
| `right_wrist` | Right arm wrist cam |
| `side` | Fixed side view of the workspace (**facing the arms**, not from behind them) |
| `front` | Fixed front / slightly top-down view from the **opposite** side of the dual-arm mount |

## Teleoperate

### CloudXR: do not start it twice

`python -m isaacteleop.cloudxr --accept-eula` leaves CloudXR running and binds TCP **49100**. Starting teleop without skipping auto-launch then fails with `Port 49100 is already in use`.

**Option A — reuse the already-running CloudXR (recommended if you accepted EULA in another terminal):**

```bash
export LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH=1
source ~/.cloudxr/run/cloudxr.env
```

**Option B — let teleop launch CloudXR:** stop the other process first (`Ctrl-C` in that terminal, or `pkill -f 'isaacteleop.cloudxr'`), then run teleop **without** `LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH`.

```bash
so101-vr-teleop \
  --robot.type=bi_so_follower \
  --robot.id="${SO101_ROBOT_ID:-bi_so101}" \
  --robot.left_arm_config.port="${SO101_LEFT_PORT}" \
  --robot.right_arm_config.port="${SO101_RIGHT_PORT}" \
  --teleop.type=bi_xr_controller
```

### Quest connection

1. On the headset open the CloudXR client (versioned URL from the `isaacteleop.cloudxr` banner, or https://nvidia.github.io/IsaacTeleop/client ).
2. **Server IP** = this PC’s LAN address on the **same Wi‑Fi** as the Quest (`hostname -I`; use `10.x` / `192.168.x`, not Docker `172.17.0.1`).
3. Accept the self-signed cert at `https://<that-ip>:48322/` , then Connect.
4. When teleop prints `Starting bimanual teleop…`: **squeeze grip** to engage each arm; **trigger** = gripper. Release grip to freeze that arm.

First connect may run interactive joint calibration per arm and save under `~/.cache/huggingface/lerobot/calibration/`.

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

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `opencv-python is required` from `find_cameras.py` | System Python, not venv | `source .venv/bin/activate` then re-run |
| `Could not connect on port ''` | `SO101_*_PORT` unset in this shell | `set -a && source configs/robot.env && set +a` |
| `Port 49100 is already in use` | Second CloudXR launch | Reuse: `export LEROBOT_CLOUDXR_SKIP_AUTOLAUNCH=1` + `source ~/.cloudxr/run/cloudxr.env`, or kill the other CloudXR |
| Headset waits forever | Wrong IP / cert / Wi‑Fi | Same LAN; cert on `:48322`; avoid Docker IP |
| Arms do not move after “Starting bimanual teleop” | Clutch not engaged | Hold **grip** past threshold (~0.5); check controller tracking |

Placo “self collisions in neutral position” warnings on SO-101 URDF are common and usually **not** fatal.

## Override reset pose

Torque off, pose both arms, then:

```bash
so101-vr-override-reset --left-port "$SO101_LEFT_PORT" --right-port "$SO101_RIGHT_PORT" --id "$SO101_ROBOT_ID"
```

## License

Apache License 2.0. See [`LICENSE`](LICENSE).

This repository includes code adapted from the LeRobot Isaac Teleop → SO-101 example (copyright NVIDIA Corporation and The HuggingFace Inc. team), also under Apache-2.0. Keep upstream copyright headers in those files. Runtime dependency `isaacteleop` is subject to its own NVIDIA package terms.

## References

- [LeRobot Isaac Teleop](https://huggingface.co/docs/lerobot/isaac_teleop)
- [Isaac Teleop system requirements](https://nvidia.github.io/IsaacTeleop/main/references/requirements.html)
- Upstream example: `examples/isaac_teleop_to_so101` in [huggingface/lerobot](https://github.com/huggingface/lerobot)
