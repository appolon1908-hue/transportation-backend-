from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands import execute_command
from app.db import get_db
from app.integrations.provenance import append_provenance
from app.models import Customer, Document, Invoice, Load, Shipment, TrackingEvent
from app.portals.models import PortalClaimSubmission
from app.portals.schemas import ClaimSubmissionIn
from app.portals.service import (
    column,
    documents_for_resources,
    has_column,
    page_rows,
    require_bound_resource,
    require_portal_binding,
    serialize_columns,
)
from app.security import Actor, get_actor

router = APIRouter(prefix="/api/v1/portals/customer", tags=["customer-portal"])

CUSTOMER_FIELDS = {
    "id", "name", "status", "code", "email", "phone", "created_at", "updated_at"
}
SHIPMENT_FIELDS = {
    "id", "customer_id", "quote_id", "reference", "status", "mode",
    "origin", "destination", "pickup_at", "delivery_at", "created_at", "updated_at", "version"
}
LOAD_FIELDS = {
    "id", "shipment_id", "reference", "status", "carrier_id", "pickup_at",
    "delivery_at", "created_at", "updated_at", "version"
}
TRACKING_FIELDS = {
    "id", "load_id", "event_type", "occurred_at", "latitude", "longitude", "payload", "created_at"
}
DOCUMENT_FIELDS = {
    "id", "resource_type", "resource_id", "document_type", "name", "filename",
    "status", "content_type", "size_bytes", "created_at", "updated_at", "version"
}
INVOICE_FIELDS = {
    "id", "customer_id", "shipment_id", "invoice_number", "status", "currency",
    "subtotal", "tax", "total", "total_amount", "due_at", "issued_at", "paid_at",
    "created_at", "updated_at", "version"
}
CLAIM_FIELDS = {
    "id", "customer_id", "shipment_id", "claim_type", "title", "description",
    "claimed_amount", "currency", "evidence_document_ids", "status",
    "customer_visible_note", "version", "created_at", "updated_at"
}


def _require_customer_mapping() -> None:
    if not has_column(Shipment, "customer_id"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CUSTOMER_PORTAL_MAPPING_UNAVAILABLE",
                "message": "Shipment customer ownership is not available in the current schema.",
            },
        )


async def _binding(db: AsyncSession, actor: Actor, request: Request):
    return await require_portal_binding(
        db,
        actor=actor,
        portal_kind="CUSTOMER",
        capability_code="customer_portal.external_access",
        action=f"{request.method} {request.url.path}",
        correlation_id=request.state.correlation_id,
    )


async def _customer_shipments(db: AsyncSession, actor: Actor, customer_id: UUID) -> list[UUID]:
    _require_customer_mapping()
    return list(
        await db.scalars(
            select(column(Shipment, "id")).where(
                column(Shipment, "tenant_id") == actor.tenant_id,
                column(Shipment, "customer_id") == customer_id,
            )
        )
    )


@router.get("/context")
async def customer_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    customer = await db.scalar(
        select(Customer).where(
            Customer.tenant_id == actor.tenant_id,
            Customer.id == binding.resource_id,
        )
    )
    if customer is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "BOUND_CUSTOMER_MISSING", "message": "Bound customer account no longer exists."},
        )
    await db.commit()
    return {
        "portal": "CUSTOMER",
        "binding": {
            "id": binding.id,
            "display_label": binding.display_label,
            "status": binding.status,
            "version": binding.version,
        },
        "customer": serialize_columns(customer, CUSTOMER_FIELDS),
    }


