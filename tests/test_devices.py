from interactive_surface.cameras import prefer_camera, synthetic_frame
from interactive_surface.displays import prefer_display


def test_external_camera_preference():
    cameras=[{'id':'0','external':False},{'id':'1','external':True}]
    assert prefer_camera(cameras)=='1'


def test_external_display_preference():
    screens=[{'id':0,'primary':True},{'id':1,'primary':False}]
    assert prefer_display(screens)==1
    assert prefer_display([]) is None


def test_synthetic_camera_frame():
    frame=synthetic_frame()
    assert frame.shape==(720,1280,3)
