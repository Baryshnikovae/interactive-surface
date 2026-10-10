import numpy as np
import pytest
from interactive_surface.geometry import Calibration, quad, homography, transform, WALL


def test_normalized_camera_projector_chain():
    c=Calibration([[.1,.2],[.9,.1],[.8,.9],[.15,.8]],[[.2,.1],[.85,.15],[.9,.9],[.05,.85]],(1280,720),(1920,1080))
    cam=np.array(c.camera_quad)*[1280,720]
    actual=c.camera_pixels_to_wall(cam.tolist())
    assert np.allclose(actual,WALL,atol=2e-7)
    assert np.allclose(c.camera_pixels_to_projector_pixels(cam.tolist()),np.array(c.projector_quad)*[1920,1080],atol=1e-3)
    back=transform(np.linalg.inv(c.camera_to_projector),np.array(c.projector_quad))
    assert np.allclose(back,c.camera_quad,atol=1e-6)


def test_rectangles_and_different_resolutions():
    c=Calibration([[.2,.15],[.8,.15],[.8,.8],[.2,.8]],[[.05,.05],[.95,.05],[.95,.95],[.05,.95]],(640,480),(3840,2160))
    assert np.allclose(c.wall_to_projector_pixels([[.5,.5]]),[[1920,1080]])


@pytest.mark.parametrize('points',[
 [[0,0],[0,0],[1,1],[0,1]],
 [[0,0],[1,1],[1,0],[0,1]],
 [[0,0],[1,0],[1.3,1],[0,1]],
 [[.4,.4],[.41,.4],[.41,.41],[.4,.41]],
])
def test_invalid_quads(points):
    with pytest.raises(ValueError): quad(points)
