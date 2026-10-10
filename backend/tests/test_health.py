import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_healthz_ok():
    settings = Settings(gemini_model="test-model", data_backend="sqlite", _env_file=None)
    client = TestClient(create_app(settings))

    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "model": "test-model",
        "data_backend": "sqlite",
        "dependencies": None,
    }


def test_cors_allows_configured_origin():
    settings = Settings(allowed_origins="http://localhost:5173,https://x.web.app", _env_file=None)
    client = TestClient(create_app(settings))

    resp = client.get("/healthz", headers={"Origin": "https://x.web.app"})

    assert resp.headers["access-control-allow-origin"] == "https://x.web.app"


def test_auth_disabled_is_rejected_on_cloud_run():
    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings(auth_disabled=True, K_SERVICE="pauseguard-api", _env_file=None)
