"""Gameplay invariants and end-to-end control API without real hardware."""
from __future__ import annotations

import math
import time

import pytest
from fastapi.testclient import TestClient

from interactive_surface.controller import Controller
from interactive_surface.game import Ball, GameEngine, GameSettings, HoleRound, DT, safe_goal
from interactive_surface.storage import Store
from interactive_surface.web import create_app


def test_settings_reject_center_line_and_bad_visuals():
    with pytest.raises(ValueError): GameSettings.parse({"goal_x": .5})
    with pytest.raises(ValueError): GameSettings.parse({"goal_x": .73, "goal_y": .2})
    with pytest.raises(ValueError): GameSettings.parse({"ball_color": "pink"})
    with pytest.raises(ValueError): GameSettings.parse({"ball_radius": 500})
    with pytest.raises(ValueError): GameSettings.parse({"cycle_mode": "random"})
    with pytest.raises(ValueError): GameSettings.parse({"visual_style": "bad"})
    with pytest.raises(ValueError): GameSettings.parse({"playlist": ["unknown"]})
    assert GameSettings.parse({"goal_x": .22, "goal_y": .7}).ball_radius == 14


def test_goal_2d_movement_never_crosses_spawn_lane():
    for x in (.13, .22, .31, .70, .80, .88):
        config = GameSettings.parse({"goal_x": x, "goal_y": .71})
        mode = HoleRound(config, random_seed=0)
        observed_x, observed_y = set(), set()
        for _ in range(1200):
            mode._goal_position(DT)
            nx, ny = mode.goal_x / 1600, mode.goal_y / 1000
            assert safe_goal(nx,ny)
            assert abs(nx-.5) > .15
            observed_x.add(round(nx,4))
            observed_y.add(round(ny,4))
        assert len(observed_y) > 10
        if x in (.22, .80): assert len(observed_x) > 10


def test_goal_can_be_static_or_manual():
    mode = HoleRound(GameSettings.parse({"moving_goal": False,"goal_x": .18,"goal_y": .84}))
    for _ in range(100): mode.step(DT)
    assert mode.goal_x == pytest.approx(.18 * 1600)
    assert mode.goal_y == pytest.approx(840)


def test_cull_and_limit_balls_during_long_session():
    mode = HoleRound(GameSettings.parse({"max_balls": 10, "spawn_interval": .20}))
    for _ in range(120 * 28):
        mode.step(DT)
        assert len(mode.balls) <= 10
    assert mode.total_culled > 0
    assert mode.total_spawned > 12
    assert all(b.age <= 12 for b in mode.balls)


def test_rectangular_collider_deflects_ball():
    mode = HoleRound(GameSettings.parse({"moving_goal": False}))
    mode.set_obstacles([{"id": 5,"corners": [[.30,.48],[.70,.48],[.70,.50],[.30,.50]]}])
    mode.balls = [Ball(99, 800, 455, 0, 450, 14)]
    for _ in range(12): mode.step(DT)
    assert mode.balls[0].vy < 0
    assert mode.balls[0].y < 520


def test_unchanged_rectangles_reuse_geometry_and_clear_on_disappear():
    mode = HoleRound(GameSettings())
    obj = [{"id": 1, "corners": [[.1,.2],[.2,.2],[.2,.22],[.1,.22]]}]
    mode.set_obstacles(obj)
    polygon = mode.obstacles[1]
    mode.set_obstacles([{"id": 1, "corners": [[x+.00001,y] for x,y in obj[0]["corners"]]}])
    assert mode.obstacles[1] is polygon
    mode.set_obstacles([])
    assert mode.obstacles == {}


def test_score_and_success():
    mode = HoleRound(GameSettings.parse({"target_hits": 1,"moving_goal": False}))
    mode.balls=[Ball(1, mode.goal_x, mode.goal_y, 0,0,14)]
    mode.step(DT)
    assert mode.finished and mode.score == 1
    assert not mode.balls


def test_scheduler_manual_repeat_sequence(monkeypatch):
    engine=GameEngine(lambda: [], lambda frame: None, start_worker=False)
    try:
        engine.start()
        first_round = engine.rounds
        engine.round.finished=True
        engine.tick()
        assert engine.state()["phase"] == "won"
        # Manual mode does not progress after win.
        engine._complete_at -= 4
        engine.tick()
        assert engine.rounds == first_round
        engine.configure({"cycle_mode": "repeat"})
        engine.tick()
        assert engine.state()["phase"] == "playing" and engine.rounds == first_round+1
        engine.round.finished=True
        engine.tick()
        engine.configure({"cycle_mode": "sequence", "playlist": ["hole"]})
        engine._complete_at -= 4
        engine.tick()
        assert engine.rounds == first_round+2
    finally:
        engine.close()


def test_controller_games_virtual_end_to_end(tmp_path):
    controller=Controller(Store(tmp_path/'calibration.json'))
    headers={"X-Control-Token":"test-key"}
    try:
        with TestClient(create_app(controller=controller,token="test-key")) as client:
            assert client.get('/games').status_code==200
            assert client.get('/api/game/state').status_code==401
            assert client.get('/api/games',headers=headers).json()['games']['hole']
            fail=client.post('/api/game/start',headers=headers,json={"game":"hole"})
            assert fail.status_code==400
            assert client.post('/api/camera/select',headers=headers,json={"id":"simulation"}).status_code==200
            assert client.post('/api/display/open',headers=headers,json={"id":"virtual"}).status_code==200
            assert client.post('/api/calibration/verify',headers=headers).status_code==200
            assert client.post('/api/calibration/complete',headers=headers).status_code==200
            assert client.post('/api/recognition/background',headers=headers,json={"background":"black"}).status_code==200
            assert client.post('/api/recognition/capture',headers=headers).status_code==200
            learned=client.post('/api/recognition/learn',headers=headers,json={"points":[[180/1280,155/720]]})
            assert learned.status_code==200, learned.text
            assert client.post('/api/recognition/finish',headers=headers).status_code==200
            updated=client.post('/api/game/settings',headers=headers,json={"changes":{"cycle_mode":"repeat","visual_style":"flat","ball_design":"comet","ball_color":"#ff33aa","ball_radius":20,"goal_x":.22,"goal_y":.79}})
            assert updated.status_code==200,updated.text
            game=client.post('/api/game/start',headers=headers,json={"game":"hole"})
            assert game.status_code==200,game.text
            assert game.json()['phase']=='playing'
            time.sleep(.15)
            assert client.get('/api/projector/visual',headers=headers).json()['mode']=='game'
            assert client.get('/api/game/state',headers=headers).json()['settings']['goal_x']==.22
            assert client.post('/api/game/settings',headers=headers,json={"changes":{"goal_x":.5}}).status_code==400
            assert client.post('/api/game/stop',headers=headers).status_code==200
            assert controller.store.read()['game']['visual_style']=='flat'
            assert client.post('/api/recognition/background',headers=headers,json={"background":"white"}).status_code==200
            assert client.post('/api/game/start',headers=headers,json={"game":"hole"}).status_code==400
    finally:
        controller.close()
