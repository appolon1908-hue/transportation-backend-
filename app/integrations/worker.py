from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.integrations.crypto import SecretResolver
from app.integrations.service import (
    claim_delivery_batch,
    claim_inbound_batch,
    fanout_outbox_batch,
    process_delivery,
    process_inbound,
    release_capability_blocked,
)

LOG = logging.getLogger("freight.integrations.worker")


def _configure_logging() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(message)s")


def _log(event: str, **fields: object) -> None:
    LOG.info(json.dumps({"event": event, **fields}, default=str, sort_keys=True))


def _database_url() -> str:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    worker_url = os.getenv("WORKER_DATABASE_URL")
    if environment == "production" and not worker_url:
        raise RuntimeError("WORKER_DATABASE_URL is required in production.")
    value = worker_url or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("A database URL is required for the integration worker.")
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


@asynccontextmanager
async def _session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        _database_url(),
        pool_pre_ping=True,
        pool_size=int(os.getenv("WORKER_DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("WORKER_DB_MAX_OVERFLOW", "5")),
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _assert_worker_role(db: AsyncSession) -> None:
    if os.getenv("ENVIRONMENT", "development").lower() != "production":
        return
    result = await db.scalar(
        text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
    )
    if result is not True:
        raise RuntimeError(
            "Production integration worker role must be a dedicated BYPASSRLS role; "
            "the API database role must not be reused."
        )


async def run_cycle(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with factory() as db:
        await _assert_worker_role(db)
        fanout = await fanout_outbox_batch(
            db, batch_size=int(os.getenv("OUTBOX_FANOUT_BATCH", "50"))
        )
    async with factory() as db:
        released = await release_capability_blocked(
            db, batch_size=int(os.getenv("DELIVERY_RELEASE_BATCH", "100"))
        )
    async with factory() as db:
        delivery_claims = await claim_delivery_batch(
            db, batch_size=int(os.getenv("DELIVERY_CLAIM_BATCH", "25"))
        )
    async with factory() as db:
        inbound_claims = await claim_inbound_batch(
            db, batch_size=int(os.getenv("INBOUND_CLAIM_BATCH", "25"))
        )

    semaphore = asyncio.Semaphore(int(os.getenv("DELIVERY_CONCURRENCY", "8")))
    resolver = SecretResolver()

    async def deliver(delivery_id, token) -> None:
        async with semaphore:
            async with factory() as db:
                result = await process_delivery(
                    db,
                    delivery_id=delivery_id,
                    lease_token=token,
                    secret_resolver=resolver,
                )
                _log("delivery_processed", delivery_id=delivery_id, result=result)

    async def ingest(inbound_id, token) -> None:
        async with semaphore:
            async with factory() as db:
                result = await process_inbound(
                    db,
                    inbound_id=inbound_id,
                    lease_token=token,
                )
                _log("inbound_processed", inbound_id=inbound_id, result=result)

    await asyncio.gather(
        *(deliver(delivery_id, token) for delivery_id, token in delivery_claims),
        *(ingest(inbound_id, token) for inbound_id, token in inbound_claims),
    )
    return {
        "outbox_fanout": fanout,
        "blocked_released": released,
        "deliveries_claimed": len(delivery_claims),
        "inbound_claimed": len(inbound_claims),
    }


async def worker_loop(*, once: bool) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    async with _session_factory() as factory:
        while not stop.is_set():
            try:
                summary = await run_cycle(factory)
                _log("worker_cycle_completed", **summary)
            except Exception as exc:
                _log("worker_cycle_failed", error_type=type(exc).__name__, detail=str(exc)[:1000])
                if os.getenv("ENVIRONMENT", "development").lower() == "production" and isinstance(
                    exc, RuntimeError
                ):
                    raise
            if once:
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable freight integration worker")
    parser.add_argument("--once", action="store_true", help="Process one cycle and exit")
    args = parser.parse_args()
    _configure_logging()
    asyncio.run(worker_loop(once=args.once))


if __name__ == "__main__":
    main()
