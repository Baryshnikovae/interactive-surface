"""Createch theme and preview/demo invariants."""
from __future__ import annotations

import pytest
import math

from interactive_surface.game import Ball, DT, GameEngine, GameSettings, HoleRound


def test_theme_defaults_and_validation():
    assert GameSettings.parse({}).theme == "classic"
    assert GameSettings.parse({"theme": "createch"}).theme == "createch"
    assert GameSettings.parse({"theme": "createch"}).ball_radius == 19
    assert GameSettings.parse({}).ball_radius == 14
    with pytest.raises(ValueError):
        GameSettings.parse({"theme": "other"})


def test_preview_freezes_and_demo_uses_real_physics():
    game = GameEngine(lambda: [], lambda _: None, start_worker=False)
    try:
        preview = game.preview()
        assert preview["phase"] == "preview"
        assert preview["demo"] is False
        assert len(preview["balls"]) == 4
        before = game.state()["balls"]
        for _ in range(30):
            game.tick(DT)
        assert game.state()["balls"] == before
        game.configure({"theme": "createch", "target_hits": 20})
        demo = game.start_demo()
        assert demo["phase"] == "playing"
        assert demo["demo"] is True
        assert game.round.demo
        for _ in range(120 * 8):
            game.tick(DT)
        assert game.round.total_spawned > 2
        assert game.state()["settings"]["theme"] == "createch"
        stopped = game.stop()
        assert stopped["phase"] == "idle"
        assert not stopped["demo"]
    finally:
        game.close()


def test_createch_bucket_requires_entry_from_above():
    settings = GameSettings.parse({"theme": "createch", "moving_goal": False, "target_hits": 5})
    r = HoleRound(settings, random_seed=7)
    r.balls = [Ball(9, r.goal_x + 100, r.goal_y, 0, 0, 14)]
    r.step(DT)
    assert r.score == 0
    r.balls = [Ball(10, r.goal_x, r.goal_y - 3, 0, 170, 14)]
    r.step(DT)
    assert r.score == 1


def test_classic_original_goal_collision():
    r = HoleRound(GameSettings.parse({"theme": "classic", "moving_goal": False}))
    r.balls = [Ball(10, r.goal_x, r.goal_y, 0, 0, 14)]
    r.step(DT)
    assert r.score == 1


def test_preview_and_demo_api_without_calibration(tmp_path):
    from fastapi.testclient import TestClient
    from interactive_surface.controller import Controller
    from interactive_surface.storage import Store
    from interactive_surface.web import create_app

    controller = Controller(Store(tmp_path / "profile.json"))
    headers = {"X-Control-Token": "createch-test"}
    try:
        with TestClient(create_app(controller=controller, token="createch-test")) as client:
            settings = client.post("/api/game/settings", headers=headers,
                                   json={"changes": {"theme": "createch"}})
            assert settings.status_code == 200
            assert settings.json()["settings"]["theme"] == "createch"
            assert controller.theme_store.read()["theme"] == "createch"
            preview = client.post("/api/game/preview", headers=headers, json={})
            assert preview.status_code == 200
            assert preview.json()["phase"] == "preview"
            assert client.get("/api/projector/visual", headers=headers).json()["game"]["phase"] == "preview"
            demo = client.post("/api/game/demo/start", headers=headers, json={})
            assert demo.status_code == 200
            assert demo.json()["demo"] is True
            assert client.get("/assets/createch-director.svg").status_code == 200
            portrait = client.get("/assets/createch-director.png")
            assert portrait.status_code == 200
            assert portrait.content.startswith(b"\x89PNG\r\n\x1a\n")
            # The original GitHub asset is served untouched, with no
            # transcoding, lossy resizing or separate ZIP deployment.
            from interactive_surface import createch_render as renderer
            original_path = renderer.ASSET_ROOT / "createch-director-original.png"
            original_response = client.get("/assets/createch-director-original.png")
            assert original_response.status_code == 200
            assert original_response.headers["content-type"].startswith("image/png")
            assert original_response.content == original_path.read_bytes()
            assert client.post("/api/game/stop", headers=headers, json={}).json()["phase"] == "idle"
            assert client.post("/api/game/preview", json={}).status_code == 401
    finally:
        controller.close()


def test_demo_reliably_catches_glyphs_and_respects_classic_radius():
    with pytest.raises(ValueError):
        GameSettings.parse({"theme": "classic", "ball_radius": 38})
    assert GameSettings.parse({"theme": "createch", "ball_radius": 38}).ball_radius == 38
    game = GameEngine(lambda: [], lambda _: None,
                      config={"theme": "createch", "ball_radius": 23, "target_hits": 20},
                      start_worker=False)
    try:
        game.start_demo()
        assert game.round.demo
        observations = []
        for i in range(120 * 22):
            game.tick(DT)
            if i % 120 == 0 and game.round.balls:
                ball = game.round.balls[0]
                observations.append((round(ball.x), round(ball.y),round(ball.vx),round(ball.vy), round(game.round.goal_x)))
            if game.round.score:
                break
        assert game.round.score > 0, f"Auto Demo must demonstrate actual catches. Trajectory: {observations}"
    finally:
        game.close()


