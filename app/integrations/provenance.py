from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.crypto import canonical_json, payload_hash, sha256_hex
from app.integrations.models import ProvenanceHead, ProvenanceRecord

ZERO_HASH = "0" * 64


def _record_material(
    *,
    tenant_id: UUID,
    stream: str,
    sequence: int,
    previous_hash: str,
    event_type: str,
    entity_id: str,
    payload_digest: str,
    actor_id: str,
    correlation_id: str,
    metadata: dict[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "tenant_id": str(tenant_id),
        "stream": stream,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "event_type": event_type,
        "entity_id": entity_id,
        "payload_hash": payload_digest,
        "actor_id": actor_id,
        "correlation_id": correlation_id,
        "metadata": metadata,
        "created_at": created_at.isoformat(),
    }


async def append_provenance(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    stream: str,
    event_type: str,
    entity_id: str,
    payload: Any,
    actor_id: str,
    correlation_id: str,
    metadata: dict[str, Any] | None = None,
) -> ProvenanceRecord:
    """Append one record while serializing writers for the tenant stream."""

    lock_key = f"{tenant_id}:{stream}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": lock_key})

    head = await db.scalar(
        select(ProvenanceHead).where(
            ProvenanceHead.tenant_id == tenant_id,
            ProvenanceHead.stream == stream,
        )
    )
    if head is None:
        head = ProvenanceHead(
            tenant_id=tenant_id,
            stream=stream,
            sequence=0,
            head_hash=ZERO_HASH,
        )
        db.add(head)
        await db.flush()

    created_at = datetime.now(timezone.utc)
    sequence = head.sequence + 1
    metadata_value = metadata or {}
    digest = payload_hash(payload)
    material = _record_material(
        tenant_id=tenant_id,
        stream=stream,
        sequence=sequence,
        previous_hash=head.head_hash,
        event_type=event_type,
        entity_id=entity_id,
        payload_digest=digest,
        actor_id=actor_id,
        correlation_id=correlation_id,
        metadata=metadata_value,
        created_at=created_at,
    )
    record_hash = sha256_hex(canonical_json(material))
    record = ProvenanceRecord(
        tenant_id=tenant_id,
        stream=stream,
        sequence=sequence,
        previous_hash=head.head_hash,
        record_hash=record_hash,
        event_type=event_type,
        entity_id=entity_id,
        payload_hash=digest,
        actor_id=actor_id,
        correlation_id=correlation_id,
        metadata_json=metadata_value,
        created_at=created_at,
    )
    db.add(record)
    head.sequence = sequence
    head.head_hash = record_hash
    head.updated_at = created_at
    await db.flush()
    return record


async def verify_provenance_stream(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    stream: str,
) -> dict[str, Any]:
    records = (
        await db.scalars(
            select(ProvenanceRecord)
            .where(
                ProvenanceRecord.tenant_id == tenant_id,
                ProvenanceRecord.stream == stream,
            )
            .order_by(ProvenanceRecord.sequence)
        )
    ).all()

    previous_hash = ZERO_HASH
    expected_sequence = 1
    for record in records:
        material = _record_material(
            tenant_id=record.tenant_id,
            stream=record.stream,
            sequence=record.sequence,
            previous_hash=record.previous_hash,
            event_type=record.event_type,
            entity_id=record.entity_id,
            payload_digest=record.payload_hash,
            actor_id=record.actor_id,
            correlation_id=record.correlation_id,
            metadata=record.metadata_json,
            created_at=record.created_at,
        )
        calculated = sha256_hex(canonical_json(material))
        if (
            record.sequence != expected_sequence
            or record.previous_hash != previous_hash
            or record.record_hash != calculated
        ):
            return {
                "valid": False,
                "stream": stream,
                "failed_sequence": record.sequence,
                "records_checked": expected_sequence - 1,
            }
        previous_hash = record.record_hash
        expected_sequence += 1

    head = await db.scalar(
        select(ProvenanceHead).where(
            ProvenanceHead.tenant_id == tenant_id,
            ProvenanceHead.stream == stream,
        )
    )
    head_valid = head is None or (
        head.sequence == len(records) and head.head_hash == previous_hash
    )
    return {
        "valid": head_valid,
        "stream": stream,
        "records_checked": len(records),
        "head_hash": previous_hash,
    }
