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
    saturation_max: int = 255
    value_max: int = 255
    excluded_colours: tuple = ()

    def to_dict(self) -> dict:
        return {"hue": round(self.hue, 3), "tolerance": round(self.tolerance, 3),
                "saturation": self.saturation, "value": self.value,
                "saturation_max": self.saturation_max, "value_max": self.value_max,
                "excluded_colours": [list(x) for x in self.excluded_colours]}

    @classmethod
    def from_dict(cls, data: dict) -> "ColourSettings":
        h, t = float(data["hue"]), float(data["tolerance"])
        s, v = int(data["saturation"]), int(data["value"])
        if not 0 <= h < 180 or not 4 <= t <= 32 or not 0 <= s <= 255 or not 0 <= v <= 255:
            raise ValueError("Некорректный профиль цвета")
        sm, vm = int(data.get("saturation_max", 255)), int(data.get("value_max", 255))
        if not s <= sm <= 255 or not v <= vm <= 255:
            raise ValueError("Некорректные границы цвета")
        exclusions = tuple(tuple(float(v) for v in group) for group in data.get("excluded_colours", []))
        if len(exclusions) > 12 or any(len(x) != 6 or not all(math.isfinite(z) for z in x) for x in exclusions):
            raise ValueError("Некорректные исключения цвета")
        return cls(h, t, s, v, sm, vm, exclusions)


def circular_distance(values, hue: float):
    diff = np.abs(values.astype(np.float32) - hue)
    return np.minimum(diff, 180.0 - diff)


def _region_samples(hsv: np.ndarray, corners: list[list[float]]) -> np.ndarray:
    """Colour pixels strictly inside a selected convex quadrilateral.

    Eroding the selected area avoids picking up wall colour at its border.
    """
    if len(corners) != 4 or any(len(p) != 2 or not all(math.isfinite(float(x)) and 0 <= float(x) <= 1 for x in p) for p in corners):
        raise ValueError("Область должна иметь четыре угла в пределах кадра")
    h, w = hsv.shape[:2]
    polygon = np.rint(np.asarray(corners, dtype=np.float64) * [w-1, h-1]).astype(np.int32)
    if not cv2.isContourConvex(polygon) or cv2.contourArea(polygon) < 20:
        raise ValueError("Выделите непересекающуюся область внутри предмета")
    x, y, bw, bh = cv2.boundingRect(polygon)
    mask = np.zeros((bh, bw), np.uint8)
    cv2.fillConvexPoly(mask, polygon - [x, y], 255)
    if min(bw, bh) >= 8:
        mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    return hsv[y:y+bh, x:x+bw][mask > 0]