def test_demo_sticker_deflects_centre_spawn_in_real_collision_solver():
    mode = HoleRound(GameSettings.parse({"theme": "createch", "ball_radius": 23}),
                     random_seed=20261106, demo=True)
    assert mode.snapshot()["demo_stickers"]
    observed_contact = False
    for _ in range(120 * 8):
        mode.step(DT)
        if any(ball.vx < -75 for ball in mode.balls):
            observed_contact = True
            break
    assert observed_contact, "Demo sticker must visibly redirect the falling K."


def test_createch_qt_renderer_draws_generated_portrait_and_sticker():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    app = QGuiApplication.instance() or QGuiApplication([])
    from interactive_surface.createch_render import paint_createch
    from pathlib import Path
    import interactive_surface

    image = Path(interactive_surface.__file__).parent / "static" / "createch-director.png"
    assert image.is_file(), "Packaged Createch portrait PNG missing"
    frame = QImage(1600, 1000, QImage.Format.Format_ARGB32)
    frame.fill(0)
    p = QPainter(frame)
    try:
        paint_createch(p, {"phase": "playing", "demo": True,
                           "goal": [.25,.705,31.], "balls": [[.5,.33,23.,0.,.3,37.]],
                           "demo_stickers": [[[.43,.5],[.57,.46],[.57,.48],[.43,.52]]]},
                      dark=True)
    finally:
        p.end()
    assert frame.pixelColor(30, 500).alpha() > 0


def test_autodemo_is_not_an_aimbot_and_sticker_rotates():
    settings = GameSettings.parse({"theme": "createch", "moving_goal": True,
                                   "spawn_interval": .42, "target_hits": 50})
    game = HoleRound(settings, random_seed=20261106, demo=True)
    assert abs(game.demo_angle - 13) < 0.1
    sticker_width = math.dist(game.obstacles[-101][0],game.obstacles[-101][1])
    assert 90 <= sticker_width <= 94
    assert game.snapshot()["demo_stickers"]
    initial_base = game.base_goal_x
    goal_positions=[]
    for i in range(120 * 10):
        game.step(DT)
        if i % 60 == 0:
            goal_positions.append(game.goal_x)
    assert game.total_spawned >= 18, "Demo must have a continuous dense vertical stream"
    assert max(goal_positions)-min(goal_positions) <= 45, "Receiver must only drift, not chase"
    assert abs(game.base_goal_x-initial_base)<.01
    assert -50.1 <= game.demo_angle <= -49.9, "Sticker must visibly rotate toward target"
    assert all(b.radius==settings.ball_radius for b in game.balls)


def test_createch_is_a_center_stream_without_auto_aiming():
    settings = GameSettings.parse({"theme": "createch", "target_hits": 50,
                                   "moving_goal": True, "spawn_interval": .42})
    classic = HoleRound(GameSettings.parse({"theme": "classic", "spawn_interval": .42}),
                        random_seed=4)
    branded = HoleRound(settings, random_seed=4)
    for _ in range(120 * 3):
        branded.step(DT)
        classic.step(DT)
    assert branded.total_spawned >= 10, "Createch needs a dense continuous glyph stream"
    assert classic.total_spawned <= 8, "Classic must keep its original spawn rate"
    assert all(abs(b.x - 800.) < 0.01 for b in branded.balls), (
        "Without a sticker the stream must not aim itself at the director"
    )
    assert branded.score == 0, "The collector must never move under a falling stream"


def test_real_createch_gameplay_uses_detected_sticker_not_demo_assist():
    """A normal round must score from the *real recognition polygon* only.

    Explicitly run with demo=False, no synthetic sticker, no camera and no
    browser. This is the same rectangular collision code used by the server
    after the real camera reports four wall-normalized corners.
    """
    settings = GameSettings.parse({
        "theme": "createch", "goal_manual": True,
        "goal_x": 425. / 1600., "goal_y": .72,
        "moving_goal": False, "target_hits": 50,
    })
    assert settings.ball_radius == 19
    real = GameEngine(lambda: [], lambda _: None,
                      config=settings.__dict__, start_worker=False)
    try:
        state = real.start()
        assert state["phase"] == "playing" and state["demo"] is False
        assert real.round.obstacles == {}
        for _ in range(120 * 3):
            real.tick(DT)
        assert real.round.score == 0, "Without a sticker, letters must miss"
        corners = HoleRound._sticker_corners(800., 520., -50.)
        real.round.set_obstacles([{
            "id": 412, "corners": [[x / 1600., y / 1000.] for x, y in corners]
        }])
        assert 412 in real.round.obstacles
        assert not real.round.demo
        for _ in range(120 * 18):
            real.tick(DT)
        assert real.round.total_spawned >= 30
        assert real.round.score > 0, (
            "Real Createch must catch using the actual physical sticker collider"
        )
        assert real.state()["settings"]["ball_radius"] == 19
    finally:
        real.close()


