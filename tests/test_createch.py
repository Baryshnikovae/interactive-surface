"""Createch theme and preview/demo invariants."""
from __future__ import annotations

import pytest

from interactive_surface.game import Ball, DT, GameEngine, GameSettings, HoleRound


def test_theme_defaults_and_validation():
    assert GameSettings.parse({}).theme == "classic"
    assert GameSettings.parse({"theme": "createch"}).theme == "createch"
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
