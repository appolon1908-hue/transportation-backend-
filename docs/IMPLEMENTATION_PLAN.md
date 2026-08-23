# Freight Platform Implementation Plan

Canonical project name: `freight-platform-backend`

Implementation must proceed in reviewable, CI-gated increments. Live external actions remain capability-gated until production release requirements are satisfied.

## Backend sequence

1. Repository + CI + runtime foundation
2. PostgreSQL + migrations + tenancy
3. OIDC authentication
4. RBAC/permissions + capabilities
5. Audit + idempotency + optimistic concurrency
6. Outbox/inbox + durable jobs
7. Customers + customer locations
8. Carriers + compliance
9. Quotes + rates + margin
10. Shipments + legs + stops + commodities
11. Loads + shipment-leg assignments
12. Tendering + carrier assignment + dispatch
13. Tracking + ETA + geofences + exceptions
14. Documents + secure blob storage
15. Invoices + settlements + claims foundation
16. Webhooks + integration framework + replay
17. Notification engine
18. Reporting + search
19. Observability + security hardening
20. Performance + resilience testing
21. Deployment + rollback + production gates

## Required quality gates per implementation PR

Where applicable each PR must include:

- Domain rules and state transitions
- Database migration and downgrade/rollback path
- Unit tests
- PostgreSQL integration tests
- Authorization and tenant-isolation tests
- Idempotency/concurrency tests for material writes
- OpenAPI contract updates
- Audit/outbox behavior
- Metrics/logging/tracing
- Failure-mode handling
- Operational documentation/runbook updates

## External effect policy

The following capabilities are disabled by default until explicitly activated through production configuration and release gates:

- Live carrier tendering
- Live carrier dispatch
- Accounting exports
- Email sending
- SMS sending
- External customer portal access
- External carrier portal access
- Provider webhooks that mutate production state

## Suggested backend tree

```text
freight-platform-backend/
├── app/
│   ├── platform/
│   ├── commercial/
│   ├── carriers/
│   ├── transportation/
│   ├── visibility/
│   ├── documents/
│   ├── finance/
│   ├── integrations/
│   ├── operations/
│   ├── notifications/
│   ├── reporting/
│   └── search/
├── api/v1/
├── workers/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── security/
│   └── e2e/
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── events/
│   ├── webhooks/
│   ├── runbooks/
│   └── adr/
├── scripts/
├── docker/
├── observability/
└── .github/workflows/
```
