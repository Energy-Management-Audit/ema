"""Regression expectation for the configured dev origin boundary."""

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.workspace import Workspace


def test_dev_mode_rejects_the_api_origin(tmp_path):
    app = create_app(
        Workspace(tmp_path / "workspace"),
        8766,
        launch_code="synthetic-code",
        dev_origin="http://127.0.0.1:5173",
    )
    client = TestClient(app, base_url="http://127.0.0.1:8766")
    response = client.post(
        "/session",
        json={"code": "synthetic-code"},
        headers={"origin": "http://127.0.0.1:8766"},
    )
    assert response.status_code == 403
