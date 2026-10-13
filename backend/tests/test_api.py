from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_capabilities_reports_background_model():
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "ai_provider_configured" in data
    assert data["background_model"] == "recraft-ai/recraft-remove-background"

def test_background_remove_fails_closed_without_provider_token(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main.settings, "replicate_api_token", "")
    response = client.post(
        "/api/v1/background/remove",
        files={"file": ("test.png", b"not-really-an-image", "image/png")}
    )
    assert response.status_code == 503

def test_generic_edit_is_not_falsely_reported_as_success():
    response = client.post("/api/v1/edits", json={
        "operation": "portrait_retouch",
        "image_url": "https://example.invalid/private-image",
        "strength": 0.4
    })
    assert response.status_code == 501

def test_portrait_retouch_route_uses_face_model(monkeypatch):
    import app.main as main
    from PIL import Image
    from io import BytesIO
    monkeypatch.setattr(main.settings, "replicate_api_token", "test-token")
    monkeypatch.setattr(main.settings, "ai_provider", "replicate")
    monkeypatch.setattr(main, "_run_image_model", lambda *args, **kwargs: b"fake-png")
    image = BytesIO()
    Image.new("RGB", (8, 8), "white").save(image, format="PNG")
    response = client.post("/api/v1/portrait/retouch", files={"file": ("portrait.png", image.getvalue(), "image/png")})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

def test_restore_route_fails_closed_without_token(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main.settings, "replicate_api_token", "")
    monkeypatch.setattr(main.settings, "ai_provider", "replicate")
    response = client.post("/api/v1/image/restore", files={"file": ("portrait.png", b"x", "image/png")})
    assert response.status_code == 503
