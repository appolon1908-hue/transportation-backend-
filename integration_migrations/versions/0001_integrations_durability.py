"""Durable integrations, signed inbox and tamper-evident provenance.

Revision ID: 0001_integrations_durability
Revises: core 0002_identity_tenancy (checked at runtime)
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_integrations_durability"
down_revision = None
branch_labels = ("integrations",)
depends_on = None

TENANT_TABLES = (
    "integration_connections",
    "webhook_subscriptions",
    "outbound_deliveries",
    "delivery_attempts",
    "inbound_webhooks_v2",
    "provenance_heads",
    "provenance_records",
)


def _tenant_policy(table_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'''CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
                USING (tenant_id::text = current_setting('app.tenant_id', true))
                WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))'''
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    core_head = bind.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if core_head != "0002_identity_tenancy":
        raise RuntimeError(
            "Integration migration requires core schema head 0002_identity_tenancy; "
            f"found {core_head!r}."
        )

    op.create_table(
        "integration_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("base_url", sa.String(length=600), nullable=False),
        sa.Column("secret_ref", sa.String(length=300), nullable=False),
        sa.Column("signing_key_id", sa.String(length=120)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 120", name="ck_integration_timeout"),
        sa.CheckConstraint(
            "rate_limit_per_minute BETWEEN 1 AND 60000", name="ck_integration_rate"
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_integration_connection_tenant_name"),
    )
    op.create_index(
        "ix_integration_connection_tenant_kind",
        "integration_connections",
        ["tenant_id", "kind", "enabled"],
    )
    op.create_index(
        "ix_integration_connections_tenant_id",
        "integration_connections",
        ["tenant_id"],
    )

    # This table intentionally stores only opaque environment references, never
    # signing material.  It is the narrow pre-tenant lookup used to identify the
    # tenant for an authenticated inbound webhook.
    op.create_table(
        "webhook_signing_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("key_id", sa.String(length=120), nullable=False),
        sa.Column("secret_ref", sa.String(length=300), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "key_id", name="uq_webhook_signing_provider_key"),
    )
    op.create_index(
        "ix_webhook_signing_active",
        "webhook_signing_keys",
        ["provider", "key_id", "enabled"],
    )
    op.create_index(
        "ix_webhook_signing_keys_tenant_id",
        "webhook_signing_keys",
        ["tenant_id"],
    )
    op.execute(sa.text("REVOKE ALL ON webhook_signing_keys FROM PUBLIC"))

    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_pattern", sa.String(length=180), nullable=False),
        sa.Column("capability_code", sa.String(length=180), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 25", name="ck_webhook_subscription_attempts"),
        sa.UniqueConstraint(
            "tenant_id",
            "connection_id",
            "event_pattern",
            name="uq_webhook_subscription_route",
        ),
    )
    op.create_index(
        "ix_webhook_subscription_match",
        "webhook_subscriptions",
        ["tenant_id", "enabled", "event_pattern"],
    )
    op.create_index(
        "ix_webhook_subscriptions_connection_id",
        "webhook_subscriptions",
        ["connection_id"],
    )
    op.create_index(
        "ix_webhook_subscriptions_tenant_id",
        "webhook_subscriptions",
        ["tenant_id"],
    )

    op.create_table(
        "outbound_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_subscriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=180), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=120)),
        sa.Column("last_error_detail", sa.Text()),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "subscription_id", "event_id", name="uq_outbound_delivery_event_route"
        ),
    )
    op.create_index(
        "ix_outbound_delivery_claim",
        "outbound_deliveries",
        ["status", "next_attempt_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_outbound_delivery_tenant_created",
        "outbound_deliveries",
        ["tenant_id", "created_at"],
    )
    op.create_index("ix_outbound_deliveries_event_id", "outbound_deliveries", ["event_id"])
    op.create_index("ix_outbound_deliveries_event_type", "outbound_deliveries", ["event_type"])
    op.create_index(
        "ix_outbound_deliveries_subscription_id", "outbound_deliveries", ["subscription_id"]
    )
    op.create_index(
        "ix_outbound_deliveries_connection_id", "outbound_deliveries", ["connection_id"]
    )
    op.create_index("ix_outbound_deliveries_tenant_id", "outbound_deliveries", ["tenant_id"])

    op.create_table(
        "delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outbound_deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_hash", sa.String(length=64)),
        sa.Column("error_code", sa.String(length=120)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("delivery_id", "attempt_number", name="uq_delivery_attempt_number"),
    )
    op.create_index(
        "ix_delivery_attempt_delivery_started",
        "delivery_attempts",
        ["delivery_id", "started_at"],
    )
    op.create_index("ix_delivery_attempts_tenant_id", "delivery_attempts", ["tenant_id"])

    op.create_table(
        "inbound_webhooks_v2",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("external_event_id", sa.String(length=220), nullable=False),
        sa.Column("key_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=180), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=120)),
        sa.Column("last_error_detail", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "external_event_id",
            name="uq_inbound_webhook_external_event",
        ),
    )
    op.create_index(
        "ix_inbound_webhook_claim",
        "inbound_webhooks_v2",
        ["status", "next_attempt_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_inbound_webhook_tenant_received",
        "inbound_webhooks_v2",
        ["tenant_id", "received_at"],
    )
    op.create_index(
        "ix_inbound_webhooks_v2_event_type", "inbound_webhooks_v2", ["event_type"]
    )
    op.create_index(
        "ix_inbound_webhooks_v2_tenant_id", "inbound_webhooks_v2", ["tenant_id"]
    )

    op.create_table(
        "provenance_heads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream", sa.String(length=180), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("head_hash", sa.String(length=64), nullable=False, server_default="0" * 64),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "stream", name="uq_provenance_head_stream"),
    )
    op.create_index("ix_provenance_heads_tenant_id", "provenance_heads", ["tenant_id"])

    op.create_table(
        "provenance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream", sa.String(length=180), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=180), nullable=False),
        sa.Column("entity_id", sa.String(length=220), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=220), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "stream", "sequence", name="uq_provenance_record_sequence"
        ),
    )
    op.create_index(
        "ix_provenance_record_stream",
        "provenance_records",
        ["tenant_id", "stream", "sequence"],
    )
    op.create_index(
        "ix_provenance_record_entity",
        "provenance_records",
        ["tenant_id", "entity_id"],
    )
    op.create_index("ix_provenance_records_tenant_id", "provenance_records", ["tenant_id"])

    for table_name in TENANT_TABLES:
        _tenant_policy(table_name)


def downgrade() -> None:
    for table_name in reversed(TENANT_TABLES):
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "{table_name}_tenant_isolation" ON "{table_name}"'
            )
        )

    op.drop_table("provenance_records")
    op.drop_table("provenance_heads")
    op.drop_table("inbound_webhooks_v2")
    op.drop_table("delivery_attempts")
    op.drop_table("outbound_deliveries")
    op.drop_table("webhook_subscriptions")
    op.drop_table("webhook_signing_keys")
    op.drop_table("integration_connections")
