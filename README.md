# Interactive Surface

**Version 0.2.0: installation and camera–projector calibration.**

A local operator UI for calibrating a physical-digital interactive wall. The games are **not yet ported**. The old project remains unchanged: [virtual_wall_balls](https://github.com/Baryshnikovae/virtual_wall_balls).

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
