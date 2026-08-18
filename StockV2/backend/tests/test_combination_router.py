# backend/tests/test_combination_router.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

HEADERS = {}  # No API key needed for test — TestClient doesn't enforce auth


def test_get_run_status_endpoint():
    response = client.get("/api/v1/combinations/run-status")
    assert response.status_code in [200, 401]


def test_get_rankings_endpoint():
    response = client.get("/api/v1/combinations/rankings")
    assert response.status_code in [200, 401]


def test_get_best_endpoint():
    response = client.get("/api/v1/combinations/best")
    assert response.status_code in [200, 401]


def test_get_avoid_endpoint():
    response = client.get("/api/v1/combinations/avoid")
    assert response.status_code in [200, 401]


def test_trigger_analysis_endpoint():
    response = client.post("/api/v1/combinations/analyze")
    assert response.status_code in [200, 401]
