from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_registers_health_route() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)
    assert "/health" in app.openapi()["paths"]


def test_health_returns_success_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"]["status"] == "ok"
    assert response.json()["postgis"]["status"] == "ok"
