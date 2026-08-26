from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, set_session_context
from app.main import app
from app.models import AuditEntry, OutboxMessage

POSTGRES_AVAILABLE = os.getenv("DATABASE_URL", "").startswith("postgresql")
client = TestClient(app)


async def _seed_dead_letter(tenant_id, message_id, aggregate_id) -> None:
    async with SessionLocal() as db:
        await set_session_context(db, tenant_id, "dead-letter-seed")
        db.add(
            OutboxMessage(
                id=message_id,
                tenant_id=tenant_id,
                event_type="load.dispatch.failed.v1",
                aggregate_type="Load",
                aggregate_id=aggregate_id,
                aggregate_version=3,
                payload={"load_id": str(aggregate_id)},
                status="FAILED_TERMINAL",
                attempts=5,
                correlation_id=f"seed-{message_id}",
            )
        )
        await db.commit()


async def _read_replay_evidence(tenant_id, message_id):
    async with SessionLocal() as db:
        await set_session_context(db, tenant_id, "dead-letter-verify")
        message = await db.scalar(
            select(OutboxMessage).where(
                OutboxMessage.id == message_id,
                OutboxMessage.tenant_id == tenant_id,
            )
        )
        audit = await db.scalar(
            select(AuditEntry).where(
                AuditEntry.tenant_id == tenant_id,
                AuditEntry.action == "DEAD_LETTER_REPLAYED",
                AuditEntry.resource_id == message_id,
            )
        )
        replay_event = await db.scalar(
            select(OutboxMessage).where(
                OutboxMessage.tenant_id == tenant_id,
                OutboxMessage.event_type == "operations.dead_letter.replayed.v1",
                OutboxMessage.aggregate_id == message_id,
            )
        )
        return message, audit, replay_event


def _headers(tenant_id, idempotency_key: str) -> dict[str, str]:
    return {
        "X-Dev-Tenant-Id": str(tenant_id),
        "X-Dev-Actor": "operations-test",
        "X-Dev-Permissions": "integration.retry",
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL contract database is not configured")
def test_dead_letter_replay_is_idempotent_audited_and_evented() -> None:
    tenant_id = uuid4()
    message_id = uuid4()
    aggregate_id = uuid4()
    key = f"dead-letter-replay-{message_id}"
    asyncio.run(_seed_dead_letter(tenant_id, message_id, aggregate_id))

    first = client.post(
        f"/api/v1/operations/dead-letters/{message_id}/replay",
        headers=_headers(tenant_id, key),
        json={"reason": "Operator verified the integration configuration."},
    )
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is True
    assert first.json()["previous_attempts"] == 5
    assert first.json()["status"] == "PENDING_CONFIGURATION"

    duplicate = client.post(
        f"/api/v1/operations/dead-letters/{message_id}/replay",
        headers=_headers(tenant_id, key),
        json={"reason": "Operator verified the integration configuration."},
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()

    message, audit, replay_event = asyncio.run(
        _read_replay_evidence(tenant_id, message_id)
    )
    assert message is not None
    assert message.status == "PENDING_CONFIGURATION"
    assert message.attempts == 0
    assert audit is not None
    assert replay_event is not None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL contract database is not configured")
def test_dead_letter_replay_rejects_nonterminal_message() -> None:
    tenant_id = uuid4()
    message_id = uuid4()
    aggregate_id = uuid4()
    asyncio.run(_seed_dead_letter(tenant_id, message_id, aggregate_id))

    first = client.post(
        f"/api/v1/operations/dead-letters/{message_id}/replay",
        headers=_headers(tenant_id, f"first-{message_id}"),
        json={"reason": "First authorized replay."},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/operations/dead-letters/{message_id}/replay",
        headers=_headers(tenant_id, f"second-{message_id}"),
        json={"reason": "A second replay must be rejected."},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "DEAD_LETTER_NOT_REPLAYABLE"
