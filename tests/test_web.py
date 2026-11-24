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


def test_local_operator_and_remote_qr_boundary(tmp_path):
    from interactive_surface.controller import Controller
    from interactive_surface.storage import Store
    c = Controller(Store(tmp_path / "config.json"))
    app = create_app("http://192.168.1.42:8765", controller=c, token="current-key")
    try:
        for peer, base_url in (
            ("127.0.0.1", "http://127.0.0.1:8765"),
            ("::ffff:127.0.0.1", "http://127.0.0.1:8765"),
            ("192.168.1.42", "http://192.168.1.42:8765"),
        ):
            with TestClient(app, client=(peer, 12345), base_url=base_url) as client:
                session = client.get("/api/session", headers={"X-Control-Token": "stale-key"})
                assert session.json()["authorized"] is True
                assert session.json()["token"] == "current-key"
                assert session.headers["cache-control"] == "no-store"
                assert client.get("/games").headers["cache-control"] == "no-store"
                headers = {"X-Control-Token": session.json()["token"]}
                assert client.get("/api/games", headers=headers).status_code == 200
                assert client.get("/api/game/state", headers=headers).status_code == 200
        with TestClient(app, client=("192.168.1.99", 12345),
                        base_url="http://192.168.1.42:8765") as client:
            session = client.get("/api/session", headers={"X-Forwarded-For": "127.0.0.1"})
            assert session.json()["authorized"] is False
            assert "token" not in session.json()
            assert client.get("/api/game/state").status_code == 401
            assert client.get("/qr.png").status_code == 403
            headers = {"X-Control-Token": "current-key"}
            assert client.get("/api/session", headers=headers).json()["authorized"] is True
            result = client.post("/api/game/preview", headers=headers, json={"game": "jump"})
            assert result.status_code == 200
            assert result.json()["game"] == "jump"
            assert client.get("/api/game/state", headers=headers).json()["game"] == "jump"
            result = client.post("/api/game/preview", headers=headers, json={"game": "hole"})
            assert result.status_code == 200
            assert result.json()["game"] == "hole"
    finally:
        c.close()
