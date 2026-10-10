# Interactive Surface

New foundation for physical-digital interactive projection installations.

**Current status: 0.1.0 — LAN control demo.** Games, calibration and projector control are not part of this first release.

## Setup (Linux / Manjaro)

```bash
git clone https://github.com/Baryshnikovae/interactive-surface.git
cd interactive-surface
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
interactive-surface
```

The terminal displays the laptop URL (`http://127.0.0.1:8765`), a LAN URL chosen from available physical adapters, and a QR code for a phone on the same network. The demo page also shows a QR code.

Select the correct adapter manually if required:

```bash
interactive-surface --lan-ip 192.168.1.42
```

Change the port:

```bash
interactive-surface --port 8080
```

If the phone cannot connect, check that both devices are on the same LAN, client isolation is disabled and the laptop firewall allows inbound TCP traffic on port 8765. Docker and VPN interfaces are excluded from automatic selection; real private 172.16–172.31 networks are supported.

Test locally:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

The first control page is **read-only demo content**. Add authentication before implementing sensitive controls. Do not expose the local service to the public internet.
