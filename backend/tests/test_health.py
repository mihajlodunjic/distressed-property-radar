from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings, get_settings
from app.main import create_app
from app.operations.status import build_readiness_report


def test_create_app_registers_health_route() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)
    assert "/live" in app.openapi()["paths"]
    assert "/health" in app.openapi()["paths"]
    assert "/ready" in app.openapi()["paths"]
    assert "/api/v1/live" in app.openapi()["paths"]
    assert "/api/v1/health" in app.openapi()["paths"]
    assert "/api/v1/ready" in app.openapi()["paths"]


def test_health_returns_success_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"]["status"] == "ok"
    assert response.json()["postgis"]["status"] == "ok"


def test_api_v1_health_returns_success_response(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_liveness_returns_process_status_without_dependency_details(
    client: TestClient,
) -> None:
    response = client.get("/live", headers={"X-Request-ID": "phase14-request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "phase14-request"
    payload = response.json()
    assert payload["status"] == "ok"
    assert "database" not in payload


def test_readiness_returns_success_when_dependencies_are_ready(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["database"]["status"] == "ok"
    assert payload["postgis"]["status"] == "ok"
    assert payload["migrations"]["status"] == "ok"


def test_readiness_reports_database_failure() -> None:
    class FailingEngine:
        def connect(self) -> object:
            raise OperationalError("SELECT 1", {}, Exception("temporary outage"))

    report = build_readiness_report(settings=Settings(APP_ENV="test"), engine=FailingEngine())

    assert report["ready"] is False
    assert report["status"] == "not_ready"
    assert report["database"]["status"] == "error"
    assert report["postgis"]["status"] == "unknown"
    assert report["migrations"]["status"] == "unknown"


def test_production_readiness_fails_closed_without_token(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_ACCESS_TOKEN", "")
    get_settings.cache_clear()

    with TestClient(create_app()) as production_client:
        response = production_client.get("/ready")

    get_settings.cache_clear()
    assert response.status_code == 503
    assert response.json()["configuration"]["status"] == "error"
    assert (
        "API_ACCESS_TOKEN is required in production." in response.json()["configuration"]["errors"]
    )
