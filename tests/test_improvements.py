import math

import cv2
import numpy as np
from fastapi.testclient import TestClient

from interactive_surface.recognition import learn_colour, detect, ColourSettings
from interactive_surface.controller import Controller
from interactive_surface.game import GameEngine, GOAL_SIDES, W
from interactive_surface.storage import Store
from interactive_surface.web import create_app

FULL = [[0,0],[1,0],[1,1],[0,1]]

def frame(angle=0):
    image = np.full((360,640,3),(35,35,35),np.uint8)
    box=cv2.boxPoints(((210,180),(188,22),angle)).astype(np.int32)
    cv2.fillConvexPoly(image,box,(205,18,208))
    cv2.rectangle(image,(450,110),(560,260),(65,122,175),-1)
    return image

def box(x0,y0,x1,y1):
    return [[x0/640,y0/360],[x1/640,y0/360],[x1/640,y1/360],[x0/640,y1/360]]

def angle_error(actual,expected):
    return abs((actual-expected+90)%180-90)

def test_angle_tracks_all_rotations():
    for angle in (0,16,38,62,90,118,153,174):
        image=frame(angle)
        settings=ColourSettings(151,12,90,25)
        obs,_,_=detect(image,settings,FULL)
        assert len(obs)==1
        a,b=np.array(obs[0]["a"]),np.array(obs[0]["b"])
        actual=math.degrees(math.atan2((b[1]-a[1])*360,(b[0]-a[0])*640))%180
        assert angle_error(actual,angle)<5,(angle,actual)

def test_quad_sampling_avoids_skin():
    image=frame()
    profile=learn_colour(image,regions=[box(125,168,290,192)],
                         negative_regions=[box(465,130,542,230)])
    found,_,_=detect(image,profile,FULL)
    assert len(found)==1
    assert ColourSettings.from_dict(profile.to_dict()) == profile

def test_random_goal_lower_half_and_manual_override():
    engine=GameEngine(lambda:[],lambda _:None,start_worker=False)
    try:
        spots=[]
        for _ in range(10):
            snapshot=engine.start()
            x,y,_=snapshot["goal"]
            assert .58 < y < .89
            assert any(lo<=x*W<=hi for lo,hi in GOAL_SIDES)
            spots.append((x,y))
        assert len(set(spots))==len(spots)
        assert all((spots[i][0]<.5)!=(spots[i+1][0]<.5) for i in range(9))
        engine.configure({"goal_x":.2,"goal_y":.79,"moving_goal":False})
        assert engine.settings.goal_manual
        assert engine.start()["goal"][:2]==[.2,.79]
        engine.configure({"goal_manual":False})
        assert not engine.settings.goal_manual
        assert engine.start()["goal"][:2]!=[.2,.79]
    finally:engine.close()

def test_saved_colour_and_calibration_restore(tmp_path):
    store=Store(tmp_path/"cal.json")
    controller=Controller(store)
    try:
        controller.select_camera("simulation",1280,720)
        controller.open_projector("virtual")
        controller.verify()
        controller.complete()
        controller.recognition.freeze()
        controller.teach_recognition(points=[[180/1280,155/720]])
        controller.finish_recognition()
        assert store.read()["recognition"]["profiles"]["black"]
        controller.choose_background("white")
        assert controller.recognition.settings is None
        controller.choose_background("black")
        assert controller.recognition.settings is not None
    finally:controller.close()
    other=Controller(store)
    try:
        other.select_camera("simulation",1280,720)
        other.open_projector("virtual")
        assert other.verified
        assert other.recognition.settings is not None
        assert other.projector.status()["mode"]=="ready"
    finally:other.close()

def test_quad_api_autosaves(tmp_path):
    controller=Controller(Store(tmp_path/"cal.json"))
    try:
        with TestClient(create_app(controller=controller,token="test")) as c:
            h={"X-Control-Token":"test"}
            c.post("/api/camera/select",headers=h,json={"id":"simulation"})
            c.post("/api/display/open",headers=h,json={"id":"virtual"})
            c.post("/api/calibration/verify",headers=h)
            c.post("/api/calibration/complete",headers=h)
            assert c.post("/api/recognition/capture",headers=h,json={}).status_code==200
            region=[[125/1280,144/720],[220/1280,144/720],
                    [220/1280,168/720],[125/1280,168/720]]
            r=c.post("/api/recognition/learn",headers=h,json={"regions":[region]})
            assert r.status_code==200,r.text
            assert controller.store.read()["recognition"]["profiles"]["black"]
    finally:controller.close()
