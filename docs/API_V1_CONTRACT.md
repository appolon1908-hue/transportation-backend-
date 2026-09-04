# Freight Platform V1 API Contract

This document is the binding route inventory for the first freight-platform backend foundation. Business authority remains in backend domain/command code; routes are transport interfaces only.

## API-wide rules

All `/api/v1/*` business endpoints are tenant-scoped and protected by authentication/permission rules except provider webhook ingress, which uses its own provider authentication/signature contract.

Material mutations require an `Idempotency-Key`. High-risk state transitions require an expected aggregate version and return `412 STALE_VERSION` when stale. Core resource reads expose `ETag` where implemented. Standard errors use `{code,message,correlation_id,fields?}`.

Live external side effects remain capability-gated and disabled by default.

## Health / platform

```text
GET    /health/live
GET    /health/ready
GET    /health/version
GET    /api/v1/me
GET    /api/v1/me/permissions
GET    /api/v1/capabilities
```

## Customers

```text
GET    /api/v1/customers
POST   /api/v1/customers
GET    /api/v1/customers/{customer_id}
PATCH  /api/v1/customers/{customer_id}
GET    /api/v1/customers/{customer_id}/locations
POST   /api/v1/customers/{customer_id}/locations
GET    /api/v1/customers/{customer_id}/contacts
POST   /api/v1/customers/{customer_id}/contacts
```

## Carriers

```text
GET    /api/v1/carriers
POST   /api/v1/carriers
GET    /api/v1/carriers/{carrier_id}
PATCH  /api/v1/carriers/{carrier_id}
GET    /api/v1/carriers/{carrier_id}/contacts
GET    /api/v1/carriers/{carrier_id}/equipment
GET    /api/v1/carriers/{carrier_id}/compliance
GET    /api/v1/carriers/{carrier_id}/insurance
POST   /api/v1/carriers/{carrier_id}/approve
POST   /api/v1/carriers/{carrier_id}/suspend
```

## Quotes

```text
GET    /api/v1/quotes
POST   /api/v1/quotes
GET    /api/v1/quotes/{quote_id}
POST   /api/v1/quotes/{quote_id}/send
POST   /api/v1/quotes/{quote_id}/accept
POST   /api/v1/quotes/{quote_id}/decline
POST   /api/v1/quotes/{quote_id}/revise
```

## Shipments

```text
GET    /api/v1/shipments
POST   /api/v1/shipments
GET    /api/v1/shipments/{shipment_id}
PATCH  /api/v1/shipments/{shipment_id}
POST   /api/v1/shipments/{shipment_id}/cancel
GET    /api/v1/shipments/{shipment_id}/legs
POST   /api/v1/shipments/{shipment_id}/legs
GET    /api/v1/shipments/{shipment_id}/stops
POST   /api/v1/shipments/{shipment_id}/stops
```

## Loads / tendering / dispatch

```text
GET    /api/v1/loads
POST   /api/v1/loads
GET    /api/v1/loads/{load_id}
POST   /api/v1/loads/{load_id}/shipment-legs
DELETE /api/v1/loads/{load_id}/shipment-legs/{leg_id}
GET    /api/v1/loads/{load_id}/carrier-search
GET    /api/v1/loads/{load_id}/tenders
POST   /api/v1/loads/{load_id}/tenders
POST   /api/v1/tenders/{tender_id}/accept
POST   /api/v1/tenders/{tender_id}/reject
POST   /api/v1/tenders/{tender_id}/withdraw
POST   /api/v1/loads/{load_id}/dispatch
POST   /api/v1/loads/{load_id}/arrive
POST   /api/v1/loads/{load_id}/depart
POST   /api/v1/loads/{load_id}/deliver
```

## Visibility / tracking

```text
GET    /api/v1/loads/{load_id}/tracking
GET    /api/v1/loads/{load_id}/positions
GET    /api/v1/loads/{load_id}/exceptions
POST   /api/v1/loads/{load_id}/tracking/manual-event
POST   /api/v1/integrations/tracking/{provider}/webhooks
```

Tracking webhook ingress requires `X-Webhook-Id`, `X-Webhook-Timestamp`, and `X-Webhook-Signature`. The signature is HMAC-SHA256 over `<timestamp>.<raw-body>`, timestamp tolerance is five minutes, body size is capped at 1 MB, and verified events are durably inserted into the inbox before `202` acknowledgement.

## Documents

```text
POST   /api/v1/documents/upload-sessions
POST   /api/v1/documents/{document_id}/confirm
GET    /api/v1/loads/{load_id}/documents
POST   /api/v1/loads/{load_id}/documents
POST   /api/v1/loads/{load_id}/pod
```

Upload, confirmation, attachment and POD write endpoints currently fail closed with `503 STORAGE_NOT_CONFIGURED`. They must not return synthetic success before secure object storage and malware scanning are implemented.

## Finance

```text
GET    /api/v1/invoices
POST   /api/v1/invoices
GET    /api/v1/invoices/{invoice_id}
POST   /api/v1/invoices/{invoice_id}/approve
POST   /api/v1/invoices/{invoice_id}/void

GET    /api/v1/carrier-settlements
POST   /api/v1/carrier-settlements
GET    /api/v1/carrier-settlements/{settlement_id}
POST   /api/v1/carrier-settlements/{settlement_id}/approve

GET    /api/v1/claims
POST   /api/v1/claims
GET    /api/v1/claims/{claim_id}
```

## Operations

```text
GET    /api/v1/operations/exceptions
POST   /api/v1/operations/exceptions/{exception_id}/acknowledge
POST   /api/v1/operations/exceptions/{exception_id}/assign
POST   /api/v1/operations/exceptions/{exception_id}/resolve
GET    /api/v1/operations/dead-letters
POST   /api/v1/operations/dead-letters/{message_id}/replay
```

## Administration

```text
GET    /api/v1/admin/users
GET    /api/v1/admin/roles
GET    /api/v1/admin/permissions
GET    /api/v1/admin/capabilities
PATCH  /api/v1/admin/capabilities/{code}
```

`GET /api/v1/admin/users` currently fails explicitly with `501 IDENTITY_DIRECTORY_NOT_IMPLEMENTED`; persistent external identity/user-directory storage belongs to the authentication/authorization PR and must not be faked.

## Current capability defaults

```text
carrier.live_tender_send = disabled
carrier.live_dispatch_notification = disabled
email.live_send = disabled
sms.live_send = disabled
accounting.live_export = disabled
customer_portal.external_access = disabled
carrier_portal.external_access = disabled
```

## Next API implementation gates

The route inventory above is not the same as production readiness. Remaining mandatory work includes persistent identity/RBAC, PostgreSQL RLS, DB-level compare-and-swap/locking for high-contention transitions, outbox/inbox worker leasing and delivery adapters, secure document storage/scanning, provider ETA/geofence adapters, full integration/negative/concurrency tests, staging, restore rehearsal, canary and rollback evidence.
