"""Carrier compliance evidence, readiness policy and write-time enforcement.

Revision ID: 0001_carrier_readiness
Requires core 0002_identity_tenancy and integrations 0001_integrations_durability.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_carrier_readiness"
down_revision = None
branch_labels = ("compliance",)
depends_on = None

TENANT_TABLES = (
    "carrier_compliance_policies",
    "carrier_authority_records",
    "carrier_insurance_records",
    "carrier_safety_records",
    "carrier_compliance_overrides",
    "carrier_readiness_decisions",
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
            "Compliance migration requires core schema head 0002_identity_tenancy; "
            f"found {core_head!r}."
        )
    integration_table = bind.execute(
        sa.text("SELECT to_regclass('public.alembic_version_integrations')")
    ).scalar_one_or_none()
    if integration_table is None:
        raise RuntimeError("Compliance migration requires the integrations migration track.")
    integration_head = bind.execute(
        sa.text("SELECT version_num FROM alembic_version_integrations")
    ).scalar_one_or_none()
    if integration_head != "0001_integrations_durability":
        raise RuntimeError(
            "Compliance migration requires integration head 0001_integrations_durability; "
            f"found {integration_head!r}."
        )

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    op.create_table(
        "carrier_compliance_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authority_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("minimum_auto_liability", sa.Numeric(18, 2), nullable=False, server_default="1000000"),
        sa.Column("minimum_cargo", sa.Numeric(18, 2), nullable=False, server_default="100000"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("expiry_buffer_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("max_safety_age_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "allowed_safety_ratings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"SATISFACTORY\",\"CONDITIONAL\",\"NOT_RATED\"]'::jsonb"),
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(length=220), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("expiry_buffer_days BETWEEN 0 AND 365", name="ck_compliance_expiry_buffer"),
        sa.CheckConstraint("max_safety_age_days BETWEEN 1 AND 730", name="ck_compliance_safety_age"),
        sa.UniqueConstraint("tenant_id", "version", name="uq_compliance_policy_tenant_version"),
    )
    op.create_index(
        "ix_compliance_policy_active",
        "carrier_compliance_policies",
        ["tenant_id", "enabled", "version"],
    )
    op.create_index(
        "ix_carrier_compliance_policies_tenant_id",
        "carrier_compliance_policies",
        ["tenant_id"],
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_compliance_policy_one_enabled "
            "ON carrier_compliance_policies (tenant_id) WHERE enabled"
        )
    )

    op.create_table(
        "carrier_authority_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authority_type", sa.String(length=60), nullable=False),
        sa.Column("authority_number_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("issued_at", sa.Date()),
        sa.Column("expires_at", sa.Date()),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("source_record_id", sa.String(length=220)),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.String(length=220), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "carrier_id", "authority_type", "authority_number_hash",
            name="uq_carrier_authority_identity",
        ),
    )
    op.create_index(
        "ix_carrier_authority_ready",
        "carrier_authority_records",
        ["tenant_id", "carrier_id", "status", "expires_at"],
    )
    op.create_index("ix_carrier_authority_records_tenant_id", "carrier_authority_records", ["tenant_id"])
    op.create_index("ix_carrier_authority_records_carrier_id", "carrier_authority_records", ["carrier_id"])

    op.create_table(
        "carrier_insurance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insurance_type", sa.String(length=60), nullable=False),
        sa.Column("policy_number_hash", sa.String(length=64), nullable=False),
        sa.Column("insurer_name", sa.String(length=220), nullable=False),
        sa.Column("limit_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("effective_at", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=False),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.String(length=220), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("limit_amount >= 0", name="ck_carrier_insurance_limit"),
        sa.UniqueConstraint(
            "tenant_id", "carrier_id", "insurance_type", "policy_number_hash",
            name="uq_carrier_insurance_identity",
        ),
    )
    op.create_index(
        "ix_carrier_insurance_ready",
        "carrier_insurance_records",
        ["tenant_id", "carrier_id", "insurance_type", "status", "expires_at"],
    )
    op.create_index("ix_carrier_insurance_records_tenant_id", "carrier_insurance_records", ["tenant_id"])
    op.create_index("ix_carrier_insurance_records_carrier_id", "carrier_insurance_records", ["carrier_id"])

    op.create_table(
        "carrier_safety_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.String(length=60), nullable=False),
        sa.Column("out_of_service", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("measured_at", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("source_record_id", sa.String(length=220), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.String(length=220), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "carrier_id", "source", "source_record_id",
            name="uq_carrier_safety_source_record",
        ),
    )
    op.create_index(
        "ix_carrier_safety_latest",
        "carrier_safety_records",
        ["tenant_id", "carrier_id", "measured_at"],
    )
    op.create_index("ix_carrier_safety_records_tenant_id", "carrier_safety_records", ["tenant_id"])
    op.create_index("ix_carrier_safety_records_carrier_id", "carrier_safety_records", ["carrier_id"])

    op.create_table(
        "carrier_compliance_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(length=220), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.String(length=220)),
    )
    op.create_index(
        "ix_compliance_override_active",
        "carrier_compliance_overrides",
        ["tenant_id", "carrier_id", "action", "expires_at"],
    )
    op.create_index("ix_carrier_compliance_overrides_tenant_id", "carrier_compliance_overrides", ["tenant_id"])
    op.create_index("ix_carrier_compliance_overrides_carrier_id", "carrier_compliance_overrides", ["carrier_id"])

    op.create_table(
        "carrier_readiness_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_version", sa.Integer()),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("evaluated_by", sa.String(length=220), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_readiness_decision_carrier",
        "carrier_readiness_decisions",
        ["tenant_id", "carrier_id", "evaluated_at"],
    )
    op.create_index(
        "ix_readiness_decision_action",
        "carrier_readiness_decisions",
        ["tenant_id", "action", "ready", "evaluated_at"],
    )
    op.create_index("ix_carrier_readiness_decisions_tenant_id", "carrier_readiness_decisions", ["tenant_id"])
    op.create_index("ix_carrier_readiness_decisions_carrier_id", "carrier_readiness_decisions", ["carrier_id"])

    for table_name in TENANT_TABLES:
        _tenant_policy(table_name)

    op.execute(
        sa.text(
            r'''
CREATE OR REPLACE FUNCTION freight_carrier_readiness(
    p_tenant_id uuid,
    p_carrier_id uuid,
    p_action text
) RETURNS TABLE (
    ready boolean,
    reasons jsonb,
    policy_version integer,
    input_hash text
)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_policy carrier_compliance_policies%ROWTYPE;
    v_safety carrier_safety_records%ROWTYPE;
    v_reasons jsonb := '[]'::jsonb;
    v_input jsonb;
    v_override_ids jsonb := '[]'::jsonb;
    v_has_override boolean := false;
    v_hard_block boolean := false;
    v_ready boolean := false;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM carriers
        WHERE id = p_carrier_id AND tenant_id = p_tenant_id
    ) THEN
        v_reasons := v_reasons || jsonb_build_array('CARRIER_NOT_FOUND');
        v_hard_block := true;
    END IF;

    SELECT * INTO v_policy
    FROM carrier_compliance_policies
    WHERE tenant_id = p_tenant_id AND enabled
    ORDER BY version DESC
    LIMIT 1;

    IF NOT FOUND THEN
        v_reasons := v_reasons || jsonb_build_array('POLICY_MISSING');
        v_hard_block := true;
    ELSE
        IF v_policy.authority_required AND NOT EXISTS (
            SELECT 1
            FROM carrier_authority_records
            WHERE tenant_id = p_tenant_id
              AND carrier_id = p_carrier_id
              AND status = 'ACTIVE'
              AND (expires_at IS NULL OR expires_at >= current_date + v_policy.expiry_buffer_days)
        ) THEN
            v_reasons := v_reasons || jsonb_build_array('AUTHORITY_INACTIVE_OR_EXPIRING');
        END IF;

        IF v_policy.minimum_auto_liability > 0 AND NOT EXISTS (
            SELECT 1
            FROM carrier_insurance_records
            WHERE tenant_id = p_tenant_id
              AND carrier_id = p_carrier_id
              AND insurance_type = 'AUTO_LIABILITY'
              AND status = 'ACTIVE'
              AND currency = v_policy.currency
              AND limit_amount >= v_policy.minimum_auto_liability
              AND effective_at <= current_date
              AND expires_at >= current_date + v_policy.expiry_buffer_days
        ) THEN
            v_reasons := v_reasons || jsonb_build_array('AUTO_LIABILITY_INSUFFICIENT_OR_EXPIRING');
        END IF;

        IF v_policy.minimum_cargo > 0 AND NOT EXISTS (
            SELECT 1
            FROM carrier_insurance_records
            WHERE tenant_id = p_tenant_id
              AND carrier_id = p_carrier_id
              AND insurance_type = 'CARGO'
              AND status = 'ACTIVE'
              AND currency = v_policy.currency
              AND limit_amount >= v_policy.minimum_cargo
              AND effective_at <= current_date
              AND expires_at >= current_date + v_policy.expiry_buffer_days
        ) THEN
            v_reasons := v_reasons || jsonb_build_array('CARGO_INSURANCE_INSUFFICIENT_OR_EXPIRING');
        END IF;

        SELECT * INTO v_safety
        FROM carrier_safety_records
        WHERE tenant_id = p_tenant_id AND carrier_id = p_carrier_id
        ORDER BY measured_at DESC, verified_at DESC
        LIMIT 1;

        IF NOT FOUND THEN
            v_reasons := v_reasons || jsonb_build_array('SAFETY_RECORD_MISSING');
        ELSE
            IF v_safety.out_of_service THEN
                v_reasons := v_reasons || jsonb_build_array('OUT_OF_SERVICE');
                v_hard_block := true;
            END IF;
            IF v_safety.measured_at < current_date - v_policy.max_safety_age_days THEN
                v_reasons := v_reasons || jsonb_build_array('SAFETY_RECORD_STALE');
            END IF;
            IF NOT (v_policy.allowed_safety_ratings ? v_safety.rating) THEN
                v_reasons := v_reasons || jsonb_build_array('SAFETY_RATING_BLOCKED');
                IF v_safety.rating = 'UNSATISFACTORY' THEN
                    v_reasons := v_reasons || jsonb_build_array('UNSATISFACTORY_SAFETY');
                    v_hard_block := true;
                END IF;
            END IF;
        END IF;
    END IF;

    SELECT COALESCE(jsonb_agg(id ORDER BY created_at), '[]'::jsonb)
    INTO v_override_ids
    FROM carrier_compliance_overrides
    WHERE tenant_id = p_tenant_id
      AND carrier_id = p_carrier_id
      AND active
      AND action IN (upper(p_action), 'ALL')
      AND starts_at <= now()
      AND expires_at > now();

    v_has_override := jsonb_array_length(v_override_ids) > 0;
    v_ready := jsonb_array_length(v_reasons) = 0;
    IF NOT v_ready AND v_has_override AND NOT v_hard_block THEN
        v_ready := true;
        v_reasons := v_reasons || jsonb_build_array('OVERRIDE_APPLIED');
    END IF;

    v_input := jsonb_build_object(
        'tenant_id', p_tenant_id,
        'carrier_id', p_carrier_id,
        'action', upper(p_action),
        'policy', CASE WHEN v_policy.id IS NULL THEN NULL ELSE jsonb_build_object(
            'id', v_policy.id,
            'version', v_policy.version,
            'authority_required', v_policy.authority_required,
            'minimum_auto_liability', v_policy.minimum_auto_liability,
            'minimum_cargo', v_policy.minimum_cargo,
            'currency', v_policy.currency,
            'expiry_buffer_days', v_policy.expiry_buffer_days,
            'max_safety_age_days', v_policy.max_safety_age_days,
            'allowed_safety_ratings', v_policy.allowed_safety_ratings
        ) END,
        'authority', (
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'id', id, 'status', status, 'expires_at', expires_at,
                'evidence_hash', evidence_hash, 'version', version
            ) ORDER BY verified_at), '[]'::jsonb)
            FROM carrier_authority_records
            WHERE tenant_id = p_tenant_id AND carrier_id = p_carrier_id
        ),
        'insurance', (
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'id', id, 'type', insurance_type, 'status', status,
                'limit', limit_amount, 'currency', currency,
                'effective_at', effective_at, 'expires_at', expires_at,
                'evidence_hash', evidence_hash, 'version', version
            ) ORDER BY verified_at), '[]'::jsonb)
            FROM carrier_insurance_records
            WHERE tenant_id = p_tenant_id AND carrier_id = p_carrier_id
        ),
        'safety', CASE WHEN v_safety.id IS NULL THEN NULL ELSE jsonb_build_object(
            'id', v_safety.id, 'rating', v_safety.rating,
            'out_of_service', v_safety.out_of_service,
            'measured_at', v_safety.measured_at,
            'evidence_hash', v_safety.evidence_hash
        ) END,
        'override_ids', v_override_ids
    );

    RETURN QUERY SELECT
        v_ready,
        v_reasons,
        v_policy.version,
        encode(digest(convert_to(v_input::text, 'UTF8'), 'sha256'), 'hex');
END;
$function$;

CREATE OR REPLACE FUNCTION enforce_freight_carrier_readiness()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id uuid;
    v_carrier_id uuid;
    v_status text;
    v_action text := upper(TG_ARGV[0]);
    v_required_status text := CASE WHEN TG_NARGS > 1 THEN upper(TG_ARGV[1]) ELSE NULL END;
    v_ready boolean;
    v_reasons jsonb;
BEGIN
    v_tenant_id := NULLIF(to_jsonb(NEW)->>'tenant_id', '')::uuid;
    v_carrier_id := NULLIF(to_jsonb(NEW)->>'carrier_id', '')::uuid;
    v_status := upper(COALESCE(to_jsonb(NEW)->>'status', ''));

    IF v_carrier_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF v_required_status IS NOT NULL AND v_status <> v_required_status THEN
        RETURN NEW;
    END IF;
    IF v_action IN ('TENDER', 'ASSIGN') AND v_status IN ('CANCELLED', 'REJECTED', 'EXPIRED', 'VOID') THEN
        RETURN NEW;
    END IF;

    SELECT ready, reasons INTO v_ready, v_reasons
    FROM freight_carrier_readiness(v_tenant_id, v_carrier_id, v_action);

    IF NOT v_ready THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'CARRIER_NOT_READY',
            DETAIL = v_reasons::text,
            HINT = 'Record current authority, insurance and safety evidence or use an approved non-hard-block override.';
    END IF;
    RETURN NEW;
END;
$function$;

DO $block$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenders' AND column_name = 'carrier_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenders' AND column_name = 'tenant_id'
    ) THEN
        DROP TRIGGER IF EXISTS trg_tenders_carrier_readiness ON tenders;
        CREATE TRIGGER trg_tenders_carrier_readiness
        BEFORE INSERT OR UPDATE ON tenders
        FOR EACH ROW EXECUTE FUNCTION enforce_freight_carrier_readiness('TENDER');
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'assignments' AND column_name = 'carrier_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'assignments' AND column_name = 'tenant_id'
    ) THEN
        DROP TRIGGER IF EXISTS trg_assignments_carrier_readiness ON assignments;
        CREATE TRIGGER trg_assignments_carrier_readiness
        BEFORE INSERT OR UPDATE ON assignments
        FOR EACH ROW EXECUTE FUNCTION enforce_freight_carrier_readiness('ASSIGN');
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'loads' AND column_name = 'carrier_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'loads' AND column_name = 'tenant_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'loads' AND column_name = 'status'
    ) THEN
        DROP TRIGGER IF EXISTS trg_loads_dispatch_readiness ON loads;
        CREATE TRIGGER trg_loads_dispatch_readiness
        BEFORE INSERT OR UPDATE ON loads
        FOR EACH ROW EXECUTE FUNCTION enforce_freight_carrier_readiness('DISPATCH', 'DISPATCHED');
    END IF;
END;
$block$;
'''
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            r'''
DO $block$
BEGIN
    IF to_regclass('public.tenders') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_tenders_carrier_readiness ON tenders;
    END IF;
    IF to_regclass('public.assignments') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_assignments_carrier_readiness ON assignments;
    END IF;
    IF to_regclass('public.loads') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_loads_dispatch_readiness ON loads;
    END IF;
END;
$block$;
DROP FUNCTION IF EXISTS enforce_freight_carrier_readiness();
DROP FUNCTION IF EXISTS freight_carrier_readiness(uuid, uuid, text);
'''
        )
    )

    for table_name in reversed(TENANT_TABLES):
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "{table_name}_tenant_isolation" ON "{table_name}"'
            )
        )

    op.drop_table("carrier_readiness_decisions")
    op.drop_table("carrier_compliance_overrides")
    op.drop_table("carrier_safety_records")
    op.drop_table("carrier_insurance_records")
    op.drop_table("carrier_authority_records")
    op.drop_table("carrier_compliance_policies")
