from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_live_health() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "live"


def test_core_v1_routes_are_registered() -> None:
    registered = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    required = {
        ("GET", "/api/v1/me"),
        ("GET", "/api/v1/me/permissions"),
        ("GET", "/api/v1/capabilities"),
        ("GET", "/api/v1/customers"),
        ("POST", "/api/v1/customers"),
        ("GET", "/api/v1/carriers"),
        ("POST", "/api/v1/carriers"),
        ("GET", "/api/v1/quotes"),
        ("POST", "/api/v1/quotes"),
        ("GET", "/api/v1/shipments"),
        ("POST", "/api/v1/shipments"),
        ("GET", "/api/v1/loads"),
        ("POST", "/api/v1/loads"),
        ("POST", "/api/v1/loads/{load_id}/tenders"),
        ("POST", "/api/v1/tenders/{tender_id}/accept"),
        ("POST", "/api/v1/loads/{load_id}/dispatch"),
        ("GET", "/api/v1/loads/{load_id}/tracking"),
        ("POST", "/api/v1/integrations/tracking/{provider}/webhooks"),
        ("GET", "/api/v1/invoices"),
        ("GET", "/api/v1/carrier-settlements"),
        ("GET", "/api/v1/claims"),
        ("GET", "/api/v1/operations/exceptions"),
        ("GET", "/api/v1/operations/dead-letters"),
        ("GET", "/api/v1/admin/capabilities"),
    }
    assert required <= registered


def test_me_fails_closed_without_identity() -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
