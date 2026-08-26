from __future__ import annotations

from fastapi.testclient import TestClient

from app.api_extended import router as extended_router
from app.config import Settings
from app.integrations_main import app as integration_app
from app.production_v4 import app
from app.release import (
    BACKEND_SERVICE_NAME,
    CANONICAL_MIGRATION_HEAD,
    INTEGRATION_SERVICE_NAME,
)


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
_LEGACY_IDENTITY_PATHS = {
    "/api/v1/admin/users",
    "/api/v1/admin/roles",
    "/api/v1/admin/permissions",
    "/api/v1/admin/capabilities",
    "/api/v1/admin/capabilities/{code}",
}


def _operations(schema: dict) -> list[tuple[str, str, dict]]:
    result: list[tuple[str, str, dict]] = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method.lower() in _HTTP_METHODS:
                result.append((path, method.lower(), operation))
    return result


def test_release_identity_is_consistent_across_entrypoints() -> None:
    backend = TestClient(app).get("/health/version")
    integrations = TestClient(integration_app).get("/health/version")

    assert backend.status_code == 200
    assert integrations.status_code == 200
    assert backend.json()["name"] == BACKEND_SERVICE_NAME
    assert integrations.json()["name"] == INTEGRATION_SERVICE_NAME
    assert backend.json()["migration_head"] == CANONICAL_MIGRATION_HEAD
    assert integrations.json()["migration_head"] == CANONICAL_MIGRATION_HEAD
    assert backend.json()["version"] == app.version
    assert integrations.json()["version"] == integration_app.version
    assert app.version == integration_app.version


def test_stale_migration_identity_is_rejected() -> None:
    try:
        Settings(migration_head="0002_identity_tenancy")
    except ValueError as exc:
        assert "MIGRATION_HEAD" in str(exc)
    else:
        raise AssertionError("stale migration identity was accepted")


def test_legacy_admin_placeholders_are_not_registered() -> None:
    paths = {str(getattr(route, "path", "")) for route in extended_router.routes}
    assert not paths & _LEGACY_IDENTITY_PATHS

    schema = app.openapi()
    assert "list_users" in schema["paths"]["/api/v1/admin/users"]["get"]["operationId"]
    assert "list_roles" in schema["paths"]["/api/v1/admin/roles"]["get"]["operationId"]
    assert "list_permissions" in schema["paths"]["/api/v1/admin/permissions"]["get"]["operationId"]


def test_openapi_has_unique_operation_ids_and_canonical_metadata() -> None:
    schema = app.openapi()
    operations = _operations(schema)
    operation_ids = [operation["operationId"] for _, _, operation in operations]

    assert operation_ids
    assert len(operation_ids) == len(set(operation_ids))
    assert schema["info"]["version"] == app.version
    assert schema["info"]["x-service-name"] == BACKEND_SERVICE_NAME
    assert schema["info"]["x-migration-head"] == CANONICAL_MIGRATION_HEAD


def test_openapi_documents_standard_bearer_security() -> None:
    schema = app.openapi()
    bearer = schema["components"]["securitySchemes"]["BearerAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"

    protected = schema["paths"]["/api/v1/admin/users"]["get"]
    assert protected["security"] == [{"BearerAuth": []}]
    assert not any(
        parameter.get("in") == "header"
        and str(parameter.get("name", "")).lower() == "authorization"
        for parameter in protected.get("parameters", [])
    )

    signed_webhook = schema["paths"][
        "/api/v1/integrations/{webhook_slug}/webhooks/{provider}"
    ]["post"]
    assert "security" not in signed_webhook


def test_production_openapi_contains_all_portal_and_integration_surfaces() -> None:
    paths = set(app.openapi()["paths"])
    required = {
        "/api/v1/admin/integrations/health",
        "/api/v1/admin/integrations",
        "/api/v1/admin/compliance/policies",
        "/api/v1/admin/portal-bindings",
        "/api/v1/admin/portal-reviews/claims",
        "/api/v1/operations/control-tower",
        "/api/v1/portals/customer/context",
        "/api/v1/portals/customer/quotes/{quote_id}/decision",
        "/api/v1/portals/carrier/context",
        "/api/v1/portals/carrier/tenders/{tender_id}/response",
        "/api/v1/portals/carrier/loads/{load_id}/tracking",
        "/api/v1/integrations/{webhook_slug}/webhooks/{provider}",
    }
    assert required <= paths
