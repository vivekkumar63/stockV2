import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_requires_key(client):
    response = client.get("/api/v1/stocks")
    assert response.status_code == 401


def test_api_accepts_valid_key(client):
    from settings import settings
    response = client.get(
        "/api/v1/stocks",
        headers={"X-API-Key": settings.api_key},
    )
    assert response.status_code != 401


def test_invalid_api_key_rejected(client):
    response = client.get(
        "/api/v1/stocks",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
