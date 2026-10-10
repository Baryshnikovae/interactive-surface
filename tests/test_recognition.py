import math
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from interactive_surface.geometry import WALL
from interactive_surface.recognition import ColourSettings, StableTracker, detect, learn_colour, project_observations
from interactive_surface.controller import Controller
from interactive_surface.storage import Store
from interactive_surface.web import create_app


QUAD=[[.05,.05],[.95,.05],[.95,.95],[.05,.95]]


def frame(background=(22,25,28), strip=(200,30,200), center=(150,120), size=(120,14), angle=0, hand=False):
    img=np.full((240,320,3),background,np.uint8)
    box=cv2.boxPoints((center,size,angle)).astype(np.int32)
    cv2.fillConvexPoly(img,box,strip)
    if hand:
        cv2.rectangle(img,(center[0]-13,center[1]-16),(center[0]+13,center[1]+16),(100,140,173),-1)
    return img


def test_sample_hue_wraps_red():
    img=np.full((120,200,3),(4,4,4),np.uint8)
    cv2.rectangle(img,(10,30),(95,60),(0,0,255),-1)
    cv2.rectangle(img,(105,30),(195,60),(10,0,255),-1)
    settings=learn_colour(img,[[.2,.4],[.78,.4]])
    assert min(settings.hue,180-settings.hue)<10
    found,mask,_=detect(img,settings,[[0,0],[1,0],[1,1],[0,1]])
    assert len(found)==2


def test_dark_and_nonuniform_wall_colour():
    img=frame(background=(18,22,32),strip=(180,20,182))
    settings=learn_colour(img,[[.50,.5]])
    found,_,_=detect(img,settings,QUAD)
    assert len(found)==1
    img2=frame(background=(32,25,49),strip=(115,14,118),hand=True)
    found,_,_=detect(img2,settings,QUAD)
    assert len(found)>=1


def test_reject_colored_noise():
    img=frame()
    cv2.circle(img,(20,20),2,(200,30,200),-1)
    settings=learn_colour(img,[[.5,.5]])
    found,_,_=detect(img,settings,[[0,0],[1,0],[1,1],[0,1]])
    assert len(found)==1


def test_hold_missing_track_without_jitter():
    tracker=StableTracker(hold_seconds=.35,retire_seconds=.75)
    observation={"a":[.25,.3],"b":[.55,.3],"area":.02}
    first=tracker.update([observation],100.)
    assert len(first)==1
    for i in range(1,5):
        jitter={"a":[.25+i*.0001,.3],"b":[.55+i*.0001,.3],"area":.02}
        second=tracker.update([jitter],100.+i*.03)
        assert second[0]['id']==first[0]['id']
    last=tracker.update([],100.23)
    assert len(last)==1 and last[0]['state']=='occluded'
    assert tracker.update([],101.)==[]


def test_motion_tracks_fast_and_does_not_enforce_aspect():
    tracker=StableTracker()
    one={"a":[.30,.3],"b":[.50,.3],"area":.012}
    original=tracker.update([one],0.)[0]
    moved={"a":[.35,.3],"b":[.55,.3],"area":.012}
    current=tracker.update([moved],.03)[0]
    assert current['id']==original['id']
    assert current['a'][0]>.33
    round_shape=frame(size=(24,24))
    settings=learn_colour(round_shape,[[150/320,120/240]])
    shapes,_,_=detect(round_shape,settings,QUAD)
    assert shapes


def test_project_wall_coordinates_identity():
    h=np.eye(3)
    result=project_observations([{'a':[.1,.2],'b':[.3,.4],'area':.1}],h)
    assert result[0]['a']==[.1,.2]


def test_snapshot_learning_api_and_background_reset(tmp_path):
    controller=Controller(Store(tmp_path/'cal.json'))
    app=create_app(controller=controller,token='key')
    headers={'X-Control-Token':'key'}
    with TestClient(app) as client:
        client.post('/api/camera/select',headers=headers,json={'id':'simulation'})
        client.post('/api/display/open',headers=headers,json={'id':'virtual'})
        client.post('/api/calibration/verify',headers=headers)
        client.post('/api/calibration/complete',headers=headers)
        assert client.get('/recognition').status_code==200
        assert client.post('/api/recognition/background',headers=headers,json={'background':'black'}).status_code==200
        assert client.post('/api/recognition/capture',headers=headers).status_code==200
        assert client.get('/api/recognition/snapshot',headers=headers).headers['content-type']=='image/jpeg'
        assert client.post('/api/recognition/learn',headers=headers,json={'points':[[.01,.01]]}).status_code==400
        assert client.post('/api/recognition/learn',headers=headers,json={'points':[[180/1280,155/720]]}).status_code==200
        assert client.post('/api/recognition/finish',headers=headers).status_code==200
        assert controller.store.read()['recognition']['background']=='black'
        assert client.post('/api/recognition/background',headers=headers,json={'background':'white'}).json()['configured'] is False
        assert client.get('/api/recognition/state').status_code==401
    controller.close()


