"""Local API and mobile control. No internet or cloud identity required."""
from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
import ipaddress
import json
import secrets
import time

import qrcode
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .controller import Controller

PAGE = Path(__file__).parent / "static" / "index.html"
VIRTUAL_PAGE = Path(__file__).parent / "static" / "virtual.html"
RECOGNITION_PAGE = Path(__file__).parent / "static" / "recognition.html"
GAME_PAGE = Path(__file__).parent / "static" / "games.html"
TRACKING_PAGE = Path(__file__).parent / "static" / "tracking.html"


class GameChoice(BaseModel):
    game: str = "hole"


class GameChange(BaseModel):
    changes: dict


class CameraChoice(BaseModel):
    id: str
    width: int = 1280
    height: int = 720


class DisplayChoice(BaseModel):
    id: int | str


class PointUpdate(BaseModel):
    points: list[list[float]]


class ModeChoice(BaseModel):
    mode: str


class BackgroundChoice(BaseModel):
    background: str


class SampleChoice(BaseModel):
    points: list[list[float]] = Field(min_length=1, max_length=24)


def _loopback(request: Request) -> bool:
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        return False


def create_app(lan_url: str | None = None, controller: Controller | None = None, token: str | None = None) -> FastAPI:
    key = token or secrets.token_urlsafe(24)
    c = controller or Controller()
    owns = controller is None
    operator_url = f"{lan_url}/?token={key}" if lan_url else None

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns:
            c.close()

    app = FastAPI(title="Interactive Surface Control", version="0.4.0", lifespan=lifespan)
    app.state.controller=c
    app.state.operator_token=key
    app.state.operator_url=operator_url

    def authorized(request: Request):
        provided=request.headers.get("x-control-token") or request.query_params.get("token")
        if not provided or not secrets.compare_digest(provided, key):
            raise HTTPException(401, "Требуется подключение оператора через QR-код")
        return True

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(PAGE, media_type="text/html")

    @app.get("/games", include_in_schema=False)
    def games_page() -> FileResponse:
        return FileResponse(GAME_PAGE, media_type="text/html")

    @app.get("/recognition", include_in_schema=False)
    def recognition_page() -> FileResponse:
        return FileResponse(RECOGNITION_PAGE, media_type="text/html")

    @app.get("/tracking", include_in_schema=False)
    def tracking_page() -> FileResponse:
        return FileResponse(TRACKING_PAGE, media_type="text/html")

    @app.get("/virtual-projector", include_in_schema=False)
    def virtual() -> FileResponse:
        return FileResponse(VIRTUAL_PAGE, media_type="text/html")

    @app.get("/health")
    def health():
        return {"status":"ok"}

    @app.get("/api/status")
    def status():
        return {"ok":True,"mode":"calibration","lan_url":lan_url,"paired_required":True}

    @app.get("/api/session")
    def session(request:Request):
        provided=request.headers.get("x-control-token") or request.query_params.get("token")
        success=bool(provided and secrets.compare_digest(provided,key))
        if _loopback(request):
            return {"authorized":True,"token":key,"local":True,"lan_url":lan_url}
        return {"authorized":success,"local":False,"lan_url":lan_url}

    @app.get("/qr.png", include_in_schema=False)
    def qr_image(request:Request):
        if not operator_url or not _loopback(request):
            raise HTTPException(403,"QR-код доступен только на ноутбуке")
        qr=qrcode.QRCode(box_size=8,border=2)
        qr.add_data(operator_url)
        qr.make(fit=True)
        stream=BytesIO()
        qr.make_image(fill_color="black",back_color="white").save(stream,format="PNG")
        return Response(stream.getvalue(),media_type="image/png",headers={"Cache-Control":"no-store"})

    @app.get("/api/devices",dependencies=[Depends(authorized)])
    def devices():
        return c.devices()

    @app.get("/api/state",dependencies=[Depends(authorized)])
    def state():
        return c.state()

    @app.post("/api/camera/select",dependencies=[Depends(authorized)])
    def select_camera(body:CameraChoice):
        try:
            return c.select_camera(body.id,body.width,body.height)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/camera/stream")
    def camera_stream(request:Request):
        authorized(request)
        def frames():
            while True:
                data=c.camera.jpeg()
                if data:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "+str(len(data)).encode()+b"\r\n\r\n"+data+b"\r\n"
                time.sleep(.10)
        return StreamingResponse(frames(),media_type="multipart/x-mixed-replace; boundary=frame",headers={"Cache-Control":"no-cache, no-store"})

    @app.post("/api/display/open",dependencies=[Depends(authorized)])
    def display_open(body:DisplayChoice):
        try:
            return c.open_projector(body.id)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/display/close",dependencies=[Depends(authorized)])
    def display_close():
        c.projector.close()
        return c.state()

    @app.post("/api/display/mode",dependencies=[Depends(authorized)])
    def display_mode(body:ModeChoice):
        try:
            c.projector.set_mode(body.mode)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        return c.state()

    @app.post("/api/calibration/points/{which}",dependencies=[Depends(authorized)])
    def points(which:str,body:PointUpdate):
        try:
            return c.update_points(which,body.points)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/calibration/verify",dependencies=[Depends(authorized)])
    def verify():
        try:
            return c.verify()
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/calibration/complete",dependencies=[Depends(authorized)])
    def complete():
        try:
            return c.complete()
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/calibration/restore",dependencies=[Depends(authorized)])
    def restore():
        try:
            return c.restore()
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/calibration/reset",dependencies=[Depends(authorized)])
    def reset():
        return c.reset()

    @app.get("/api/recognition/state",dependencies=[Depends(authorized)])
    def recognition_state():
        return c.recognition.state()

    @app.post("/api/recognition/background",dependencies=[Depends(authorized)])
    def recognition_background(body:BackgroundChoice):
        try:
            return c.choose_background(body.background)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/recognition/capture",dependencies=[Depends(authorized)])
    def recognition_capture():
        try:
            jpeg, resolution=c.freeze_recognition()
            return {"ok":True,"resolution":resolution}
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/recognition/snapshot",dependencies=[Depends(authorized)])
    def recognition_snapshot():
        with c.recognition.lock:
            jpeg=c.recognition.snapshot_jpeg
        if jpeg is None:
            raise HTTPException(404,"Сначала сделайте снимок")
        return Response(jpeg,media_type="image/jpeg",headers={"Cache-Control":"no-store"})

    @app.post("/api/recognition/learn",dependencies=[Depends(authorized)])
    def recognition_learn(body:SampleChoice):
        try:
            return c.teach_recognition(body.points)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/recognition/finish",dependencies=[Depends(authorized)])
    def recognition_finish():
        try:
            return c.finish_recognition()
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/games",dependencies=[Depends(authorized)])
    def games_catalog():
        return {"games": c.game.available_games}

    @app.get("/api/game/state",dependencies=[Depends(authorized)])
    def game_state():
        return c.game.state()

    @app.post("/api/game/start",dependencies=[Depends(authorized)])
    def game_start(body: GameChoice):
        try:
            return c.start_game(body.game)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/game/stop",dependencies=[Depends(authorized)])
    def game_stop():
        return c.stop_game()

    @app.post("/api/game/settings",dependencies=[Depends(authorized)])
    def game_settings(body: GameChange):
        try:
            return c.configure_game(body.changes)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/projector/visual",dependencies=[Depends(authorized)])
    def visual():
        from .geometry import WALL, homography, transform
        p=c.projector.status()
        output={"mode":p["mode"],"quad":p["quad"],"active":p["active"],"screen":p["screen"],"background":p["background"]}
        if p["mode"] == "game":
            output["game"] = c.game.state()
        if p["mode"] == "verify":
            h=homography(WALL, p["quad"])
            grid=[]
            for i in range(1, 9):
                t=i/9
                for endpoints in ([[t,0],[t,1]],[[0,t],[1,t]]):
                    grid.append(transform(h,endpoints).tolist())
            output["grid"]=grid
        return output

    return app
