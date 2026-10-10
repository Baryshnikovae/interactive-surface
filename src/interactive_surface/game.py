"""Deterministic, bounded arcade physics and a lightweight multi-game round scheduler.

The simulation uses wall pixels (1600 x 1000) for isotropic collisions, whereas
recognition and calibration use normalized wall coordinates. No display or camera
code executes on the physics thread; projector frames are immutable snapshots.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random
import re
import threading
import time
from typing import Callable

W, H = 1600.0, 1000.0
DT = 1.0 / 120.0
SPAWN_X = 800.0
GOAL_SIDES = ((180.0, 515.0), (1085.0, 1420.0))
PALETTE = ("solid", "orbit", "comet")
MODES = ("manual", "repeat", "sequence")
AVAILABLE_GAMES = ("hole",)


@dataclass
class GameSettings:
    cycle_mode: str = "manual"
    visual_style: str = "neon"
    ball_design: str = "orbit"
    ball_color: str = "#70e9ff"
    ball_radius: int = 14
    moving_goal: bool = True
    goal_manual: bool = False
    goal_x: float = 0.78
    goal_y: float = 0.72
    target_hits: int = 5
    spawn_interval: float = 0.42
    max_balls: int = 65
    playlist: tuple[str, ...] = ("hole",)

    @classmethod
    def parse(cls, data: dict) -> "GameSettings":
        result = cls()
        allowed = set(cls.__dataclass_fields__)
        for key, value in data.items():
            if key not in allowed:
                raise ValueError(f"Неизвестная настройка: {key}")
            if key == "cycle_mode" and value not in MODES:
                raise ValueError("Неизвестный режим смены раундов")
            elif key == "visual_style" and value not in ("flat", "neon"):
                raise ValueError("Неизвестный визуальный стиль")
            elif key == "ball_design" and value not in PALETTE:
                raise ValueError("Неизвестный дизайн шарика")
            elif key == "ball_color" and (not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
                raise ValueError("Укажите цвет в формате #RRGGBB")
            elif key == "ball_radius" and (type(value) is not int or not 8 <= value <= 26):
                raise ValueError("Радиус шарика должен быть от 8 до 26")
            elif key == "moving_goal" and type(value) is not bool:
                raise ValueError("Некорректное значение движения лунки")
            elif key in ("goal_x", "goal_y") and (not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError("Координаты лунки должны находиться между 0 и 1")
            elif key == "target_hits" and (type(value) is not int or not 1 <= value <= 50):
                raise ValueError("Количество попаданий должно быть от 1 до 50")
            elif key == "spawn_interval" and (type(value) not in (int, float) or not .2 <= value <= 2):
                raise ValueError("Интервал появления должен быть от 0,2 до 2 секунд")
            elif key == "goal_manual" and type(value) is not bool:
                raise ValueError("Режим размещения лунки должен быть логическим")
            elif key == "max_balls" and (type(value) is not int or not 10 <= value <= 100):
                raise ValueError("Ограничение шариков должно быть от 10 до 100")
            elif key == "playlist":
                if not isinstance(value, (list, tuple)) or not value or any(x not in AVAILABLE_GAMES for x in value):
                    raise ValueError("Список игр содержит неизвестную игру")
                value = tuple(value)
            setattr(result, key, value)
        if ("goal_x" in data or "goal_y" in data) and "goal_manual" not in data:
            result.goal_manual = True
        if not safe_goal(result.goal_x, result.goal_y):
            raise ValueError("Лунка должна находиться сбоку от центрального потока")
        return result


def safe_goal(x: float, y: float) -> bool:
    return .54 <= y <= .89 and any(lo <= x * W <= hi for lo, hi in GOAL_SIDES)


@dataclass
class Ball:
    id: int
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    age: float = 0.


def _closest_segment(x: float, y: float, a: tuple, b: tuple) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = min(1., max(0., ((x-a[0])*dx+(y-a[1])*dy) / max(dx*dx+dy*dy, 1e-10)))
    return a[0]+t*dx, a[1]+t*dy


def _point_inside(x: float, y: float, polygon: tuple) -> bool:
    positive = negative = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
        positive |= cross > 0
        negative |= cross < 0
    return not (positive and negative)


class HoleRound:
    id = "hole"
    title = "Шарики и лунка"

    def __init__(self, settings: GameSettings, random_seed: int | None = None):
        self.rng = random.Random(random_seed)
        self.settings = settings
        self.balls: list[Ball] = []
        self.obstacles: dict[int, tuple] = {}
        self.score = 0
        self.finished = False
        self.total_spawned = 0
        self.total_culled = 0
        self.next_id = 1
        self.spawn_clock = 0.
        self.elapsed = 0.
        self.goal_x = settings.goal_x * W
        self.goal_y = settings.goal_y * H
        self.base_goal_x = self.goal_x
        self.base_goal_y = self.goal_y
        self.goal_radius = 45.0
        self.last_hit = -20.
        self._goal_phase = 0.
        self.randomize_goal()

    def randomize_goal(self, side: int | None = None) -> None:
        if self.settings.goal_manual:
            self.base_goal_x = self.settings.goal_x * W
            self.base_goal_y = self.settings.goal_y * H
        else:
            left, right = GOAL_SIDES[side if side in (0, 1) else self.rng.randrange(2)]
            self.base_goal_x = self.rng.uniform(left + 92, right - 92)
            self.base_goal_y = self.rng.uniform(670, 790)
        self._goal_phase = self.rng.uniform(-math.pi, math.pi)
        self._goal_position(0.)

    def set_obstacles(self, objects: list[dict]) -> None:
        seen = set()
        for obj in objects:
            try:
                identity = int(obj["id"])
                poly = obj.get("corners")
                if poly is None or len(poly) != 4:
                    continue
                polygon = tuple((float(x)*W, float(y)*H) for x, y in poly)
                if any(not math.isfinite(v) for p in polygon for v in p):
                    continue
                seen.add(identity)
                previous = self.obstacles.get(identity)
                if previous is None or max(math.dist(a, b) for a, b in zip(previous, polygon)) >= 1.5:
                    self.obstacles[identity] = polygon
            except (TypeError, ValueError, KeyError, OverflowError):
                continue
        for identity in self.obstacles.keys() - seen:
            del self.obstacles[identity]

    def _goal_position(self, dt: float) -> None:
        if not self.settings.moving_goal:
            self.goal_x = self.base_goal_x
            self.goal_y = self.base_goal_y
            return
        self._goal_phase += dt * .75
        base_x, base_y = self.base_goal_x, self.base_goal_y
        lo, hi = next((lo, hi) for lo, hi in GOAL_SIDES if lo <= base_x <= hi)
        amplitude_x = min(75., base_x-lo, hi-base_x)
        amplitude_y = min(95., base_y-540., 890.-base_y)
        self.goal_x = base_x + amplitude_x * math.sin(self._goal_phase)
        self.goal_y = base_y + amplitude_y * math.sin(self._goal_phase*1.3 + .8)

    def _spawn(self) -> None:
        if len(self.balls) >= self.settings.max_balls:
            return
        radius = self.settings.ball_radius
        # No random horizontal jitter: the goal must not catch unassisted balls.
        self.balls.append(Ball(self.next_id, SPAWN_X, 18., 0., 0., radius))
        self.next_id += 1
        self.total_spawned += 1

    def _collide_rectangles(self, ball: Ball) -> None:
        for poly in self.obstacles.values():
            if ball.x < min(p[0] for p in poly)-ball.radius or ball.x > max(p[0] for p in poly)+ball.radius:
                continue
            if ball.y < min(p[1] for p in poly)-ball.radius or ball.y > max(p[1] for p in poly)+ball.radius:
                continue
            nearest = None
            min_sq = float("inf")
            for a, b in zip(poly, poly[1:]+poly[:1]):
                px, py = _closest_segment(ball.x, ball.y, a, b)
                sq = (ball.x-px)**2+(ball.y-py)**2
                if sq < min_sq:
                    min_sq, nearest = sq, (px, py, a, b)
            inside = _point_inside(ball.x, ball.y, poly)
            if not inside and min_sq >= ball.radius**2:
                continue
            px, py, a, b = nearest
            distance = math.sqrt(min_sq)
            if distance > 1e-8:
                nx, ny = (ball.x-px)/distance, (ball.y-py)/distance
                if inside:
                    nx, ny = -nx, -ny
            else:
                dx, dy = b[0]-a[0], b[1]-a[1]
                size = math.hypot(dx, dy)
                if size < 1e-8:
                    continue
                nx, ny = -dy/size, dx/size
                if ball.vx*nx+ball.vy*ny > 0:
                    nx, ny = -nx, -ny
            penetration = (ball.radius+distance) if inside else (ball.radius-distance)
            ball.x += nx*(penetration+.1)
            ball.y += ny*(penetration+.1)
            speed = ball.vx*nx+ball.vy*ny
            if speed < 0:
                ball.vx -= 1.72*speed*nx
                ball.vy -= 1.72*speed*ny
                # A little tangent friction keeps the trajectory varied.
                tangent = ball.vx*(-ny)+ball.vy*nx
                ball.vx += ny*tangent*.035
                ball.vy -= nx*tangent*.035

    def _collide_balls(self) -> None:
        # Spatial grid avoids O(n²) comparisons for the capped stream.
        cell = 54.
        grid: dict[tuple[int, int], list[Ball]] = {}
        for ball in self.balls:
            x, y = int(ball.x//cell), int(ball.y//cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in grid.get((x+dx, y+dy), ()):
                        ox, oy = ball.x-other.x, ball.y-other.y
                        sq = ox*ox+oy*oy
                        limit = ball.radius+other.radius
                        if sq < limit*limit:
                            distance = math.sqrt(sq)
                            nx, ny = (ox/distance, oy/distance) if distance > .0001 else (1., 0.)
                            overlap = (limit-distance)*.5+.02
                            ball.x += nx*overlap; ball.y += ny*overlap
                            other.x -= nx*overlap; other.y -= ny*overlap
                            relative = (ball.vx-other.vx)*nx+(ball.vy-other.vy)*ny
                            if relative < 0:
                                impulse = -(1+.76)*relative*.5
                                ball.vx += impulse*nx; ball.vy += impulse*ny
                                other.vx -= impulse*nx; other.vy -= impulse*ny
            grid.setdefault((x, y), []).append(ball)

    def step(self, dt: float) -> None:
        if self.finished:
            return
        self.elapsed += dt
        self._goal_position(dt)
        self.spawn_clock += dt
        if self.spawn_clock >= self.settings.spawn_interval:
            self.spawn_clock -= self.settings.spawn_interval
            self._spawn()
        alive = []
        for ball in self.balls:
            ball.age += dt
            ball.vy += 940.*dt
            ball.vx *= .9995
            ball.vy *= .9995
            ball.x += ball.vx*dt
            ball.y += ball.vy*dt
            self._collide_rectangles(ball)
            if (ball.x-self.goal_x)**2+(ball.y-self.goal_y)**2 <= (self.goal_radius+ball.radius*.33)**2:
                self.score += 1
                self.last_hit = self.elapsed
                continue
            if (-100 <= ball.x <= W+100 and -100 <= ball.y <= H+100 and ball.age <= 12):
                alive.append(ball)
            else:
                self.total_culled += 1
        self.balls = alive
        self._collide_balls()
        if self.score >= self.settings.target_hits:
            self.finished = True
            self.balls.clear()

    def snapshot(self) -> dict:
        return {
            "balls": [[round(b.x/W, 5), round(b.y/H, 5), b.radius, round(b.vx/W, 4), round(b.vy/H, 4)] for b in self.balls],
            "goal": [round(self.goal_x/W, 5), round(self.goal_y/H, 5), self.goal_radius],
            "score": self.score,
            "target": self.settings.target_hits,
            "hits_fx": max(0., 1.-(self.elapsed-self.last_hit)/.38),
            "culled": self.total_culled,
            "spawned": self.total_spawned,
            "obstacles": len(self.obstacles),
        }


class GameEngine:
    """Owns all gameplay on one 120Hz thread; displays only read/push snapshots."""
    def __init__(self, objects_provider: Callable[[], list[dict]], publish: Callable[[dict], None], config: dict | None = None, start_worker: bool = True):
        self.lock = threading.RLock()
        self.objects_provider = objects_provider
        self.publish = publish
        self.settings = GameSettings.parse(config or {})
        self.available_games = {"hole": "Шарики и лунка"}
        self.current_game = "hole"
        self.phase = "idle"
        self.round: HoleRound | None = None
        self.rounds = 0
        self._complete_at = 0.
        self._last_obstacles = -1.
        self._last_emit = -1.
        self._frames = 0
        self._recent_fps = 0.
        self._tick_cost_ms = 0.
        self._last_tick = 0.
        self._snapshot = self._compose()
        self.running = True
        self.worker = threading.Thread(target=self._loop, daemon=True, name="interactive-surface-game") if start_worker else None
        if self.worker:
            self.worker.start()

    def _compose(self) -> dict:
        result = self.round.snapshot() if self.round else {"balls": [], "goal": [self.settings.goal_x, self.settings.goal_y, 45.], "score": 0, "target": self.settings.target_hits, "hits_fx": 0., "culled": 0, "spawned": 0, "obstacles": 0}
        return {**result, "game": self.current_game, "phase": self.phase, "round_number": self.rounds,
                "settings": asdict(self.settings), "physics_fps": round(self._recent_fps, 1),
                "physics_ms": round(self._tick_cost_ms, 3), "updated": time.monotonic()}

    def _start_locked(self, game: str = "hole") -> None:
        if game not in self.available_games:
            raise ValueError("Неизвестная игра")
        self.current_game = game
        self.round = HoleRound(self.settings)
        if not self.settings.goal_manual:
            self.round.randomize_goal(side=self.rounds % 2)
        self.phase = "playing"
        self.rounds += 1
        self._complete_at = 0.
        self._last_obstacles = -1.
        self._snapshot = self._compose()

    def start(self, game: str = "hole") -> dict:
        with self.lock:
            self._start_locked(game)
            return self.state()

    def stop(self) -> dict:
        with self.lock:
            self.phase = "idle"
            self.round = None
            self._snapshot = self._compose()
            return self.state()

    def configure(self, updates: dict) -> dict:
        with self.lock:
            data = asdict(self.settings)
            data.update(updates)
            if ("goal_x" in updates or "goal_y" in updates) and "goal_manual" not in updates:
                data["goal_manual"] = True
            new = GameSettings.parse(data)
            self.settings = new
            if self.round:
                self.round.settings = new
                # The manual position is immediately effective when movement is off.
                if "goal_x" in updates or "goal_y" in updates or "goal_manual" in updates:
                    if "goal_x" in updates or "goal_y" in updates:
                        new.goal_manual = True
                        self.settings.goal_manual = True
                    self.round.randomize_goal()
                if "ball_radius" in updates:
                    for ball in self.round.balls:
                        ball.radius = new.ball_radius
                if len(self.round.balls) > new.max_balls:
                    self.round.balls = self.round.balls[-new.max_balls:]
            self._snapshot = self._compose()
            return self.state()

    def state(self) -> dict:
        return {k: v for k, v in self._snapshot.items() if k != "updated"}

    def tick(self, dt: float = DT) -> None:
        with self.lock:
            if self.phase == "playing" and self.round:
                self.round.step(dt)
                if self.round.finished:
                    self.phase = "won"
                    self._complete_at = time.monotonic()
            elif self.phase == "won" and self.round and self.settings.cycle_mode != "manual":
                if time.monotonic() - self._complete_at >= 2.7:
                    if self.settings.cycle_mode == "sequence":
                        playlist = list(self.settings.playlist)
                        pos = playlist.index(self.current_game) if self.current_game in playlist else -1
                        next_game = playlist[(pos+1) % len(playlist)]
                    else:
                        next_game = self.current_game
                    self._start_locked(next_game)
            self._snapshot = self._compose()

    def _loop(self) -> None:
        previous = time.monotonic()
        accumulator = 0.
        while self.running:
            now = time.monotonic()
            # Cap catch-up and drop excess time after OS stall (no spiral of death).
            accumulator += min(now-previous, .075)
            previous = now
            loops = 0
            while accumulator >= DT and loops < 6:
                begin = time.perf_counter()
                if now - self._last_obstacles >= 1/30.:
                    try:
                        objects = self.objects_provider()
                        with self.lock:
                            if self.round:
                                self.round.set_obstacles(objects)
                    except (ValueError, KeyError, TypeError):
                        pass
                    self._last_obstacles = now
                self.tick(DT)
                cost = (time.perf_counter()-begin)*1000.
                self._tick_cost_ms = self._tick_cost_ms*.93+cost*.07
                accumulator -= DT
                loops += 1
                self._frames += 1
            if loops >= 6 and accumulator >= DT:
                accumulator = 0.
            if self._last_tick:
                delta = now-self._last_tick
                if delta >= 1:
                    self._recent_fps = self._frames/delta
                    self._frames = 0
                    self._last_tick = now
            else:
                self._last_tick = now
            if now-self._last_emit >= 1/60:
                with self.lock:
                    frame = self._snapshot.copy()
                try:
                    self.publish(frame)
                except (OSError, BrokenPipeError):
                    pass
                self._last_emit = now
            time.sleep(.002)

    def close(self) -> None:
        self.running = False
        if self.worker:
            self.worker.join(timeout=2)
