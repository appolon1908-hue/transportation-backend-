from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.security import Actor

client = TestClient(app)


def test_identity_routes_are_registered() -> None:
    registered = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    required = {
        ("GET", "/api/v1/auth/context"),
        ("GET", "/api/v1/admin/tenant"),
        ("PATCH", "/api/v1/admin/tenant"),
        ("GET", "/api/v1/admin/organizations"),
        ("POST", "/api/v1/admin/organizations"),
        ("GET", "/api/v1/admin/users"),
        ("POST", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/memberships"),
        ("POST", "/api/v1/admin/memberships"),
        ("GET", "/api/v1/admin/roles"),
        ("POST", "/api/v1/admin/roles"),
        ("GET", "/api/v1/admin/permissions"),
        ("GET", "/api/v1/admin/audit"),
        ("GET", "/api/v1/admin/capabilities"),
        ("PATCH", "/api/v1/admin/capabilities/{code}"),
    }
    assert not required - registered


def test_actor_requires_database_granted_permission() -> None:
    actor = Actor(
        subject="subject",
        issuer="issuer",
        principal_id=uuid4(),
        membership_id=uuid4(),
        tenant_id=uuid4(),
        organization_id=None,
        customer_id=None,
        carrier_id=None,
        principal_type="USER",
        permissions=frozenset({"customer.read"}),
        roles=frozenset({"reader"}),
    )
    actor.require("customer.read")
    with pytest.raises(HTTPException) as denied:
        actor.require("customer.manage")
    assert denied.value.status_code == 403


def test_production_rejects_development_identity_headers() -> None:
    with pytest.raises(ValueError, match="ALLOW_DEVELOPMENT_IDENTITY_HEADERS"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://app:secret@db/freight",
            oidc_issuer="https://auth.example.com/realms/freight",
            oidc_audience="freight-api",
            allowed_hosts="api.example.com",
            cors_origins="https://app.example.com",
            allow_development_identity_headers=True,
        )


def test_row_level_policy_migrations_cover_business_and_identity_tables() -> None:
    business_migration = Path(
        "migrations/versions/0002_identity_tenancy.py"
    ).read_text()
    for table in (
        "customers",
        "carriers",
        "shipments",
        "loads",
        "audit_entries",
        "outbox_messages",
    ):
        assert f'"{table}"' in business_migration
    assert "current_setting('app.tenant_id'" in business_migration

    identity_migration = Path(
        "migrations/versions/0002b_identity_rbac_rls.py"
    ).read_text()
    for table in (
        "platform_organizations",
        "platform_roles",
        "platform_memberships",
        "platform_role_permissions",
        "platform_membership_roles",
    ):
        assert table in identity_migration
    assert "current_setting('app.tenant_id'" in identity_migration


def test_auth_context_fails_closed_without_identity() -> None:
    response = client.get("/api/v1/auth/context")
    assert response.status_code == 401
