# Freight Platform Feature Branch Ownership

Release work is stacked and reviewed in dependency order. A branch owns one architectural concern; it must not become a dumping ground for unrelated features.

## Backend stack

```text
be/freight-platform-foundation
  └─ core domain models, migrations, command/idempotency foundation

be/identity-tenancy-rbac-v2
  └─ OIDC, local principals, memberships, RBAC and tenant isolation

be/integrations-webhooks-provenance-v3
  └─ Odoo, n8n, signed webhooks, inbox/outbox and provenance

be/compliance-gateway-production-v4
  └─ carrier compliance, Kong, Caddy and production ingress controls

be/domain-workflows-portals-v5
  └─ admin, operations, customer and carrier portal workflows

be/release-readiness-v6
  └─ consolidated release gates and immutable deployment packaging

be/fix-compliance-contract-gate-v1
  └─ isolated compatibility and CI repairs for the compliance release gate

be/api-contract-readiness-v1
  └─ canonical release identity, OpenAPI security, duplicate-route removal,
     endpoint inventory and API contract tests
```

## Frontend stack

```text
fe/freight-platform-foundation
  └─ Vue application foundation

fe/auth-portal-shell-v2
  └─ OIDC Authorization Code + PKCE and authorization boundary

fe/portal-shell-authz-api-v2
  └─ typed API client and portal shell

fe/release-readiness-v4
  └─ admin, operations, customer and carrier workspaces, browser E2E and
     deterministic production build
```

## Reserved next feature branches

Create these only with real implementation commits; do not create empty branches.

```text
be/documents-secure-storage-v1
  object storage, presigned upload, checksum/content validation, malware scan,
  quarantine, retention and download authorization

be/integration-operations-hardening-v1
  command-backed dead-letter replay, delivery collision/concurrency hardening,
  operational audit and replay authorization

be/observability-slo-v1
  metrics, traces, structured audit dashboards, alert rules and SLO evidence

fe/documents-workflows-v1
  authorized upload, scan/quarantine status, document review and POD workflows
```

## Merge rules

1. Each branch targets its direct dependency, not `main`.
2. Every branch must have an independently reviewed exact head.
3. Required CI must be green on the unchanged reviewed SHA.
4. The protected release branch is assembled in dependency order.
5. Images are built only from the exact protected merged SHA.
6. No feature branch may deploy or enable a live capability.
7. Repository rename, workflow identity, image names and deployment references move in one controlled repository-identity change.
