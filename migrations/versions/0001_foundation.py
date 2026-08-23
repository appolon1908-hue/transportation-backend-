"""initial freight platform foundation

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-23
"""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("""
    CREATE TABLE capabilities (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, code varchar(120) NOT NULL,
      enabled boolean NOT NULL DEFAULT false, updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_capability_tenant_code UNIQUE (tenant_id, code)
    );
    CREATE INDEX ix_capabilities_tenant_id ON capabilities(tenant_id);

    CREATE TABLE customers (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      name varchar(250) NOT NULL, external_reference varchar(120), currency varchar(3) NOT NULL DEFAULT 'USD',
      is_active boolean NOT NULL DEFAULT true
    );
    CREATE INDEX ix_customers_tenant_id ON customers(tenant_id);

    CREATE TABLE customer_locations (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      name varchar(180) NOT NULL, address1 varchar(250) NOT NULL, city varchar(120) NOT NULL,
      region varchar(80) NOT NULL, postal_code varchar(32) NOT NULL, country varchar(2) NOT NULL DEFAULT 'US'
    );
    CREATE INDEX ix_customer_locations_tenant_id ON customer_locations(tenant_id);
    CREATE INDEX ix_customer_locations_customer_id ON customer_locations(customer_id);

    CREATE TABLE customer_contacts (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      name varchar(180) NOT NULL, email varchar(254), phone varchar(40)
    );
    CREATE INDEX ix_customer_contacts_tenant_id ON customer_contacts(tenant_id);
    CREATE INDEX ix_customer_contacts_customer_id ON customer_contacts(customer_id);

    CREATE TABLE carriers (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      legal_name varchar(250) NOT NULL, mc_number varchar(40), dot_number varchar(40),
      is_active boolean NOT NULL DEFAULT true, compliance_status varchar(40) NOT NULL DEFAULT 'PENDING'
    );
    CREATE INDEX ix_carriers_tenant_id ON carriers(tenant_id);

    CREATE TABLE carrier_contacts (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
      name varchar(180) NOT NULL, email varchar(254), phone varchar(40)
    );
    CREATE INDEX ix_carrier_contacts_tenant_id ON carrier_contacts(tenant_id);
    CREATE INDEX ix_carrier_contacts_carrier_id ON carrier_contacts(carrier_id);

    CREATE TABLE carrier_equipment (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
      equipment_type varchar(60) NOT NULL, unit_number varchar(80), is_active boolean NOT NULL DEFAULT true
    );
    CREATE INDEX ix_carrier_equipment_tenant_id ON carrier_equipment(tenant_id);
    CREATE INDEX ix_carrier_equipment_carrier_id ON carrier_equipment(carrier_id);

    CREATE TABLE carrier_compliance (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
      authority_status varchar(40) NOT NULL DEFAULT 'PENDING', safety_status varchar(40) NOT NULL DEFAULT 'PENDING', notes text
    );
    CREATE INDEX ix_carrier_compliance_tenant_id ON carrier_compliance(tenant_id);
    CREATE INDEX ix_carrier_compliance_carrier_id ON carrier_compliance(carrier_id);

    CREATE TABLE carrier_insurance (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
      policy_number varchar(120) NOT NULL, coverage_type varchar(80) NOT NULL, expires_at timestamptz NOT NULL
    );
    CREATE INDEX ix_carrier_insurance_tenant_id ON carrier_insurance(tenant_id);
    CREATE INDEX ix_carrier_insurance_carrier_id ON carrier_insurance(carrier_id);

    CREATE TABLE quotes (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      status varchar(40) NOT NULL DEFAULT 'DRAFT', currency varchar(3) NOT NULL DEFAULT 'USD',
      sell_total_minor integer NOT NULL DEFAULT 0, buy_total_minor integer NOT NULL DEFAULT 0, expires_at timestamptz
    );
    CREATE INDEX ix_quotes_tenant_id ON quotes(tenant_id);
    CREATE INDEX ix_quotes_customer_id ON quotes(customer_id);

    CREATE TABLE quote_versions (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      quote_id uuid NOT NULL REFERENCES quotes(id) ON DELETE RESTRICT, revision integer NOT NULL,
      sell_total_minor integer NOT NULL, buy_total_minor integer NOT NULL, accessorials jsonb NOT NULL DEFAULT '{}'::jsonb,
      CONSTRAINT uq_quote_revision UNIQUE (quote_id, revision)
    );
    CREATE INDEX ix_quote_versions_tenant_id ON quote_versions(tenant_id);
    CREATE INDEX ix_quote_versions_quote_id ON quote_versions(quote_id);

    CREATE TABLE shipments (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      customer_reference varchar(120) NOT NULL, mode varchar(30) NOT NULL DEFAULT 'FTL', status varchar(40) NOT NULL DEFAULT 'DRAFT'
    );
    CREATE INDEX ix_shipments_tenant_id ON shipments(tenant_id);
    CREATE INDEX ix_shipments_customer_id ON shipments(customer_id);

    CREATE TABLE shipment_legs (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      shipment_id uuid NOT NULL REFERENCES shipments(id) ON DELETE RESTRICT, sequence integer NOT NULL,
      origin_city varchar(120) NOT NULL, origin_region varchar(80) NOT NULL,
      destination_city varchar(120) NOT NULL, destination_region varchar(80) NOT NULL,
      pickup_at timestamptz, delivery_at timestamptz,
      CONSTRAINT uq_shipment_leg_sequence UNIQUE (shipment_id, sequence)
    );
    CREATE INDEX ix_shipment_legs_tenant_id ON shipment_legs(tenant_id);
    CREATE INDEX ix_shipment_legs_shipment_id ON shipment_legs(shipment_id);

    CREATE TABLE stops (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      shipment_id uuid NOT NULL REFERENCES shipments(id) ON DELETE RESTRICT,
      sequence integer NOT NULL, stop_type varchar(30) NOT NULL, city varchar(120) NOT NULL,
      region varchar(80) NOT NULL, appointment_at timestamptz
    );
    CREATE INDEX ix_stops_tenant_id ON stops(tenant_id);
    CREATE INDEX ix_stops_shipment_id ON stops(shipment_id);

    CREATE TABLE loads (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      load_number varchar(80) NOT NULL, equipment_type varchar(60) NOT NULL DEFAULT 'DRY_VAN',
      status varchar(40) NOT NULL DEFAULT 'DRAFT', carrier_id uuid REFERENCES carriers(id) ON DELETE RESTRICT,
      carrier_rate numeric(19,4), currency varchar(3) NOT NULL DEFAULT 'USD',
      CONSTRAINT uq_load_number UNIQUE (tenant_id, load_number)
    );
    CREATE INDEX ix_loads_tenant_id ON loads(tenant_id);

    CREATE TABLE load_shipment_legs (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      load_id uuid NOT NULL REFERENCES loads(id) ON DELETE RESTRICT,
      shipment_leg_id uuid NOT NULL REFERENCES shipment_legs(id) ON DELETE RESTRICT,
      CONSTRAINT uq_load_leg UNIQUE (tenant_id, load_id, shipment_leg_id)
    );
    CREATE INDEX ix_load_shipment_legs_tenant_id ON load_shipment_legs(tenant_id);
    CREATE INDEX ix_load_shipment_legs_load_id ON load_shipment_legs(load_id);
    CREATE INDEX ix_load_shipment_legs_leg_id ON load_shipment_legs(shipment_leg_id);

    CREATE TABLE tenders (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      load_id uuid NOT NULL REFERENCES loads(id) ON DELETE RESTRICT,
      carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
      status varchar(40) NOT NULL DEFAULT 'SENT', rate numeric(19,4) NOT NULL,
      currency varchar(3) NOT NULL DEFAULT 'USD', expires_at timestamptz
    );
    CREATE INDEX ix_tenders_tenant_id ON tenders(tenant_id);
    CREATE INDEX ix_tenders_load_id ON tenders(load_id);
    CREATE INDEX ix_tenders_carrier_id ON tenders(carrier_id);

    CREATE TABLE tracking_events (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      load_id uuid NOT NULL REFERENCES loads(id) ON DELETE RESTRICT,
      event_type varchar(80) NOT NULL, occurred_at timestamptz NOT NULL,
      latitude numeric(9,6), longitude numeric(9,6), payload jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX ix_tracking_events_tenant_id ON tracking_events(tenant_id);
    CREATE INDEX ix_tracking_events_load_id ON tracking_events(load_id);

    CREATE TABLE documents (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      load_id uuid REFERENCES loads(id) ON DELETE RESTRICT, purpose varchar(60) NOT NULL,
      status varchar(40) NOT NULL DEFAULT 'PENDING_UPLOAD', object_key varchar(500), checksum_sha256 varchar(64)
    );
    CREATE INDEX ix_documents_tenant_id ON documents(tenant_id);
    CREATE INDEX ix_documents_load_id ON documents(load_id);

    CREATE TABLE invoices (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
      shipment_id uuid REFERENCES shipments(id) ON DELETE RESTRICT, status varchar(40) NOT NULL DEFAULT 'DRAFT',
      total_minor integer NOT NULL DEFAULT 0, currency varchar(3) NOT NULL DEFAULT 'USD'
    );
    CREATE INDEX ix_invoices_tenant_id ON invoices(tenant_id);
    CREATE INDEX ix_invoices_customer_id ON invoices(customer_id);

    CREATE TABLE carrier_settlements (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      carrier_id uuid NOT NULL REFERENCES carriers(id) ON DELETE RESTRICT,
      load_id uuid REFERENCES loads(id) ON DELETE RESTRICT, status varchar(40) NOT NULL DEFAULT 'DRAFT',
      total_minor integer NOT NULL DEFAULT 0, currency varchar(3) NOT NULL DEFAULT 'USD'
    );
    CREATE INDEX ix_carrier_settlements_tenant_id ON carrier_settlements(tenant_id);
    CREATE INDEX ix_carrier_settlements_carrier_id ON carrier_settlements(carrier_id);

    CREATE TABLE claims (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      shipment_id uuid NOT NULL REFERENCES shipments(id) ON DELETE RESTRICT,
      status varchar(40) NOT NULL DEFAULT 'OPEN', description text NOT NULL
    );
    CREATE INDEX ix_claims_tenant_id ON claims(tenant_id);
    CREATE INDEX ix_claims_shipment_id ON claims(shipment_id);

    CREATE TABLE operational_exceptions (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      code varchar(80) NOT NULL, status varchar(40) NOT NULL DEFAULT 'OPEN', resource_type varchar(80) NOT NULL,
      resource_id uuid, assigned_to varchar(200), detail text
    );
    CREATE INDEX ix_operational_exceptions_tenant_id ON operational_exceptions(tenant_id);
    CREATE INDEX ix_operational_exceptions_code ON operational_exceptions(code);

    CREATE TABLE audit_entries (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, actor_id varchar(200) NOT NULL,
      action varchar(120) NOT NULL, resource_type varchar(80) NOT NULL, resource_id uuid,
      correlation_id varchar(80) NOT NULL, metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_audit_entries_tenant_id ON audit_entries(tenant_id);
    CREATE INDEX ix_audit_entries_action ON audit_entries(action);

    CREATE TABLE idempotency_records (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, actor_id varchar(200) NOT NULL,
      operation varchar(120) NOT NULL, key varchar(200) NOT NULL, request_hash varchar(64) NOT NULL,
      status varchar(40) NOT NULL DEFAULT 'IN_PROGRESS', response_json jsonb, created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_idempotency_scope UNIQUE (tenant_id, actor_id, operation, key)
    );
    CREATE INDEX ix_idempotency_records_tenant_id ON idempotency_records(tenant_id);

    CREATE TABLE outbox_messages (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, event_type varchar(160) NOT NULL,
      aggregate_type varchar(80) NOT NULL, aggregate_id uuid NOT NULL, aggregate_version integer NOT NULL,
      schema_version integer NOT NULL DEFAULT 1, payload jsonb NOT NULL, destination varchar(120) NOT NULL DEFAULT 'freight-events',
      status varchar(40) NOT NULL DEFAULT 'PENDING_CONFIGURATION', attempts integer NOT NULL DEFAULT 0,
      correlation_id varchar(80) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_outbox_messages_tenant_id ON outbox_messages(tenant_id);
    CREATE INDEX ix_outbox_messages_event_type ON outbox_messages(event_type);

    CREATE TABLE inbox_messages (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL, provider varchar(120) NOT NULL,
      external_event_id varchar(200) NOT NULL, event_type varchar(160) NOT NULL, raw_hash varchar(64) NOT NULL,
      signature_verified boolean NOT NULL DEFAULT false, payload jsonb NOT NULL,
      status varchar(40) NOT NULL DEFAULT 'PENDING', attempts integer NOT NULL DEFAULT 0,
      received_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_inbox_external_event UNIQUE (provider, external_event_id)
    );
    CREATE INDEX ix_inbox_messages_tenant_id ON inbox_messages(tenant_id);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS inbox_messages;
    DROP TABLE IF EXISTS outbox_messages;
    DROP TABLE IF EXISTS idempotency_records;
    DROP TABLE IF EXISTS audit_entries;
    DROP TABLE IF EXISTS operational_exceptions;
    DROP TABLE IF EXISTS claims;
    DROP TABLE IF EXISTS carrier_settlements;
    DROP TABLE IF EXISTS invoices;
    DROP TABLE IF EXISTS documents;
    DROP TABLE IF EXISTS tracking_events;
    DROP TABLE IF EXISTS tenders;
    DROP TABLE IF EXISTS load_shipment_legs;
    DROP TABLE IF EXISTS loads;
    DROP TABLE IF EXISTS stops;
    DROP TABLE IF EXISTS shipment_legs;
    DROP TABLE IF EXISTS shipments;
    DROP TABLE IF EXISTS quote_versions;
    DROP TABLE IF EXISTS quotes;
    DROP TABLE IF EXISTS carrier_insurance;
    DROP TABLE IF EXISTS carrier_compliance;
    DROP TABLE IF EXISTS carrier_equipment;
    DROP TABLE IF EXISTS carrier_contacts;
    DROP TABLE IF EXISTS carriers;
    DROP TABLE IF EXISTS customer_contacts;
    DROP TABLE IF EXISTS customer_locations;
    DROP TABLE IF EXISTS customers;
    DROP TABLE IF EXISTS capabilities;
    """)
