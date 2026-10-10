"""One process owns installation state, shared between all authenticated browsers."""
from __future__ import annotations

from datetime import datetime, timezone
import threading

from .cameras import CameraService, discover as discover_cameras, prefer_camera
from .displays import ProjectorService, prefer_display
from .geometry import Calibration, quad
from .recognition import RecognitionService
from .game import GameEngine, GameSettings
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
        self.recognition = RecognitionService(self.camera, self._recognition_geometry)
        if self.saved.get("recognition"):
            self.recognition.restore(self.saved["recognition"])
        try:
            game_settings = GameSettings.parse(self.saved.get("game", {}))
        except ValueError:
            game_settings = GameSettings()
        self.game = GameEngine(lambda: self.recognition.state()["objects"], self.projector.publish_game,
                               config=game_settings.__dict__)

    def _recognition_geometry(self):
        from .geometry import homography, WALL
        with self.lock:
            return {"quad": [p[:] for p in self.camera_quad], "matrix": homography(quad(self.camera_quad), WALL)}

    def devices(self) -> dict:
        screens = self.projector.screens()
        cameras = self.camera.devices()
        return {"cameras": cameras, "screens": screens, "recommended_camera": prefer_camera([d for d in cameras if d["id"] != "simulation"]), "recommended_screen": prefer_display(screens)}

    def select_camera(self, identity: str, width: int, height: int) -> dict:
        with self.lock:
            old = self.camera.status()
            result = self.camera.select(identity, width, height)
            if old["selected"] != identity or old["resolution"] != result["resolution"]:
                self.game.stop()
                self.verified = False
                self.recognition.invalidate()
            return result

    def open_projector(self, screen):
        with self.lock:
            previous = self.projector.screen_id
            data = self.projector.open(screen)
            if previous != screen:
                self.game.stop()
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
            self.game.stop()
            self.verified = False
            self.recognition.invalidate()
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
            if self.recognition.settings and self.saved.get("recognition"):
                payload["recognition"] = self.saved["recognition"]
            payload["game"] = self.game.state()["settings"]
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
            self.game.stop()
            self.recognition.invalidate()
            self.verified=False
            return self.state()

    def reset(self):
        with self.lock:
            self.camera_quad=[p[:] for p in DEFAULT_CAMERA_QUAD]
            self.projector_quad=[p[:] for p in DEFAULT_PROJECTOR_QUAD]
            self.projector.set_quad(self.projector_quad)
            self.projector.set_mode("calibrate")
            self.verified=False
            self.recognition.restore({})
            self.game.stop()
            self.store.clear()
            self.saved={}
            return self.state()

    def choose_background(self, background: str) -> dict:
        with self.lock:
            if not self.verified:
                raise ValueError("Сначала завершите калибровку камеры и проектора")
            self.game.stop()
            self.recognition.change_background(background)
            self.projector.set_background(background)
            self.projector.set_mode("background")
            return self.recognition.state()

    def freeze_recognition(self):
        with self.lock:
            if not self.verified:
                raise ValueError("Сначала завершите калибровку")
            return self.recognition.freeze()

    def teach_recognition(self, points: list[list[float]]):
        with self.lock:
            if not self.verified:
                raise ValueError("Сначала завершите калибровку")
            return self.recognition.learn(points)

    def finish_recognition(self):
        with self.lock:
            if not self.verified or self.recognition.settings is None:
                raise ValueError("Сначала завершите калибровку и обучение цвета")
            data = self.store.read()
            if not data:
                raise ValueError("Не найдена сохранённая пространственная калибровка")
            data["recognition"] = {"background": self.recognition.background,
                                   "settings": self.recognition.settings.to_dict()}
            self.store.write(data)
            self.saved = self.store.read()
            self.projector.set_mode("ready")
            return self.state()

    def start_game(self, game: str = "hole") -> dict:
        with self.lock:
            if not self.verified or not self.projector.status()["active"]:
                raise ValueError("Сначала завершите пространственную калибровку и включите проектор")
            if self.recognition.settings is None:
                raise ValueError("Сначала настройте распознавание цветных элементов")
            result = self.game.start(game)
            self.projector.set_mode("game")
            return result

    def stop_game(self) -> dict:
        with self.lock:
            state = self.game.stop()
            if self.projector.status()["active"]:
                self.projector.set_mode("ready")
            return state

    def configure_game(self, updates: dict) -> dict:
        with self.lock:
            state = self.game.configure(updates)
            data = self.store.read()
            if data:
                data["game"] = state["settings"]
                self.store.write(data)
                self.saved = self.store.read()
            return state

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
            "recognition": self.recognition.state(),
            "game": self.game.state(),
        }

    def close(self):
        self.game.close()
        self.recognition.close()
        self.camera.close()
        self.projector.close()
