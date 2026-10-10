"""Fast colour tracking for projected surfaces.

A dedicated worker consumes the newest camera frame only; browser polling never drives
recognition. Hue is circular (OpenCV 0..179); geometry is optional evidence, not a
hard rectangular-shape requirement. Positions are normalized to calibrated wall-space.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time

import cv2
import numpy as np

from .geometry import transform


@dataclass(frozen=True)
class ColourSettings:
    hue: float
    tolerance: float
    saturation: int
    value: int

    def to_dict(self) -> dict:
        return {"hue": round(self.hue, 3), "tolerance": round(self.tolerance, 3),
                "saturation": self.saturation, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict) -> "ColourSettings":
        h, t = float(data["hue"]), float(data["tolerance"])
        s, v = int(data["saturation"]), int(data["value"])
        if not 0 <= h < 180 or not 4 <= t <= 32 or not 0 <= s <= 255 or not 0 <= v <= 255:
            raise ValueError("Некорректный профиль цвета")
        return cls(h, t, s, v)


def circular_distance(values, hue: float):
    diff = np.abs(values.astype(np.float32) - hue)
    return np.minimum(diff, 180.0 - diff)


def learn_colour(frame: np.ndarray, points: list[list[float]]) -> ColourSettings:
    """Learn one permissive but bounded colour range from confirmed touch points.

    Each point samples a small local neighbourhood; only pixels close to the seed
    hue are retained to reject fingers/background. Coordinates are normalized.
    """
    if frame is None or frame.ndim != 3 or not 1 <= len(points) <= 24:
        raise ValueError("Выберите от 1 до 24 точек на пластиковых элементах")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width = hsv.shape[:2]
    patches = []
    for point in points:
        if len(point) != 2 or not all(math.isfinite(float(a)) and 0 <= a <= 1 for a in point):
            raise ValueError("Точки должны находиться внутри снимка")
        x = min(width - 1, max(0, round(point[0] * (width - 1))))
        y = min(height - 1, max(0, round(point[1] * (height - 1))))
        seed = hsv[y, x].astype(np.float32)
        if seed[1] < 38 or seed[2] < 40:
            raise ValueError("Выбранный участок слишком тёмный или ненасыщенный. Укажите яркий цветной участок")
        radius = max(3, round(min(width, height) * .010))
        patch = hsv[max(0, y-radius):min(height, y+radius+1), max(0, x-radius):min(width, x+radius+1)]
        valid = (circular_distance(patch[:, :, 0], seed[0]) <= 9) & (patch[:, :, 1] >= 30) & (patch[:, :, 2] >= 30)
        samples = patch[valid]
        if len(samples) < 8:
            raise ValueError("Выбранная точка не содержит достаточно цветных пикселей")
        patches.append(samples)
    pixels = np.concatenate(patches).astype(np.float32)
    theta = pixels[:, 0] * (2 * np.pi / 180)
    center = np.arctan2(np.mean(np.sin(theta)), np.mean(np.cos(theta))) % (2 * np.pi)
    hue = float(center * 180 / (2 * np.pi))
    distances = circular_distance(pixels[:, 0], hue)
    tolerance = float(np.clip(np.percentile(distances, 96) + 6, 7, 27))
    saturation = int(np.clip(np.percentile(pixels[:, 1], 10) - 45, 30, 180))
    value = int(np.clip(np.percentile(pixels[:, 2], 10) - 85, 25, 170))
    return ColourSettings(hue, tolerance, saturation, value)


def detect(frame: np.ndarray, settings: ColourSettings, camera_quad: list, *, max_width=960) -> tuple[list[dict], np.ndarray, float]:
    """Threshold source camera ROI (no expensive perspective frame warp)."""
    height, width = frame.shape[:2]
    scale = min(1., max_width / width)
    img = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else frame
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = settings.hue - settings.tolerance
    upper = settings.hue + settings.tolerance
    if lower < 0:
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, (0, settings.saturation, settings.value), (round(upper), 255, 255)),
            cv2.inRange(hsv, (round(180 + lower), settings.saturation, settings.value), (179, 255, 255)))
    elif upper >= 180:
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, (round(lower), settings.saturation, settings.value), (179, 255, 255)),
            cv2.inRange(hsv, (0, settings.saturation, settings.value), (round(upper - 180), 255, 255)))
    else:
        mask = cv2.inRange(hsv, (round(lower), settings.saturation, settings.value), (round(upper), 255, 255))
    polygon = np.rint(np.array(camera_quad, dtype=np.float32) * [w, h]).astype(np.int32)
    roi = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(roi, polygon, 255)
    mask = cv2.bitwise_and(mask, roi)
    # Small kernels bridge local reflection gaps while avoiding heavy image passes.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = max(32, w * h * .000065)
    results = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not min_area <= area <= w * h * .20:
            continue
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(cnt)
        if max(rw, rh) < 5:
            continue
        if rw < rh:
            angle += 90
        rad = math.radians(angle % 180)
        length = max(rw, rh)
        ux, uy = .5 * length * math.cos(rad), .5 * length * math.sin(rad)
        # Fit a complete rectangular footprint to the visible colour contour.
        # Shape is not used as a strict admission criterion; partial occlusions
        # are repaired from tracking history rather than the raw contour.
        a = [(cx-ux)/w, (cy-uy)/h]
        b = [(cx+ux)/w, (cy+uy)/h]
        nx, ny = -math.sin(rad)*min(rw,rh)*.5, math.cos(rad)*min(rw,rh)*.5
        corners = [[(cx-ux+nx)/w, (cy-uy+ny)/h],
                   [(cx+ux+nx)/w, (cy+uy+ny)/h],
                   [(cx+ux-nx)/w, (cy+uy-ny)/h],
                   [(cx-ux-nx)/w, (cy-uy-ny)/h]]
        results.append({"a": a, "b": b, "corners": corners,
                        "area": float(area) / (w*h), "center": [cx/w, cy/h]})
    results.sort(key=lambda d: d["area"], reverse=True)
    return results[:32], mask, scale


def rectangular_corners(a, b, half_width: float) -> list[list[float]]:
    """Return four corners of the reconstructed rectangular wall-space collider."""
    p, q = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    v = q - p
    length = float(np.linalg.norm(v))
    if length < 1e-8 or not np.isfinite(length):
        raise ValueError("Не удалось восстановить ось элемента")
    normal = np.array([-v[1], v[0]]) * (max(0., half_width) / length)
    return [point.tolist() for point in (p+normal, q+normal, q-normal, p-normal)]


def project_observations(observations: list[dict], camera_to_wall: np.ndarray) -> list[dict]:
    """Convert the visible fitted colour boxes to wall-space rectangles.

    A camera-space rectangle may become a quadrilateral after the homography.
    We retain its measured *width*, then build a consistent rectangular
    collision footprint in wall-space. Tracking can preserve that footprint
    when a hand temporarily hides part of the coloured region.
    """
    output = []
    for observation in observations:
        source = [observation["a"], observation["b"]]
        corners = observation.get("corners")
        if corners is not None:
            source += corners
        transformed = transform(camera_to_wall, source)
        if not np.isfinite(transformed).all():
            continue
        a, b = transformed[:2]
        item = {"a": a.tolist(), "b": b.tolist(), "area": observation["area"]}
        if corners is not None:
            c = transformed[2:]
            # Average the two end widths to attenuate projective distortion.
            width = (np.linalg.norm(c[0]-c[3]) + np.linalg.norm(c[1]-c[2])) * .5
            item["half_width"] = max(0., float(width) * .5)
            item["corners"] = rectangular_corners(a, b, item["half_width"])
        output.append(item)
    return output


def _align_endpoints(reference: dict, obs: dict):
    p = np.array([reference["a"], reference["b"]])
    q = np.array([obs["a"], obs["b"]])
    if np.sum((p-q[::-1])**2) < np.sum((p-q)**2):
        q = q[::-1]
    return p, q


class StableTracker:
    """Low-cost nearest-endpoint association with occlusion grace and movement hysteresis."""
    def __init__(self, hold_seconds=.36, retire_seconds=.9):
        self.tracks: dict[int, dict] = {}
        self.next_id = 1
        self.hold_seconds = hold_seconds
        self.retire_seconds = retire_seconds

    def update(self, observations: list[dict], timestamp: float) -> list[dict]:
        unmatched = set(range(len(observations)))
        pairs = []
        for tid, track in self.tracks.items():
            if timestamp - track["seen"] > self.retire_seconds:
                continue
            for j, observation in enumerate(observations):
                p, q = _align_endpoints(track, observation)
                distance = float(np.linalg.norm(p.mean(axis=0)-q.mean(axis=0)))
                if distance < .19:
                    length_ratio = min(np.linalg.norm(p[1]-p[0]), np.linalg.norm(q[1]-q[0])) / max(np.linalg.norm(p[1]-p[0]), np.linalg.norm(q[1]-q[0]), 1e-5)
                    cost = distance + .045 * (1-length_ratio)
                    pairs.append((cost, tid, j, q, distance, length_ratio))
        used_ids = set()
        for _, tid, j, q, distance, length_ratio in sorted(pairs, key=lambda item: item[0]):
            if tid in used_ids or j not in unmatched:
                continue
            used_ids.add(tid)
            unmatched.remove(j)
            t = self.tracks[tid]
            # A hand often truncates a strip. Hold its geometry until enough of it is visible.
            new_half_width = observation.get("half_width")
            old_half_width = t.get("half_width")
            width_ratio = 1.0
            if new_half_width is not None and old_half_width is not None:
                width_ratio = min(new_half_width, old_half_width) / max(new_half_width, old_half_width, 1e-7)
            # Partial hand coverage can truncate either length or width.
            # Prefer the last reliable full rectangle over a suddenly shrinking one.
            occluded = length_ratio < .75 or width_ratio < .70
            if not occluded:
                old = np.array([t["a"], t["b"]], dtype=float)
                error = float(np.linalg.norm(q-old, axis=1).max())
                if error > .0016:
                    moving = error > .007 or t.get("moving", False) and error > .003
                    alpha = .70 if moving else .26
                    updated = old + alpha * (q-old)
                    t["a"], t["b"] = updated.tolist()
                    t["moving"] = moving
                else:
                    t["moving"] = False
                if new_half_width is not None:
                    # Stable width estimates are gently filtered independently
                    # from movement; a hand cannot collapse the collider.
                    t["half_width"] = (0.85 * old_half_width + 0.15 * new_half_width
                                       if old_half_width is not None else new_half_width)
            t["seen"] = timestamp
            t["occluded"] = occluded
        for j in sorted(unmatched):
            observation = observations[j]
            q = np.array([observation["a"], observation["b"]])
            center = q.mean(axis=0)
            fragment_of_existing = False
            for previous in self.tracks.values():
                if timestamp - previous["seen"] > self.hold_seconds:
                    continue
                a, b = np.array(previous["a"]), np.array(previous["b"])
                edge = b-a
                t = float(np.clip(np.dot(center-a,edge) / max(np.dot(edge,edge),1e-8),0,1))
                perpendicular = np.linalg.norm(center-(a+t*edge))
                if perpendicular < .017 and np.linalg.norm(q[1]-q[0]) < .75*np.linalg.norm(edge):
                    fragment_of_existing = True
                    break
            if fragment_of_existing:
                continue
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = {"id": tid, "a": observation["a"], "b": observation["b"],
                                "half_width": observation.get("half_width"),
                                "seen": timestamp, "created": timestamp, "moving": False, "occluded": False}
        for tid in list(self.tracks):
            if timestamp - self.tracks[tid]["seen"] > self.retire_seconds:
                del self.tracks[tid]
        result = []
        for t in self.tracks.values():
            age = timestamp - t["seen"]
            if age > self.hold_seconds:
                continue
            obj = {"id": t["id"], "a": t["a"], "b": t["b"],
                   "state": "occluded" if t["occluded"] or age > .08 else "tracked",
                   "last_seen_age_ms": round(age*1000), "moving": t["moving"]}
            if t.get("half_width") is not None:
                obj["corners"] = rectangular_corners(t["a"], t["b"], t["half_width"])
                obj["width"] = t["half_width"] * 2
            result.append(obj)
        return result


class RecognitionService:
    """One worker and latest-frame mailbox, independent of UI and rendering."""
    def __init__(self, camera, camera_quad_getter):
        self.camera = camera
        self.camera_quad_getter = camera_quad_getter
        self.lock = threading.RLock()
        self.settings: ColourSettings | None = None
        self.background = "black"
        self.tracker = StableTracker()
        self.snapshot: np.ndarray | None = None
        self.snapshot_jpeg: bytes | None = None
        self.latest_objects: list[dict] = []
        self.running = True
        self.last_seq = -1
        self.last_frame_time = 0.
        self.processing_ms = 0.
        self.fps = 0.
        self.last_done = 0.
        self.frames_skipped = 0
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def freeze(self) -> tuple[bytes, tuple[int,int]]:
        frame, seq, _ = self.camera.get_latest()
        if frame is None:
            raise ValueError("Нет изображения камеры")
        with self.lock:
            self.snapshot = frame.copy()
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise ValueError("Не удалось сохранить снимок")
        with self.lock:
            self.snapshot_jpeg = encoded.tobytes()
        return encoded.tobytes(), (frame.shape[1], frame.shape[0])

    def learn(self, points: list[list[float]]) -> dict:
        with self.lock:
            if self.snapshot is None:
                raise ValueError("Сначала сделайте снимок")
            settings = learn_colour(self.snapshot, points)
            self.settings = settings
            self.tracker = StableTracker()
            return settings.to_dict()

    def change_background(self, background: str) -> None:
        if background not in ("black", "white"):
            raise ValueError("Фон должен быть чёрным или белым")
        with self.lock:
            if background != self.background:
                self.settings = None  # must relearn on a different lighting/projection background
                self.tracker = StableTracker()
            self.background = background
            self.snapshot = None
            self.snapshot_jpeg = None

    def invalidate(self):
        with self.lock:
            self.settings = None
            self.tracker = StableTracker()
            self.latest_objects = []

    def restore(self, config: dict):
        with self.lock:
            self.background = config.get("background", "black")
            if self.background not in ("black", "white"):
                self.background = "black"
            try:
                self.settings = ColourSettings.from_dict(config["settings"])
            except (KeyError, TypeError, ValueError):
                self.settings = None
            self.tracker = StableTracker()

    def state(self):
        with self.lock:
            return {"background": self.background,
                    "configured": self.settings is not None,
                    "settings": self.settings.to_dict() if self.settings else None,
                    "objects": self.latest_objects,
                    "processing_ms": round(self.processing_ms, 2),
                    "fps": round(self.fps, 1),
                    "frames_skipped": self.frames_skipped,
                    "camera_latency_ms": round(max(0.,(time.monotonic()-self.last_frame_time)*1000),1) if self.last_frame_time else None}

    def _loop(self):
        while self.running:
            frame, seq, ts = self.camera.get_latest()
            if frame is None or seq == self.last_seq:
                time.sleep(.007)
                continue
            before = time.monotonic()
            with self.lock:
                settings = self.settings
                previous_seq = self.last_seq
                self.last_seq = seq
            if settings:
                try:
                    quad = self.camera_quad_getter()
                    detections, _, _ = detect(frame, settings, quad["quad"])
                    objects = project_observations(detections, quad["matrix"])
                    with self.lock:
                        tracked = self.tracker.update(objects, before)
                        inverse = np.linalg.inv(quad["matrix"])
                        for item in tracked:
                            projected = transform(inverse, [item["a"], item["b"]])
                            item["camera_a"], item["camera_b"] = projected.tolist()
                            if "corners" in item:
                                item["camera_corners"] = transform(inverse, item["corners"]).tolist()
                        self.latest_objects = tracked
                except (ValueError, cv2.error):
                    with self.lock:
                        self.latest_objects = []
            else:
                with self.lock:
                    self.latest_objects = []
            ended = time.monotonic()
            with self.lock:
                self.frames_skipped += max(0, seq - previous_seq - 1) if previous_seq >= 0 else 0
                self.last_frame_time = ts
                self.processing_ms = .85*self.processing_ms + .15*((ended-before)*1000)
                if self.last_done:
                    instantaneous = 1/max(.001, ended-self.last_done)
                    self.fps = .85*self.fps + .15*instantaneous
                self.last_done = ended
            time.sleep(.001)

    def close(self):
        self.running = False
        self.worker.join(timeout=2)