def test_real_projector_createch_uses_same_game_state_and_win_text(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from interactive_surface import createch_render as renderer
    from interactive_surface.game_render import paint_game

    app = QGuiApplication.instance() or QGuiApplication([])
    received = []
    original = renderer._text

    def capture(painter, text, *args, **kwargs):
        received.append(text)
        return original(painter, text, *args, **kwargs)

    monkeypatch.setattr(renderer, "_text", capture)
    frame = QImage(800, 500, QImage.Format.Format_ARGB32)
    frame.fill(0)
    snapshot = {"phase": "won", "settings": {"theme": "createch",
                "cycle_mode": "repeat"}, "score": 5, "target": 5,
                "goal": [.265625, .72, 31.], "balls": []}
    painter = QPainter(frame)
    try:
        paint_game(painter, snapshot,
                   [[0., 0.], [1., 0.], [1., 1.], [0., 1.]],
                   frame.width(), frame.height())
    finally:
        painter.end()
    assert "ОТЛИЧНО!" in received
    assert "Следующий раунд скоро начнётся" in received
    assert "ПОЙМАНО!" not in received


def test_live_theme_switch_does_not_change_classic_size():
    game = GameEngine(lambda: [], lambda _: None, start_worker=False)
    try:
        assert game.state()["settings"]["ball_radius"] == 14
        updated = game.configure({"theme": "createch"})
        assert updated["settings"]["ball_radius"] == 19
        updated = game.configure({"theme": "classic"})
        assert updated["settings"]["ball_radius"] == 14
    finally:
        game.close()


def test_controller_restores_smaller_glyphs_before_browser_opens(tmp_path):
    from interactive_surface.controller import Controller
    from interactive_surface.storage import Store

    for previous_radius in (14, 23):
        store = Store(tmp_path / f"profile-{previous_radius}.json")
        store.write({"game": {"theme": "createch",
                              "ball_radius": previous_radius}})
        controller = Controller(store)
        try:
            assert controller.game.state()["settings"]["theme"] == "createch"
            assert controller.game.state()["settings"]["ball_radius"] == 19
        finally:
            controller.close()


def test_physical_qt_renderer_prefers_high_quality_png(monkeypatch, tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QColor, QImage
    from interactive_surface import createch_render as renderer

    app = QGuiApplication.instance() or QGuiApplication([])
    lo = QImage(8, 10, QImage.Format.Format_ARGB32)
    lo.fill(QColor("#ec0000"))
    assert lo.save(str(tmp_path / "createch-director.png"))
    hi = QImage(24, 30, QImage.Format.Format_ARGB32)
    hi.fill(QColor("#06aeff"))
    assert hi.save(str(tmp_path / "createch-director-hq.png"))
    monkeypatch.setattr(renderer, "ASSET_ROOT", tmp_path)
    monkeypatch.setattr(renderer, "_portrait", None)
    monkeypatch.setattr(renderer, "_fallback", None)
    image, _ = renderer._sprite()
    assert image.size().width() == 24
    assert image.pixelColor(0, 0) == QColor("#06aeff")


def test_createch_prefers_exact_original_over_legacy_portraits(monkeypatch, tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QColor, QImage
    from interactive_surface import createch_render as renderer

    app = QGuiApplication.instance() or QGuiApplication([])
    samples = [
        ("createch-director-original.png", "#16cd23", (1086, 1448)),
        ("createch-director-hq.png", "#132ed9", (48, 72)),
        ("createch-director.png", "#c82324", (16, 24)),
    ]
    for filename, color, (width, height) in samples:
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor(color))
        assert image.save(str(tmp_path / filename))
    monkeypatch.setattr(renderer, "ASSET_ROOT", tmp_path)
    monkeypatch.setattr(renderer, "_portrait", None)
    monkeypatch.setattr(renderer, "_fallback", None)
    actual, _ = renderer._sprite()
    assert (actual.width(), actual.height()) == (1086, 1448)
    assert actual.pixelColor(0, 0) == QColor("#16cd23")


def test_browser_viewer_uses_exact_original_and_matches_qt_bucket_alignment():
    from interactive_surface import createch_render as renderer
    source = (renderer.ASSET_ROOT / "virtual.html").read_text(encoding="utf-8")
    assert source.index("/assets/createch-director-original.png") < source.index(
        "/assets/createch-director-hq.png")
    assert "const w=207,h=276,x=gx-.61*w,y=gy-.31*h" in source
    import inspect
    qt_source = inspect.getsource(renderer._actor)
    assert "w, h = 207., 276." in qt_source
    assert "x - .61*w, y - .31*h" in qt_source
    assert "cc.imageSmoothingQuality='high'" in source
