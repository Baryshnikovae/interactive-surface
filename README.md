# Interactive Surface

**Event test version 0.4.1: calibration, physical-object recognition, and ball game.**

**Windows event setup (operate with the laptop lid closed from a phone):** [WINDOWS_EVENT_SETUP.md](WINDOWS_EVENT_SETUP.md). The optional [prepare-event-windows.bat](prepare-event-windows.bat) configures AC lid/sleep and a Private-only LAN firewall rule; read the guide before running it as administrator.

**Вся актуальная версия находится в `main`. Не нужно искать или переключать ветки.**

Local operator UI for camera/projector calibration, colour recognition and the **«Шарики и лунка»** game. Old project: [virtual_wall_balls](https://github.com/Baryshnikovae/virtual_wall_balls).

## Быстрый старт — всегда из `main`

**Windows (Command Prompt):**

```cmd
cd /d "%USERPROFILE%"
git clone https://github.com/Baryshnikovae/interactive-surface.git
cd interactive-surface
start.bat
```

**Linux / Manjaro:**

```bash
cd ~/Загрузки
git clone https://github.com/Baryshnikovae/interactive-surface.git
cd interactive-surface
sh start.sh
```

Для работы с закрытой крышкой Windows и телефоном смотри [инструкцию](WINDOWS_EVENT_SETUP.md).

## Launch on Manjaro / other Linux

Download or clone this repository, connect a USB webcam and a projector, then run:

```bash
./start.sh
```

If the launch script cannot run, first grant permission:

```bash
chmod +x start.sh
./start.sh
```

The initial run installs dependencies into `.venv`; subsequent runs use the existing environment. You need Python 3.10+, a working graphical desktop session and permission to read the camera. On Linux the Qt display backend normally uses your active X11/Wayland session. Some Wayland compositors restrict programmatic window movement and fullscreen assignment; use the screen selection and test it on your installation.

## Launch on Windows 10/11

Install Python 3.10+ (with the `py` launcher), connect devices and run `start.bat` from the unpacked repository folder. It creates `.venv`, installs dependencies and starts the browser-based wizard. On subsequent launches it reuses `.venv`.

## Alternative developer commands

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m interactive_surface
```

Run tests:

```bash
python -m pytest -q
```

CLI options:

```bash
python -m interactive_surface --port 8765 --no-browser
python -m interactive_surface --lan-ip 192.168.1.42
```

## What the operator does

1. Connect devices and start the application. It opens `http://127.0.0.1:8765` on the laptop and prints a LAN URL and QR code for a phone. The QR contains a **temporary operator access token**. Only share it with trusted staff.
2. In **Equipment**, choose the USB camera and selected monitor, then open the projection window. A separate projector display is preferred. Test the correct display with the "Identify" button. When real hardware is unavailable, select the simulation camera and virtual projector.
3. In **Camera**, drag four labelled handles (TL → TR → BR → BL) to the four real markers in the live camera image. Use touch gestures or arrow nudges for precision.
4. In **Projector**, drag four markers on the control page to the **same four real physical spots**. The projector updates interactively.
5. In **Verification**, inspect the grid including points **between** the calibration corners. If accurate, confirm. The projector displays **«ИГРА ГОТОВА»**. The resulting profile is saved atomically outside the repo.

With no camera/display installed, the virtual camera and virtual projector let you exercise the web wizard in the browser; the browser-based virtual projection is not a substitute for hardware qualification. Use the built-in saved-profile restore only after connecting the same devices and selecting the same resolutions.

## Mathematical model

Two 3×3 planar homographies map `camera image (normalized) → wall [0,1]^2 → projector (normalized)`. The effective camera-to-projector matrix is `H_wall_to_projector @ H_camera_to_wall`. The reusable implementation is in `src/interactive_surface/geometry.py`, along with point conversion helpers for future games.

**Limits:** A planar homography corrects perspective for one plane, but not lens distortion or an uneven surface. Four fitted corners cannot measure interior reprojection error; verify with additional physical reference points on the projected test grid. No automatic optical calibration/structured light is implemented at this stage.

## Architecture

- `web.py`: FastAPI LAN API, short-lived operator token, MJPEG preview and calibration endpoints.
- `network.py`: ranks real private IPv4 Wi-Fi/Ethernet candidates, excluding common Docker and VPN interfaces. Real 172.16–172.31 networks are accepted.
- `cameras.py`: Linux V4L2 names and persistent by-id candidates, Windows DirectShow naming when available, one capture worker shared by all clients; virtual camera for simulation.
- `displays.py` / `projector_host.py`: Qt GUI isolated in a child process, listing screens and creating a fullscreen projector window with point, grid, identify and ready scenes. Browser manages this process via server calls.
- `geometry.py`: validated quadrilaterals and homography transforms.
- `controller.py`: central installation state and calibration lifecycle.
- `storage.py`: local atomic JSON profiles, cross-platform config path.
- `static/index.html`: responsive 5-step touch wizard, with point-drag and 0.1%-step nudging.
- `static/virtual.html`: browser-based virtual output for simulation.

## Security and network troubleshooting

No cloud dependency. The HTTP server listens on `0.0.0.0`, but its mutating operations require a per-run random token. Opening the control page from the phone requires scanning the QR code shown locally or in the **laptop's** terminal. Tokens are **not TLS protected** on a typical LAN. This protects against casual accidental access, not hostile LAN observers; use a trusted isolated event network. Do **not** expose port 8765 to the internet.

If the phone cannot connect: confirm both devices are on the same LAN, that Wi-Fi isolation is disabled, and that the laptop's firewall permits inbound port 8765. If multiple adapters exist, explicitly choose the correct IP with `--lan-ip`. The correct IP cannot be inferred with certainty when multiple disjoint LANs are active.

On Linux, camera enumeration uses `/dev/video*` and `/dev/v4l/by-id`; only compatible capture devices can actually open. Some devices expose additional metadata-only nodes. On Windows the optional `pygrabber` package helps display friendly DirectShow names; camera indices may change after unplug/replug, so always verify the preview. Display names/indices are reported by Qt and can change when hardware is reconnected.

## Verification to perform with physical equipment

- Check both Windows and Linux with actual USB webcams, integrated cameras, a projector and two display arrangements; verify `Identify` and fullscreen placement, including HiDPI scaling.
- Confirm the projector shows the calibration markers on the correct physical screen, not the laptop display.
- Mark four physical points; calibrate both quadrilaterals from the phone, then inspect the grid alignment at multiple **additional** points.
- Disconnect/reconnect the camera and projector, change output resolution and confirm recovery or invalidation warning.
- Verify mobile access on the actual LAN, that the QR selects its reachable IP, and that firewalls/client isolation do not block access.
- Test several hours of continuous preview and calibration to check capture recovery, stability and latency.

**Not physically validated in this build:** cross-OS Qt display placement, Windows/USB capture selection and projector accuracy. These need a live installation test.

## Recognition configuration (v0.3)

After camera/projector calibration, select **Настроить распознавание**. The page uses the same LAN server and operator session. Choose black or white projector background, place bright matte strips across the wall, freeze one camera frame, tap one or more coloured sample regions, and inspect the live overlay. The colour selection is based on robust circular-HSV statistics, with shape used only to estimate line geometry. Finish saves background/thresholds into the local calibration file. Changing the background invalidates the learnt colour settings and requires retraining.

Recognition runs in its own worker using the **latest** frame from the shared camera. The web preview is independently JPEG-encoded and does not drive the detector. The game-facing `/api/recognition/state` exposes line endpoints in normalized **wall-space**, IDs, last observation state, processing latency and detector FPS. `camera_a` / `camera_b` are additional coordinates used for browser debugging. Future game rendering must not wait on this endpoint; use current tracked state with an independent physics/render loop.

The target is lightweight real-time tracking, not guaranteed identification under full occlusion or arbitrary projector artwork. Bright moving projected graphics that match the plastic colour may create false positives; constant black/white background is the validated operating assumption for this stage. Real camera/projector latency, shadows, reflections and FPS require on-site measurement. Hardware validation intentionally deferred until the rest of the system is built.

## Version 0.4 — ball game and round control (in `main`)

After spatial calibration and colour recognition, open **`/games`** from the
calibration dashboard, or from any phone already paired with the LAN controller.
The actual projection is drawn by the existing Qt fullscreen window; the phone
only sends control actions. With the virtual screen selected, use
`/virtual-projector` to view a simulated output.

The first game is **Balls into the Hole**. Recognized rectangle corners become
physical colliders, preserving the full rectangle during short hand occlusions.
Balls spawn at the top centre, fall under gravity, bounce off strips and can
be steered into a side goal. The goal orbits smoothly in a restricted side
corridor, never crossing the central fall line. Tap a safe part of the map on
`/games` to change its position, and switch motion on/off separately.

Configure ball color, radius (8–26 logical wall pixels), appearance (`solid`,
`orbit`, `comet`) and visual style (`flat` or `neon`) from the same responsive
web page. The selected black/white projector background is inherited from
recognition. Changing that background invalidates the color calibration and
stops gameplay until it has been checked again.

### Round modes

- **Manual:** on a win screen until an operator starts another round.
- **Repeat:** wait for the win message, then restart the same game.
- **Sequence:** after winning, advance to the next installed game in the
  configured playlist. **At present only `hole` is implemented**, so sequence
  behaves like repeat until additional mechanics are added. The engine and API
  are ready for future game registration.

### Performance design

- Fixed **120 Hz** simulation in a dedicated thread, independent of camera
  tracking and the Qt drawing loop (nominal **60 Hz** repaint).
- Recognition objects are sampled up to 30 Hz, with stable rectangular
  collider geometry reused unless it actually moves.
- Latest-frame-only camera processing from the previous release stays intact.
- Ball list is bounded (10–100, default 65). Balls beyond the surface +
  margin or older than 12 seconds are removed, and all balls are cleared
  after a win. A spatial grid limits ball-to-ball candidate comparisons.
- Projector uses a projective Qt painter transform from the actual four-point
  calibration, rather than repeatedly warping a full-resolution image.
- Operator page runs its own animation loop and cannot block the game physics.

### Installing and running from `main`

Linux / Manjaro:

```bash
git clone https://github.com/Baryshnikovae/interactive-surface.git
cd interactive-surface
sh start.sh
```

Windows: clone the default `main` branch and run `start.bat`. The existing scripts
install the declared Python dependencies when needed.

Automated tests:

```bash
 python -m pip install -e '.[dev]'
 python -m pytest -q
```

### Known limits before venue tests

Real camera / USB and physical projector placement still require on-site tests.
Qt rendering / frame pacing with the actual GPU, driver and Wayland compositor
must be evaluated. The numerical benchmark measures the physics loop only, not
end-to-end projector latency or frame pacing. Gameplay currently implements one
mechanic and assumes one camera, one projector and one calibrated plane.
Objects heavily occluded for longer than the detector grace period cannot be
tracked reliably. The local operator token should not be shared beyond a trusted
LAN. There is no soundtrack or image upload in this milestone.

## Version 0.4.1 — calibration usability hotfix

- In **/recognition**, select an object by its **four corners** on the frozen frame. Drag a selected corner to refine it; add more green sticker regions and red *exclude-colour* regions (skin, wall, etc.). Undo and remove unwanted selections directly in the mobile UI. Learned colours are saved automatically.
- Rectangular physical objects use a principal-axis estimate for elongated contours; briefly obscured strips retain their full collision rectangles and update orientation when an elongated visible fragment remains.
- Stored colour settings are independent for black and white projected backgrounds. Selecting the same camera, video resolution and display on a subsequent launch restores compatible calibration and colour automatically, while changed hardware requires checking the setup.
- The hole appears at a newly randomized **lower-left/lower-right location** each round, alternating sides without entering the central drop corridor. Tapping the map manually pins the hole; choose **Случайное положение каждый раунд** to restore randomness. The projector no longer displays the top «ЛУНКА» heading.

Update a previously cloned Manjaro checkout (stop the current server first):

```bash
cd ~/Загрузки/interactive-surface-test
git fetch origin main
git switch -C main origin/main
sh start.sh
```

Local calibration, colour and game settings are stored outside Git in `~/.config/interactive-surface/calibration.json` by default. Back this file up before resetting the installation. False positives whose HSV values are essentially identical to the target colour cannot always be separated by colour alone; avoid matching colours in clothing, or use controlled lighting and the red exclusion samples.
