"""SkyHop: deterministic 120 Hz vertical arcade, driven by detected wall rectangles.

Wall geometry is NEVER scrolled. Only virtual world coordinates (hero, coins and
finish) are offset by the scene camera before collision and rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

W, H = 1600.0, 1000.0
G = 1290.0
RADIUS = 30.0
JUMP_SPEED = 1070.0
MAX_HORIZONTAL = 440.0


@dataclass
class Hero:
    x: float = 800.0
    y: float = 220.0                    # world height, increasing upward
    vx: float = 0.0
    vy: float = JUMP_SPEED


def sticker_top(corners):
    """Find the visually upper long edge, independent of polygon winding.

    All coordinates are wall pixels with y increasing down. Returning a left-
    to-right segment prevents 180-degree orientation flips in recognition.
    """
    if len(corners) != 4:
        return None
    poly = [(float(x) * W, float(y) * H) for x, y in corners]
    if not all(math.isfinite(v) for pt in poly for v in pt):
        return None
    edges = [(poly[i], poly[(i + 1) % 4]) for i in range(4)]
    lengths = [math.dist(*edge) for edge in edges]
    long = [i for i in range(4) if lengths[i] >= max(lengths) * .75]
    if len(long) < 2:
        return None
    choices = sorted((edges[i] for i in long), key=lambda pair: (pair[0][1] + pair[1][1]) / 2)
    a, b = choices[0]
    if b[0] < a[0]:
        a, b = b, a
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx < 25 or abs(math.degrees(math.atan2(dy, dx))) > 65:
        return None
    return a, b


class JumpRound:
    id = "jump"
    title = "SkyHop — Прыжки со стикером"

    def __init__(self, settings, demo=False, preview=False):
        self.settings = settings
        self.demo = demo
        self.elapsed = 0.0
        self.hero = Hero()
        self.camera = 0.0
        self.finished = False
        self.failed = False
        self.score = 0
        self.best = 0
        self.bounces = 0
        self.last_bounce = -100.0
        self.last_coin = -100.0
        self.last_coin_pos = (800.0, 450.0)
        self.last_platform = None
        self.obstacles = {}
        self.level_height = float(settings.jump_height)
        self.coins = self._make_coins(settings.jump_coins)
        self._demo_angle = 0.0
        self._demo_x = 800.0
        self._last_contact = None
        self._contact_cooldown = 0.0
        if preview:
            self.hero = Hero(800., 445., 0., -220.)
            self.camera = 20.
            self.obstacles[-1] = self._demo_object(800., 740., -12.)
            self.coins = self._make_coins(settings.jump_coins)

    def _make_coins(self, count):
        # Deterministic curated layout; moderate horizontal variation makes
        # sticker inclination useful without demanding a lucky random level.
        x_positions = (800, 930, 675, 1040, 755, 870, 575, 1020, 770, 910, 660, 980)
        result = []
        for i in range(count):
            y = 380. + (self.level_height - 510.) * i / max(1, count - 1)
            x = x_positions[i % len(x_positions)]
            result.append({"id": i + 1, "x": float(x), "world_y": y, "taken": False})
        return result

    @staticmethod
    def _demo_object(x, screen_y, angle):
        rad = math.radians(angle)
        cs, sn = math.cos(rad), math.sin(rad)
        points = []
        for xx, yy in ((-78., -13.), (78., -13.), (78., 13.), (-78., 13.)):
            points.append([(x + xx * cs - yy * sn) / W,
                           (screen_y + xx * sn + yy * cs) / H])
        return {"id": -1, "corners": points}

    def set_obstacles(self, objects):
        if self.demo:
            return
        fresh = {}
        for obj in objects:
            try:
                # The tracker intentionally holds occluded shapes for ~360 ms.
                # A stale shape must not become an invisible catching platform.
                if obj.get("last_seen_age_ms", 0) > 170:
                    continue
                top = sticker_top(obj["corners"])
                if top is not None:
                    fresh[int(obj["id"])] = top
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        self.obstacles = fresh

    def _demo_sticker(self, dt):
        # Camera-free auto-player; it merely moves a real-shaped sticker into
        # position. The same swept collision solver creates EVERY bounce.
        target_x = self.hero.x + self.hero.vx * .012
        self._demo_x += (target_x - self._demo_x) * min(1., dt * 18.)
        self._demo_x = min(W - 95., max(95., self._demo_x))
        if self.hero.vy > 0:
            next_coin = next((c for c in self.coins if not c["taken"] and
                              c["world_y"] > self.hero.y), None)
            direction = (next_coin["x"] - self.hero.x) if next_coin else 0.
            desired = min(18., max(-18., direction * .045))
            self._demo_angle += (desired - self._demo_angle) * min(1., dt * 3.)
        demo = self._demo_object(self._demo_x, 765., self._demo_angle)
        self.obstacles[-1] = sticker_top(demo["corners"])

    def _bounce(self, old_x, old_y, new_x, new_y):
        if self.hero.vy >= 0 or self._contact_cooldown > 0:
            return False
        # Feet are RADIUS below hero centre in wall coordinates.
        old_foot = H - (old_y - self.camera) + RADIUS
        new_foot = H - (new_y - self.camera) + RADIUS
        for identity, segment in self.obstacles.items():
            a, b = segment
            slope = (b[1] - a[1]) / (b[0] - a[0])
            hit_x = new_x
            top_y = a[1] + (hit_x - a[0]) * slope
            if not (a[0] - RADIUS * .45 <= hit_x <= b[0] + RADIUS * .45):
                continue
            # Ignore hits from underneath and crossing while the hero rises.
            if old_foot <= top_y + 5. and new_foot >= top_y - 2.:
                # Snap feet precisely above top edge and apply one jump.
                self.hero.y = H + self.camera - top_y + RADIUS
                tilt = max(-.65, min(.65, slope))
                difficulty = {"easy": .78, "normal": 1., "hard": 1.14}[self.settings.jump_difficulty]
                self.hero.vx = max(-MAX_HORIZONTAL, min(MAX_HORIZONTAL,
                    self.hero.vx * .18 + tilt * 600. * difficulty))
                self.hero.vy = JUMP_SPEED * (1.06 if self.settings.jump_difficulty == "easy" else 1.)
                self.last_bounce = self.elapsed
                self.last_platform = identity
                self.bounces += 1
                self._contact_cooldown = .16
                return True
        return False

    def step(self, dt):
        if self.finished or self.failed:
            return
        dt = max(0., min(dt, .05))
        self.elapsed += dt
        self._contact_cooldown = max(0., self._contact_cooldown - dt)
        if self.demo:
            self._demo_sticker(dt)
        h = self.hero
        old_x, old_y = h.x, h.y
        h.vy = max(-1300., h.vy - G * dt)
        h.vx *= math.exp(-.37 * dt)
        h.x += h.vx * dt
        # Soft margins keep the hero visible; no teleportation at the edges.
        if h.x < RADIUS + 46.:
            h.x = RADIUS + 46.
            h.vx = abs(h.vx) * .33
        elif h.x > W - RADIUS - 46.:
            h.x = W - RADIUS - 46.
            h.vx = -abs(h.vx) * .33
        h.y += h.vy * dt
        if h.vy > 0:
            self.camera += max(0., h.y - 640. - self.camera) * min(1., dt * 4.0)
        self._bounce(old_x, old_y, h.x, h.y)
        for coin in self.coins:
            if not coin["taken"] and math.hypot(h.x - coin["x"], h.y - coin["world_y"]) < RADIUS + 22.:
                coin["taken"] = True
                self.score += 1
                self.last_coin = self.elapsed
                self.last_coin_pos = (coin["x"], coin["world_y"])
        if h.y >= self.level_height:
            self.finished = True
            h.vy = 0.
            h.vx = 0.
        elif H - (h.y - self.camera) - RADIUS > H + 72. and h.vy < 0:
            self.failed = True

    def snapshot(self):
        h = self.hero
        screen_y = H - (h.y - self.camera)
        return {
            "balls": [], "goal": [0., 0., 0.], "culled": 0, "spawned": 0,
            "score": self.score, "target": self.settings.jump_coins,
            "jump": {
                "hero": [round(h.x, 3), round(screen_y, 3), RADIUS,
                         round(h.vx, 2), round(-h.vy, 2)],
                "camera": round(self.camera, 3),
                "level_height": self.level_height,
                "progress": round(min(1., h.y / self.level_height), 4),
                "coins": [{"id": c["id"], "x": c["x"],
                           "y": round(H - (c["world_y"] - self.camera), 3)}
                          for c in self.coins if not c["taken"]],
                "total_coins": len(self.coins),
                "bounces": self.bounces,
                "elapsed": round(self.elapsed, 2),
                "bounce_fx": max(0., 1. - (self.elapsed - self.last_bounce) / .26),
                "coin_fx": max(0., 1. - (self.elapsed - self.last_coin) / .33),
                "coin_fx_pos": [self.last_coin_pos[0],
                                H - (self.last_coin_pos[1] - self.camera)],
                "finish_y": round(H - (self.level_height - self.camera), 3),
                "failed": self.failed,
                "stickers": [
                    [[round(x*W, 2), round(y*H, 2)] for x, y in
                     self._demo_object(self._demo_x, 765., self._demo_angle)["corners"]]
                ] if self.demo else [],
            }
        }
