from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from evidenceguard.app import create_app


def test_app_vertical_slice(tmp_path: Path):
    app = create_app(tmp_path / "api.sqlite3", seed=False, start_worker=False, provider=type("DisabledProvider", (), {"name": "disabled", "ready": False})())
    app.state.camera.active.manifests = AsyncMock(return_value=[])
    with TestClient(app) as client:
        response = client.get("/api/bootstrap")
        assert response.status_code == 200
        assert response.json()["agent"]["ready"] is False
        assert response.json()["skills"] == []
        assert response.json()["evidence"] == []


def test_invalid_frame_id_is_rejected(tmp_path: Path):
    app = create_app(tmp_path / "api.sqlite3", seed=False, start_worker=False, provider=type("DisabledProvider", (), {"name": "disabled", "ready": False})())
    with TestClient(app) as client:
        assert client.get("/api/camera/frames/cam-a/../../secret.jpg").status_code == 404
