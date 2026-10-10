"""Minimal, network-accessible control-page foundation."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response


PAGE = Path(__file__).parent / "static" / "index.html"


def create_app(lan_url: str | None = None) -> FastAPI:
    app = FastAPI(title="Interactive Surface Control", version="0.1.0")
    qr_png = None
    if lan_url:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(lan_url)
        qr.make(fit=True)
        stream = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(stream, format="PNG")
        qr_png = stream.getvalue()

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(PAGE, media_type="text/html")

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return {"ok": True, "mode": "demo", "lan_url": lan_url}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/qr.png", include_in_schema=False)
    def qr_image() -> Response:
        if qr_png is None:
            raise HTTPException(status_code=404, detail="LAN address is not available")
        return Response(qr_png, media_type="image/png", headers={"Cache-Control": "no-store"})

    return app
