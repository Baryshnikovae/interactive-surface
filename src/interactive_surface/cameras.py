"""Device selection with Linux V4L2 persistent paths and Windows DShow names.

One capture instance is shared across all browser viewers.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys
import threading
import time

import cv2
import numpy as np


RESOLUTIONS = [(640, 480), (1280, 720), (1920, 1080)]


def discover() -> list[dict]:
    result = []
    if sys.platform.startswith("linux"):
        by_id = Path("/dev/v4l/by-id")
        links = {}
        if by_id.is_dir():
            for link in by_id.iterdir():
                try:
                    target = str(link.resolve())
                    if "video-index0" in link.name:
                        links[target] = str(link)
                except OSError:
                    continue
        for node in sorted(Path("/dev").glob("video[0-9]*")):
            devname = node.name
            name_path = Path("/sys/class/video4linux") / devname / "name"
            try:
                name = name_path.read_text().strip()
            except OSError:
                name = devname
            path = links.get(str(node), str(node))
            external = str(node) in links
            result.append({"id": path, "name": name, "external": external, "label": f"{name} ({devname})"})
    elif sys.platform == "win32":
        try:
            from pygrabber.dshow_graph import FilterGraph
            names = FilterGraph().get_input_devices()
        except Exception:
            names = []
        for i, name in enumerate(names):
            external = not any(x in name.lower() for x in ("integrated", "built-in", "internal", "ir camera"))
            result.append({"id": str(i), "name": name, "external": external, "label": name})
        if not names:
            result = [{"id": str(i), "name": f"Камера {i}", "external": False, "label": f"Камера {i}"} for i in range(4)]
    else:
        result = [{"id": str(i), "name": f"Camera {i}", "external": False, "label": f"Camera {i}"} for i in range(4)]
    return result


def prefer_camera(items: list[dict]) -> str | None:
    if not items:
        return None
    return next((x["id"] for x in items if x["external"]), items[0]["id"])


def synthetic_frame() -> np.ndarray:
    frame = np.full((720, 1280, 3), (36, 28, 22), dtype=np.uint8)
    cv2.rectangle(frame, (120, 100), (1150, 625), (64, 66, 73), -1)
    cv2.rectangle(frame, (120, 100), (1150, 625), (210, 198, 180), 2)
    for x, y in [(180, 155), (1090, 155), (1090, 570), (180, 570)]:
        cv2.circle(frame, (x, y), 15, (40, 210, 244), -1)
    cv2.putText(frame, "SIMULATION - NO CAMERA", (340, 355), cv2.FONT_HERSHEY_SIMPLEX, 1, (220, 222, 225), 2)
    return frame


class CameraService:
    def __init__(self):
        self.lock = threading.RLock()
        self.capture = None
        self.selected: str | None = None
        self.resolution = (1280, 720)
        self.simulation = False
        self.frame = None
        self.frame_seq = 0
        self.frame_time = 0.0
        self.jpeg_cache = None
        self.jpeg_seq = -1
        self.error = "Камера не выбрана"
        self.running = True
        self.worker = threading.Thread(target=self._capture_loop, daemon=True)
        self.worker.start()

    def devices(self) -> list[dict]:
        items = discover()
        items.insert(0, {"id": "simulation", "name": "Тестовая камера", "label": "Тестовый кадр (без оборудования)", "external": False})
        return items

    def select(self, device_id: str, width: int = 1280, height: int = 720) -> dict:
        if (width, height) not in RESOLUTIONS:
            raise ValueError("Неподдерживаемое разрешение")
        choices = self.devices()
        if device_id not in {c["id"] for c in choices}:
            raise ValueError("Камера не найдена. Обновите список устройств")
        with self.lock:
            if self.capture is not None:
                self.capture.release()
                self.capture = None
            self.simulation = device_id == "simulation"
            self.selected = device_id
            self.resolution = width, height
            self.frame = synthetic_frame() if self.simulation else None
            self.frame_seq += 1
            self.frame_time = time.monotonic()
            self.jpeg_cache = None
            self.jpeg_seq = -1
            if not self.simulation:
                arg = int(device_id) if device_id.isdigit() else device_id
                backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
                cap = cv2.VideoCapture(arg, backend)
                if not cap.isOpened():
                    cap.release()
                    self.selected = None
                    self.error = "Не удалось открыть камеру"
                    raise ValueError(self.error)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self.capture = cap
            self.error = ""
        return self.status()

    def _capture_loop(self) -> None:
        while self.running:
            started = time.monotonic()
            with self.lock:
                if self.simulation:
                    if self.frame is None:
                        self.frame = synthetic_frame()
                    self.frame_seq += 1
                    self.frame_time = time.monotonic()
                elif self.capture is not None:
                    ok, frame = self.capture.read()
                    if ok and frame is not None:
                        self.frame = frame
                        self.frame_seq += 1
                        self.frame_time = time.monotonic()
                        self.error = ""
                    else:
                        self.error = "Нет кадров. Проверьте подключение камеры"
            time.sleep(max(.002, 1 / 30 - (time.monotonic() - started)))

    def get_latest(self):
        with self.lock:
            return (self.frame, self.frame_seq, self.frame_time)

    def jpeg(self) -> bytes | None:
        with self.lock:
            if self.frame is None:
                return None
            if self.jpeg_seq != self.frame_seq:
                success, buffer = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, 76])
                if not success:
                    return None
                self.jpeg_cache = buffer.tobytes()
                self.jpeg_seq = self.frame_seq
            return self.jpeg_cache

    def status(self) -> dict:
        with self.lock:
            height, width = self.frame.shape[:2] if self.frame is not None else (self.resolution[1], self.resolution[0])
            return {"selected": self.selected, "resolution": [width, height], "simulation": self.simulation, "error": self.error, "ready": self.frame is not None}

    def close(self) -> None:
        self.running = False
        self.worker.join(timeout=2)
        with self.lock:
            if self.capture is not None:
                self.capture.release()
                self.capture = None