@router.get("/shipments")
async def list_customer_shipments(
    request: Request,
    shipment_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    _require_customer_mapping()
    statement = select(Shipment).where(
        column(Shipment, "tenant_id") == actor.tenant_id,
        column(Shipment, "customer_id") == binding.resource_id,
    )
    if shipment_status and has_column(Shipment, "status"):
        statement = statement.where(column(Shipment, "status") == shipment_status.upper())
    items, next_cursor = await page_rows(
        db,
        statement=statement,
        model=Shipment,
        limit=limit,
        cursor=cursor,
    )
    await db.commit()
    return {
        "items": [serialize_columns(item, SHIPMENT_FIELDS) for item in items],
        "next_cursor": next_cursor,
    }


@router.get("/shipments/{shipment_id}")
async def customer_shipment_detail(
    shipment_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    _require_customer_mapping()
    shipment = await require_bound_resource(
        db,
        model=Shipment,
        actor=actor,
        binding=binding,
        resource_id=shipment_id,
        ownership_column="customer_id",
        resource_type="Shipment",
        action="customer.shipment.read",
        correlation_id=request.state.correlation_id,
    )
    loads = []
    if has_column(Load, "shipment_id"):
        loads = list(
            (
                await db.scalars(
                    select(Load).where(
                        column(Load, "tenant_id") == actor.tenant_id,
                        column(Load, "shipment_id") == shipment_id,
                    )
                )
            ).all()
        )
    load_ids = [item.id for item in loads]
    tracking = []
    if load_ids and has_column(TrackingEvent, "load_id"):
        tracking = list(
            (
                await db.scalars(
                    select(TrackingEvent)
                    .where(
                        column(TrackingEvent, "tenant_id") == actor.tenant_id,
                        column(TrackingEvent, "load_id").in_(load_ids),
                    )
                    .order_by(column(TrackingEvent, "occurred_at").desc())
                    .limit(200)
                )
            ).all()
        )
    documents = await documents_for_resources(
        db,
        tenant_id=actor.tenant_id,
        resource_ids=[shipment_id, *load_ids],
        resource_types=["Shipment", "Load", "shipment", "load"],
        limit=200,
    )
    await db.commit()
    return {
        "shipment": serialize_columns(shipment, SHIPMENT_FIELDS),
        "loads": [serialize_columns(item, LOAD_FIELDS) for item in loads],
        "tracking": [serialize_columns(item, TRACKING_FIELDS) for item in tracking],
        "documents": [serialize_columns(item, DOCUMENT_FIELDS) for item in documents],
    }


@router.get("/documents")
async def list_customer_documents(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    shipment_ids = await _customer_shipments(db, actor, binding.resource_id)
    load_ids: list[UUID] = []
    if shipment_ids and has_column(Load, "shipment_id"):
        load_ids = list(
            await db.scalars(
                select(column(Load, "id")).where(
                    column(Load, "tenant_id") == actor.tenant_id,
                    column(Load, "shipment_id").in_(shipment_ids),
                )
            )
        )
    items = await documents_for_resources(
        db,
        tenant_id=actor.tenant_id,
        resource_ids=[*shipment_ids, *load_ids],
        resource_types=["Shipment", "Load", "shipment", "load"],
        limit=limit,
    )
    await db.commit()
    return {"items": [serialize_columns(item, DOCUMENT_FIELDS) for item in items]}


@router.get("/invoices")
async def list_customer_invoices(
    request: Request,
    invoice_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    if not has_column(Invoice, "customer_id"):
        raise HTTPException(status_code=503, detail={"code": "INVOICE_CUSTOMER_MAPPING_UNAVAILABLE", "message": "Invoice customer ownership is unavailable."})
    statement = select(Invoice).where(
        column(Invoice, "tenant_id") == actor.tenant_id,
        column(Invoice, "customer_id") == binding.resource_id,
    )
    if invoice_status and has_column(Invoice, "status"):
        statement = statement.where(column(Invoice, "status") == invoice_status.upper())
    items, next_cursor = await page_rows(db, statement=statement, model=Invoice, limit=limit, cursor=cursor)
    await db.commit()
    return {
        "items": [serialize_columns(item, INVOICE_FIELDS) for item in items],
        "next_cursor": next_cursor,
    }


@router.get("/claims")
async def list_customer_claims(
    request: Request,
    claim_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    statement = select(PortalClaimSubmission).where(
        PortalClaimSubmission.tenant_id == actor.tenant_id,
        PortalClaimSubmission.customer_id == binding.resource_id,
    )
    if claim_status:
        statement = statement.where(PortalClaimSubmission.status == claim_status.upper())
    items, next_cursor = await page_rows(
        db,
        statement=statement,
        model=PortalClaimSubmission,
        limit=limit,
        cursor=cursor,
    )
    await db.commit()
    return {
        "items": [serialize_columns(item, CLAIM_FIELDS) for item in items],
        "next_cursor": next_cursor,
    }


@router.post("/claims", status_code=201)
async def submit_customer_claim(
    payload: ClaimSubmissionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    binding = await _binding(db, actor, request)
    _require_customer_mapping()
    await require_bound_resource(
        db,
        model=Shipment,
        actor=actor,
        binding=binding,
        resource_id=payload.shipment_id,
        ownership_column="customer_id",
        resource_type="Shipment",
        action="customer.claim.submit",
        correlation_id=request.state.correlation_id,
    )
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={"code": "IDEMPOTENCY_KEY_REQUIRED", "message": "Idempotency-Key is required."},
        )

    if payload.evidence_document_ids:
        allowed_documents = await documents_for_resources(
            db,
            tenant_id=actor.tenant_id,
            resource_ids=[payload.shipment_id],
            resource_types=["Shipment", "shipment"],
            limit=200,
        )
        allowed_ids = {item.id for item in allowed_documents}
        if not set(payload.evidence_document_ids).issubset(allowed_ids):
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_CLAIM_EVIDENCE", "message": "One or more evidence documents are not available to this customer shipment."},
            )

    async def action():
        item = PortalClaimSubmission(
            tenant_id=actor.tenant_id,
            customer_id=binding.resource_id,
            shipment_id=payload.shipment_id,
            submitted_by_subject=actor.subject,
            submission_key=idempotency_key,
            claim_type=payload.claim_type,
            title=payload.title,
            description=payload.description,
            claimed_amount=payload.claimed_amount,
            currency=payload.currency,
            evidence_document_ids=[str(item) for item in payload.evidence_document_ids],
            status="SUBMITTED",
        )
        db.add(item)
        await db.flush()
        await append_provenance(
            db,
            tenant_id=actor.tenant_id,
            stream="portal.customer.claims",
            event_type="customer.claim.submitted",
            entity_id=str(item.id),
            payload={
                "customer_id": str(item.customer_id),
                "shipment_id": str(item.shipment_id),
                "claim_type": item.claim_type,
                "claimed_amount": str(item.claimed_amount),
                "currency": item.currency,
                "evidence_document_ids": item.evidence_document_ids,
            },
            actor_id=actor.subject,
            correlation_id=request.state.correlation_id,
        )
        return serialize_columns(item, CLAIM_FIELDS), "PortalClaimSubmission", item.id, item.version

    return await execute_command(
        db=db,
        request=request,
        actor=actor,
        operation="customer.portal.claim.submit",
        payload=payload.model_dump(mode="json"),
        action=action,
        event_type="customer.portal.claim.submitted.v1",
        audit_action="CUSTOMER_PORTAL_CLAIM_SUBMITTED",
    )
