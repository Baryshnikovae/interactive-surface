"""SkyHop regressions: physics, isolated settings, lifecycle and rendering."""
import math
import pytest

from interactive_surface.game import DT, GameEngine, GameSettings
from interactive_surface.jump_game import JumpRound, sticker_top


def test_settings_validate_without_changing_classic_defaults():
    default = GameSettings.parse({})
    assert default.theme == "classic" and default.playlist == ("hole",)
    assert GameSettings.parse({"jump_theme": "neon", "jump_difficulty": "hard"}).jump_theme == "neon"
    for bad in (
        {"jump_theme": "unknown"}, {"jump_difficulty": "extreme"},
        {"jump_height": 100}, {"jump_height": 3000},
        {"jump_coins": 0}, {"jump_coins": 30},
        {"jump_sound": "yes"}, {"jump_auto_restart": 1},
    ):
        with pytest.raises(ValueError):
            GameSettings.parse(bad)


def test_sticker_top_is_orientation_independent():
    corners = [[.45,.70],[.55,.70],[.55,.73],[.45,.73]]
    expected = sticker_top(corners)
    assert expected is not None
    for shift in range(4):
        shifted = corners[shift:]+corners[:shift]
        assert sticker_top(shifted) == expected
        assert sticker_top(list(reversed(shifted))) == expected


def test_jump_is_one_shot_and_steered_by_sticker_angle():
    settings = GameSettings.parse({})
    game = JumpRound(settings)
    # The sticker is positioned under a descending hero, just above his feet.
    game.hero.x, game.hero.y = 800., 340.
    game.hero.vy = -650.
    game.hero.vx = 0.
    game.obstacles = {3: sticker_top(JumpRound._demo_object(800, 705, 18)["corners"])}
    game.step(DT)
    assert game.bounces == 1
    assert game.hero.vy > 0
    assert game.hero.vx > 0
    for _ in range(15):
        game.step(DT)
    assert game.bounces == 1


def test_no_bounce_when_rising_or_missing():
    game = JumpRound(GameSettings())
    game.hero.x, game.hero.y, game.hero.vy = 800., 300., 500.
    game.obstacles = {1: sticker_top(JumpRound._demo_object(800, 705, 0)["corners"])}
    game.step(DT)
    assert game.bounces == 0
    game.hero.x, game.hero.vy = 1200., -400.
    game.step(DT)
    assert game.bounces == 0


def test_stale_tracker_sticker_is_not_collidable():
    game = JumpRound(GameSettings())
    corners = JumpRound._demo_object(800, 700, 0)["corners"]
    game.set_obstacles([{"id": 1, "corners": corners, "last_seen_age_ms": 200}])
    assert not game.obstacles
    game.set_obstacles([{"id": 1, "corners": corners, "last_seen_age_ms": 20}])
    assert 1 in game.obstacles


def test_world_camera_does_not_scroll_real_sticker():
    game = JumpRound(GameSettings())
    game.camera = 330.
    game.set_obstacles([{"id": 1, "corners": JumpRound._demo_object(800, 700, 0)["corners"]}])
    assert game.obstacles[1][0][1] == pytest.approx(687.)
    assert game.snapshot()["jump"]["camera"] == 330.


def test_coin_collection_and_finish():
    game = JumpRound(GameSettings.parse({"jump_height": 1100, "jump_coins": 4}))
    coin = game.coins[0]
    game.hero.x, game.hero.y = coin["x"], coin["world_y"]
    game.hero.vy = 0.
    game.step(DT)
    assert game.score == 1
    game.step(DT)
    assert game.score == 1
    game.hero.y = game.level_height - 1
    game.hero.vy = 600.
    game.step(DT)
    assert game.finished
    assert game.score <= game.settings.jump_coins


def test_engine_preview_demo_and_game_isolation():
    engine = GameEngine(lambda: [], lambda _: None, start_worker=False)
    try:
        assert "hole" in engine.available_games and "jump" in engine.available_games
        preview = engine.preview("jump")
        assert preview["phase"] == "preview" and "jump" in preview
        demo = engine.start_demo("jump")
        assert demo["game"] == "jump" and demo["demo"]
        for _ in range(360):
            engine.tick(DT)
        assert engine.state()["jump"]["bounces"] > 0
        engine.start("hole")
        assert engine.state()["game"] == "hole"
        assert "jump" not in engine.state()
    finally:
        engine.close()


def test_qt_painter_and_browser_projector_routes():
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QImage, QPainter
    from interactive_surface.jump_render import paint_jump
    game = JumpRound(GameSettings.parse({"jump_theme": "neon"}), preview=True)
    state = {"game": "jump", "phase": "preview",
             "settings": {"jump_theme": "neon"}, **game.snapshot()}
    image = QImage(1600, 1000, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        paint_jump(painter, state)
    finally:
        painter.end()
    assert not image.isNull()
