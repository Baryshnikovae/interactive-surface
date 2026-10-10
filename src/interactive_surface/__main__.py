"""Start the local controller and show its reachable LAN address as a QR code."""

from __future__ import annotations

import argparse
import os
import sys

import qrcode
import uvicorn

from .network import choose_lan_ip
from .web import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Surface local control server")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument(
        "--lan-ip", default=os.getenv("INTERACTIVE_SURFACE_LAN_IP"),
        help="Override automatic LAN address selection",
    )
    parser.add_argument("--no-qr", action="store_true", help="Do not print terminal QR code")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    try:
        lan_ip, candidates = choose_lan_ip(args.lan_ip)
    except ValueError as exc:
        parser.error(str(exc))

    lan_url = f"http://{lan_ip}:{args.port}" if lan_ip else None
    print("\nInteractive Surface — local control (demo)", flush=True)
    print(f"Laptop:  http://127.0.0.1:{args.port}", flush=True)
    if lan_url:
        print(f"Phone:   {lan_url}", flush=True)
        if len(candidates) > 1:
            alternatives = ", ".join(f"{c.interface}={c.ip}" for c in candidates)
            print(f"Detected local interfaces: {alternatives}", flush=True)
        if not args.no_qr:
            qr = qrcode.QRCode(border=2)
            qr.add_data(lan_url)
            qr.make(fit=True)
            print("\nScan this QR on a device in the same local network:\n", flush=True)
            qr.print_ascii(invert=True)
    else:
        print("No physical LAN IPv4 address found. Connect to Wi-Fi/Ethernet.", flush=True)
        print("Local web page remains available on the laptop; QR was not generated.", flush=True)
    print("\nPress Ctrl+C to stop.\n", flush=True)
    try:
        uvicorn.run(create_app(lan_url), host="0.0.0.0", port=args.port, log_level="warning")
    except OSError as exc:
        print(f"Cannot start server: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