def learn_colour(frame: np.ndarray, points: list[list[float]] | None = None, *,
                 regions: list[list[list[float]]] | None = None,
                 negative_regions: list[list[list[float]]] | None = None) -> ColourSettings:
    """Learn chroma from selected objects, never from an unbounded camera patch.

    Positive regions contribute the dominant saturated colour; optional rejected
    regions help discriminate similarly hued background/skin where possible.
    Legacy touch points remain accepted for backward-compatible API clients.
    """
    if frame is None or frame.ndim != 3:
        raise ValueError("Нет кадра для настройки")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    if regions is not None:
        if not 1 <= len(regions) <= 24:
            raise ValueError("Укажите хотя бы один пластиковый элемент")
        patches = [_region_samples(hsv, polygon) for polygon in regions]
    else:
        if not points or not 1 <= len(points) <= 24:
            raise ValueError("Укажите цветные элементы")
        h, w = hsv.shape[:2]
        patches=[]
        for point in points:
            if len(point) != 2 or not all(math.isfinite(float(a)) and 0 <= a <= 1 for a in point):
                raise ValueError("Точка вне кадра")
            x=min(w-1, round(point[0]*(w-1)));y=min(h-1,round(point[1]*(h-1)))
            radius=max(3,round(min(w,h)*.010))
            patch=hsv[max(0,y-radius):min(h,y+radius+1),max(0,x-radius):min(w,x+radius+1)]
            patches.append(patch.reshape(-1,3))
    samples=np.concatenate(patches).astype(np.float32)
    strong=samples[(samples[:,1]>=38)&(samples[:,2]>=40)]
    if len(strong)<10:
        raise ValueError("На выделенной области мало различимого цвета")
    # Find the dominant saturated hue first; hands, wall, highlights must not
    # broaden the learnt hue even if they occupy a sizeable part of the polygon.
    histogram=np.bincount(strong[:,0].astype(np.int32),weights=strong[:,1],minlength=180)
    smooth=np.convolve(np.r_[histogram[-3:],histogram,histogram[:3]],np.ones(7),mode='valid')
    main=float(np.argmax(smooth))
    colour=strong[circular_distance(strong[:,0],main)<=13]
    if len(colour)<10 or len(colour)<len(strong)*.20:
        raise ValueError("Область содержит слишком много посторонних цветов. Выделите только пластик")
    theta=colour[:,0]*(2*np.pi/180)
    hue=float((np.arctan2(np.mean(np.sin(theta)),np.mean(np.cos(theta)))%(2*np.pi))*180/(2*np.pi))
    tolerance=float(np.clip(np.percentile(circular_distance(colour[:,0],hue),95)+3,4,22))
    sat=int(np.clip(np.percentile(colour[:,1],6)-30,38,255))
    val=int(np.clip(np.percentile(colour[:,2],6)-85,25,255))
    sat_max=int(np.clip(np.percentile(colour[:,1],99)+28,sat,255))
    val_max=int(np.clip(np.percentile(colour[:,2],99)+55,val,255))
    excluded=[]
    for polygon in (negative_regions or [])[:12]:
        negative=_region_samples(hsv,polygon).astype(np.float32)
        negative=negative[(negative[:,1]>20)&(negative[:,2]>20)]
        if len(negative)<10:continue
        # Exclude a coherent foreign hue only if distinct from plastic.
        theta=negative[:,0]*(2*np.pi/180)
        nh=float((np.arctan2(np.mean(np.sin(theta)),np.mean(np.cos(theta)))%(2*np.pi))*180/(2*np.pi))
        radius=float(np.clip(np.percentile(circular_distance(negative[:,0],nh),90)+2,3,14))
        low_s=int(np.clip(np.percentile(negative[:,1],10)-8,0,255)); high_s=int(np.clip(np.percentile(negative[:,1],90)+8,0,255))
        low_v=int(np.clip(np.percentile(negative[:,2],10)-12,0,255)); high_v=int(np.clip(np.percentile(negative[:,2],90)+12,0,255))
        if circular_distance(np.array([nh]),hue)[0] > tolerance+radius or high_s < sat or low_s > sat_max or high_v < val or low_v > val_max:
            excluded.append((nh,radius,low_s,high_s,low_v,high_v))
    return ColourSettings(hue,tolerance,sat,val,sat_max,val_max,tuple(excluded))

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
            cv2.inRange(hsv, (0, settings.saturation, settings.value), (round(upper), settings.saturation_max, settings.value_max)),
            cv2.inRange(hsv, (round(180 + lower), settings.saturation, settings.value), (179, settings.saturation_max, settings.value_max)))
    elif upper >= 180:
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, (round(lower), settings.saturation, settings.value), (179, settings.saturation_max, settings.value_max)),
            cv2.inRange(hsv, (0, settings.saturation, settings.value), (round(upper - 180), settings.saturation_max, settings.value_max)))
    else:
        mask = cv2.inRange(hsv, (round(lower), settings.saturation, settings.value), (round(upper), settings.saturation_max, settings.value_max))
    for hue, tolerance, lo_s, hi_s, lo_v, hi_v in settings.excluded_colours:
        reject = ((circular_distance(hsv[:, :, 0],hue)<=tolerance) &
                  (hsv[:, :, 1]>=lo_s) & (hsv[:, :, 1]<=hi_s) &
                  (hsv[:, :, 2]>=lo_v) & (hsv[:, :, 2]<=hi_v))
        mask[reject]=0
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
        length, width = max(rw,rh), min(rw,rh)
        if len(cnt)>=5 and length/max(width,1.)>=2.0:
            data=cnt.reshape(-1,2).astype(np.float64)
            _, eigenvectors, eigenvalues=cv2.PCACompute2(data,mean=None)
            axis=eigenvectors[0]
            rad=math.atan2(float(axis[1]),float(axis[0])) % math.pi
            ux0,uy0=math.cos(rad),math.sin(rad)
            projections=data @ np.array([ux0,uy0])
            length=float(np.percentile(projections,99)-np.percentile(projections,1))
            center_proj=(np.percentile(projections,99)+np.percentile(projections,1))*.5
            current_proj=cx*ux0+cy*uy0
            cx+=(center_proj-current_proj)*ux0;cy+=(center_proj-current_proj)*uy0
        else:
            if rw < rh: angle += 90
            rad = math.radians(angle % 180)
        ux, uy = .5 * length * math.cos(rad), .5 * length * math.sin(rad)
        # Fit a complete rectangular footprint to the visible colour contour.
        # Shape is not used as a strict admission criterion; partial occlusions
        # are repaired from tracking history rather than the raw contour.
        a = [(cx-ux)/w, (cy-uy)/h]
        b = [(cx+ux)/w, (cy+uy)/h]
        nx, ny = -math.sin(rad)*width*.5, math.cos(rad)*width*.5
        corners = [[(cx-ux+nx)/w, (cy-uy+ny)/h],
                   [(cx+ux+nx)/w, (cy+uy+ny)/h],
                   [(cx+ux-nx)/w, (cy+uy-ny)/h],
                   [(cx-ux-nx)/w, (cy-uy-ny)/h]]
        results.append({"a": a, "b": b, "corners": corners,
                        "area": float(area) / (w*h), "center": [cx/w, cy/h],
                        "elongation": float(length/max(width,1.))})
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
        item = {"a": a.tolist(), "b": b.tolist(), "area": observation["area"], "elongation": observation.get("elongation",1.)}
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
            if occluded and observation.get("elongation",1.) >= 2.5 and length_ratio >= .30:
                old=np.array([t["a"],t["b"]],dtype=float)
                edge=old[1]-old[0]; observed=q[1]-q[0]
                old_angle=math.atan2(edge[1],edge[0]); new_angle=math.atan2(observed[1],observed[0])
                delta=(new_angle-old_angle+math.pi/2)%math.pi-math.pi/2
                if abs(delta)<math.radians(28):
                    angle=old_angle+delta*.45
                    center=old.mean(axis=0)
                    direction=np.array([math.cos(angle),math.sin(angle)]) * np.linalg.norm(edge)*.5
                    t["a"],t["b"]=(center-direction).tolist(),(center+direction).tolist()
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
        self.profiles: dict[str,ColourSettings] = {}
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

    def learn(self, points: list[list[float]] | None = None,
              regions: list | None = None, negative_regions: list | None = None) -> dict:
        with self.lock:
            if self.snapshot is None:
                raise ValueError("Сначала сделайте снимок")
            settings = learn_colour(self.snapshot, points, regions=regions,
                                    negative_regions=negative_regions)
            self.settings = settings
            self.profiles[self.background] = settings
            self.tracker = StableTracker()
            return settings.to_dict()

    def change_background(self, background: str) -> None:
        if background not in ("black", "white"):
            raise ValueError("Фон должен быть чёрным или белым")
        with self.lock:
            if background != self.background:
                self.settings = self.profiles.get(background)
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
            self.profiles = {}
            for bg, colour in config.get("profiles", {}).items():
                if bg in ("black", "white"):
                    try:self.profiles[bg]=ColourSettings.from_dict(colour)
                    except (ValueError,KeyError,TypeError):pass
            self.background = config.get("background", "black")
            if self.background not in ("black", "white"):
                self.background = "black"
            if self.background not in self.profiles:
                try:self.profiles[self.background]=ColourSettings.from_dict(config["settings"])
                except (KeyError, TypeError, ValueError):pass
            self.settings=self.profiles.get(self.background)
            self.tracker = StableTracker()

    def state(self):
        with self.lock:
            return {"background": self.background,
                    "configured": self.settings is not None,
                    "settings": self.settings.to_dict() if self.settings else None,
                    "saved_backgrounds": sorted(self.profiles.keys()),
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