def test_hand_splits_strip_without_ghost_object():
    original = frame()
    occluded = frame(hand=True)
    settings = learn_colour(original, [[150/320, 120/240]])
    observations, _, _ = detect(original, settings, QUAD)
    cut, _, _ = detect(occluded, settings, QUAD)
    assert len(observations)==1 and len(cut)==2
    tracker=StableTracker()
    stable=tracker.update(observations, 100.)
    tracked=tracker.update(cut, 100.033)
    assert len(tracked)==1
    assert tracked[0]["id"]==stable[0]["id"]
    assert tracked[0]["state"]=="occluded"
    assert np.allclose(tracked[0]["a"], stable[0]["a"])


def test_background_and_colour_settings_validation():
    with pytest.raises(ValueError):
        ColourSettings.from_dict({"hue": 10, "tolerance": 78, "saturation": 20, "value": 30})
    with pytest.raises(ValueError):
        learn_colour(frame(), [[1.4,.5]])


def test_rectangle_geometry_is_exposed_for_game_and_overlay():
    img = frame(center=(160, 120), size=(120, 18), angle=31)
    settings = learn_colour(img, [[160/320, 120/240]])
    found, _, _ = detect(img, settings, QUAD)
    assert len(found) == 1
    assert len(found[0]["corners"]) == 4
    wall = project_observations(found, np.eye(3))
    tracker = StableTracker()
    objects = tracker.update(wall, 100.)
    assert len(objects) == 1
    rectangle = np.asarray(objects[0]["corners"])
    assert rectangle.shape == (4, 2)
    assert np.linalg.norm(rectangle[0]-rectangle[1]) > .2
    assert np.linalg.norm(rectangle[0]-rectangle[3]) > .03
    assert np.allclose(rectangle[0]-rectangle[3], rectangle[1]-rectangle[2], atol=1e-7)
    assert objects[0]["width"] > 0


def test_rectangle_is_restored_after_hand_splits_mask():
    base = frame(center=(160, 120), size=(120, 16), angle=0)
    blocked = frame(center=(160, 120), size=(120, 16), angle=0, hand=True)
    settings = learn_colour(base, [[160/320, 120/240]])
    first, _, _ = detect(base, settings, QUAD)
    fragments, _, _ = detect(blocked, settings, QUAD)
    assert len(first) == 1 and len(fragments) == 2
    tracker = StableTracker()
    initial = tracker.update(project_observations(first, np.eye(3)), 50.)[0]
    lost = tracker.update(project_observations(fragments, np.eye(3)), 50.033)
    assert len(lost) == 1
    assert lost[0]["id"] == initial["id"]
    assert lost[0]["state"] == "occluded"
    assert np.allclose(lost[0]["corners"], initial["corners"], atol=1e-7)
    assert lost[0]["width"] == initial["width"]
    restored = tracker.update(project_observations(first, np.eye(3)), 50.066)
    assert restored[0]["state"] == "tracked"
    assert len(restored[0]["corners"]) == 4


def test_width_only_occlusion_does_not_collapse_rectangle():
    tracker = StableTracker()
    full = {"a": [.2, .4], "b": [.5, .4], "half_width": .018, "area": .01}
    first = tracker.update([full], 1.)[0]
    thin = {"a": [.2, .4], "b": [.5, .4], "half_width": .004, "area": .003}
    other = tracker.update([thin], 1.03)[0]
    assert other["state"] == "occluded"
    assert np.allclose(other["corners"], first["corners"])


def test_moderately_truncated_colour_area_keeps_full_rectangle():
    tracker = StableTracker()
    full = {"a": [.20, .40], "b": [.50, .40], "half_width": .015, "area": .015}
    initial = tracker.update([full], 3.)[0]
    trimmed = {"a": [.225, .40], "b": [.50, .40], "half_width": .015, "area": .012}
    held = tracker.update([trimmed], 3.033)[0]
    assert held["id"] == initial["id"]
    assert held["state"] == "occluded"
    assert np.allclose(held["corners"], initial["corners"])


def test_tracking_page_route_and_rectangle_overlay(tmp_path):
    controller = Controller(Store(tmp_path / "cal.json"))
    app = create_app(controller=controller, token="key")
    with TestClient(app) as client:
        page = client.get("/tracking")
        assert page.status_code == 200
        assert "Отслеживание объектов" in page.text
        assert 'class="track' in page.text
        recognition_page = client.get("/recognition")
        assert 'href="/tracking"' in recognition_page.text
        assert "<polygon" in recognition_page.text
        assert client.get("/api/recognition/state").status_code == 401
        assert client.get("/api/recognition/state", headers={"X-Control-Token": "key"}).status_code == 200
    controller.close()
