"""Local control server, automatic LAN QR, one CLI command."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

import qrcode
import uvicorn

from .network import choose_lan_ip
from .web import create_app


def main():
    parser=argparse.ArgumentParser(description="Interactive Surface calibration controller")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--lan-ip",default=os.getenv("INTERACTIVE_SURFACE_LAN_IP"))
    parser.add_argument("--no-qr",action="store_true")
    parser.add_argument("--no-browser",action="store_true")
    args=parser.parse_args()
    if not 1<=args.port<=65535:
        parser.error("--port must be between 1 and 65535")
    try:
        ip, candidates=choose_lan_ip(args.lan_ip)
    except ValueError as exc:
        parser.error(str(exc))
    lan_url=f"http://{ip}:{args.port}" if ip else None
    app=create_app(lan_url)
    print("\nInteractive Surface / настройка оборудования",flush=True)
    print(f"На ноутбуке: http://127.0.0.1:{args.port}",flush=True)
    if lan_url:
        print(f"Локальная сеть: {lan_url}",flush=True)
        if len(candidates)>1:
            print("Сетевые интерфейсы: "+", ".join(f"{i.interface}={i.ip}" for i in candidates),flush=True)
        if not args.no_qr:
            qr=qrcode.QRCode(border=2)
            qr.add_data(app.state.operator_url)
            qr.make(fit=True)
            print("\nQR для телефона (содержит код доступа оператора):\n",flush=True)
            qr.print_ascii(invert=True)
    else:
        print("Физическая локальная сеть не обнаружена; на ноутбуке управление доступно.",flush=True)
    print("\nCtrl+C — остановить сервер.\n",flush=True)
    if not args.no_browser:
        threading.Timer(1.25,lambda:webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    uvicorn.run(app,host="0.0.0.0",port=args.port,log_level="warning")


if __name__=="__main__":
    main()
