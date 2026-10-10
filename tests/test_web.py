from fastapi.testclient import TestClient
from interactive_surface.web import create_app


def test_public_and_protected_endpoints(tmp_path):
    from interactive_surface.controller import Controller
    from interactive_surface.storage import Store
    controller = Controller(Store(tmp_path / "data.json"))
    app = create_app("http://192.168.1.42:8765", controller=controller, token="test-secret")
    with TestClient(app) as client:
        assert "Подготовка интерактивной поверхности" in client.get("/").text
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/status").json()["lan_url"] == "http://192.168.1.42:8765"
        assert client.get("/api/devices").status_code == 401
        assert client.post("/api/calibration/reset").status_code == 401
        headers={"X-Control-Token":"test-secret"}
        assert client.get("/api/state",headers=headers).status_code == 200
        assert client.get("/api/devices",headers=headers).status_code == 200
        assert client.post("/api/camera/select",headers=headers,json={"id":"simulation"}).status_code == 200
        assert client.post("/api/display/open",headers=headers,json={"id":"virtual"}).status_code == 200
        assert client.post("/api/calibration/verify",headers=headers).status_code == 200
        assert client.post("/api/calibration/complete",headers=headers).status_code == 200
        assert controller.saved["simulation"] is True
        assert client.get("/api/state",headers=headers).json()["verified"] is True
        assert client.get("/api/projector/visual",headers=headers).json()["mode"] == "ready"
        assert client.post("/api/calibration/restore",headers=headers).status_code == 200
        assert client.post("/api/calibration/reset",headers=headers).status_code == 200
        assert controller.saved == {}
    controller.close()


def test_reject_bad_points_and_no_qr(tmp_path):
    from interactive_surface.controller import Controller
    from interactive_surface.storage import Store
    c = Controller(Store(tmp_path / "config.json"))
    client=TestClient(create_app(controller=c,token="a"))
    assert client.get("/qr.png").status_code == 403
    headers={"X-Control-Token":"a"}
    bad=[[.5,.5],[.5,.5],[.5,.5],[.5,.5]]
    assert client.post("/api/calibration/points/camera",headers=headers,json={"points":bad}).status_code == 400
    assert client.post("/api/calibration/complete",headers=headers).status_code == 400
    c.close()
