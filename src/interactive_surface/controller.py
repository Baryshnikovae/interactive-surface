"""One process owns installation state, shared between all authenticated browsers."""
from __future__ import annotations

from datetime import datetime, timezone
import threading

from .cameras import CameraService, discover as discover_cameras, prefer_camera
from .displays import ProjectorService, prefer_display
from .geometry import Calibration, quad
from .storage import Store

DEFAULT_CAMERA_QUAD = [[.14,.15],[.86,.15],[.86,.85],[.14,.85]]
DEFAULT_PROJECTOR_QUAD = [[.12,.13],[.88,.13],[.88,.87],[.12,.87]]


class Controller:
    def __init__(self, store: Store | None = None):
        self.lock = threading.RLock()
        self.camera = CameraService()
        self.projector = ProjectorService()
        self.store = store or Store()
        self.camera_quad = [p[:] for p in DEFAULT_CAMERA_QUAD]
        self.projector_quad = [p[:] for p in DEFAULT_PROJECTOR_QUAD]
        self.verified = False
        self.saved = self.store.read()
        self.warning = ""

    def devices(self) -> dict:
        screens = self.projector.screens()
        cameras = self.camera.devices()
        return {"cameras": cameras, "screens": screens, "recommended_camera": prefer_camera([d for d in cameras if d["id"] != "simulation"]), "recommended_screen": prefer_display(screens)}

    def select_camera(self, identity: str, width: int, height: int) -> dict:
        with self.lock:
            old = self.camera.status()
            result = self.camera.select(identity, width, height)
            if old["selected"] != identity or old["resolution"] != result["resolution"]:
                self.verified = False
            return result

    def open_projector(self, screen):
        with self.lock:
            previous = self.projector.screen_id
            data = self.projector.open(screen)
            if previous != screen:
                self.verified = False
            return data

    def update_points(self, which: str, points: list) -> dict:
        validated = quad(points).tolist()
        with self.lock:
            if which == "camera":
                self.camera_quad = validated
            elif which == "projector":
                self.projector_quad = validated
                self.projector.set_quad(validated)
            else:
                raise ValueError("Неизвестная система координат")
            self.verified = False
            return self.state()

    def calculate(self) -> Calibration:
        cam = self.camera.status()
        pro = self.projector.status()
        if not cam["selected"] or not cam["ready"]:
            raise ValueError("Сначала выберите и включите камеру")
        if not pro["active"]:
            raise ValueError("Сначала откройте проекционное окно")
        if pro["virtual"]:
            res=(1920,1080)
        else:
            screens=self.projector.screens()
            selected=next((d for d in screens if d["id"]==pro["screen"]),None)
            if not selected:
                raise ValueError("Выбранный дисплей больше не подключён")
            res=tuple(selected["resolution"])
        return Calibration(self.camera_quad, self.projector_quad, tuple(cam["resolution"]), res)

    def verify(self) -> dict:
        with self.lock:
            calibration = self.calculate()
            info = calibration.info()
            self.verified = False
            self.projector.set_mode("verify")
            return info

    def complete(self) -> dict:
        with self.lock:
            calibration=self.calculate()
            if self.projector.mode != "verify":
                raise ValueError("Перед завершением проверьте проекцию тестовой сеткой")
            camera=self.camera.status()
            projector=self.projector.status()
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "camera_id":camera["selected"],
                "camera_resolution":list(calibration.camera_resolution),
                "screen_id":projector["screen"],
                "projector_resolution":list(calibration.projector_resolution),
                "camera_quad":self.camera_quad,
                "projector_quad":self.projector_quad,
                "matrices":calibration.info(),
                "simulation": camera["simulation"] or projector["virtual"],
            }
            self.store.write(payload)
            self.saved=self.store.read()
            self.verified=True
            self.projector.set_mode("ready")
            return self.state()

    def restore(self) -> dict:
        with self.lock:
            data=self.saved
            if not data:
                raise ValueError("Нет сохранённой калибровки")
            camera=self.camera.status()
            projector=self.projector.status()
            if data.get("camera_id")!=camera["selected"] or data.get("camera_resolution")!=camera["resolution"]:
                raise ValueError("Камера или её разрешение изменились; настройте точки заново")
            if data.get("screen_id")!=projector["screen"]:
                raise ValueError("Проекционный экран изменился; настройте точки заново")
            self.camera_quad=quad(data["camera_quad"]).tolist()
            self.projector_quad=quad(data["projector_quad"]).tolist()
            cal=self.calculate()
            if list(cal.projector_resolution)!=data.get("projector_resolution"):
                raise ValueError("Разрешение проектора изменилось; нужна повторная калибровка")
            self.projector.set_quad(self.projector_quad)
            self.projector.set_mode("verify")
            self.verified=False
            return self.state()

    def reset(self):
        with self.lock:
            self.camera_quad=[p[:] for p in DEFAULT_CAMERA_QUAD]
            self.projector_quad=[p[:] for p in DEFAULT_PROJECTOR_QUAD]
            self.projector.set_quad(self.projector_quad)
            self.projector.set_mode("calibrate")
            self.verified=False
            self.store.clear()
            self.saved={}
            return self.state()

    def state(self) -> dict:
        return {
            "camera_quad":self.camera_quad,
            "projector_quad":self.projector_quad,
            "camera":self.camera.status(),
            "projector":self.projector.status(),
            "verified":self.verified,
            "has_saved_profile":bool(self.saved),
            "saved_at":self.saved.get("timestamp"),
            "saved_simulation":self.saved.get("simulation",False),
        }

    def close(self):
        self.camera.close()
        self.projector.close()
