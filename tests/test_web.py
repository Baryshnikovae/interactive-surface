from fastapi.testclient import TestClient

from interactive_surface.web import create_app


def test_demo_page_and_api():
    client = TestClient(create_app("http://192.168.1.42:8765"))
    assert client.get("/").status_code == 200
    assert "Система запущена" in client.get("/").text
    assert client.get("/api/status").json() == {
        "ok": True, "mode": "demo", "lan_url": "http://192.168.1.42:8765"
    }
    assert client.get("/health").json() == {"status": "ok"}
    qr = client.get("/qr.png")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content.startswith(b"\x89PNG")


def test_no_qr_when_offline():
    client = TestClient(create_app())
    assert client.get("/qr.png").status_code == 404
