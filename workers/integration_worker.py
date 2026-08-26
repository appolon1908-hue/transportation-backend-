from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from collections.abc import Awaitable, Callable

from app.db import SessionLocal
from app.integrations.service import (
    claim_delivery_batch,
    claim_inbox_batch,
    fanout_outbox_batch,
    process_claimed_delivery,
    process_claimed_inbox,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("freight.integration-worker")
_shutdown = asyncio.Event()


def _signal_shutdown() -> None:
    _shutdown.set()


async def run_fanout() -> int:
    async with SessionLocal() as db:
        count = await fanout_outbox_batch(
            db, limit=int(os.getenv("INTEGRATION_FANOUT_BATCH_SIZE", "100"))
        )
    logger.info("integration_fanout_complete count=%s", count)
    return count


async def run_delivery() -> int:
    async with SessionLocal() as db:
        claims = await claim_delivery_batch(
            db, limit=int(os.getenv("INTEGRATION_DELIVERY_BATCH_SIZE", "25"))
        )
    processed = 0
    for claim in claims:
        async with SessionLocal() as db:
            outcome = await process_claimed_delivery(
                db, delivery_id=claim.delivery_id, claim_token=claim.claim_token
            )
        logger.info(
            "integration_delivery_complete delivery_id=%s outcome=%s",
            claim.delivery_id,
            outcome,
        )
        processed += 1
    return processed


async def run_inbox() -> int:
    async with SessionLocal() as db:
        claims = await claim_inbox_batch(
            db, limit=int(os.getenv("INTEGRATION_INBOX_BATCH_SIZE", "50"))
        )
    processed = 0
    for claim in claims:
        async with SessionLocal() as db:
            outcome = await process_claimed_inbox(
                db, inbox_id=claim.inbox_id, claim_token=claim.claim_token
            )
        logger.info(
            "integration_inbox_complete inbox_id=%s outcome=%s",
            claim.inbox_id,
            outcome,
        )
        processed += 1
    return processed


async def run_cycle(mode: str) -> int:
    total = 0
    if mode in {"all", "fanout"}:
        total += await run_fanout()
    if mode in {"all", "inbox"}:
        total += await run_inbox()
    if mode in {"all", "delivery"}:
        total += await run_delivery()
    return total


async def main_async(mode: str, once: bool) -> None:
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signal_name, _signal_shutdown)
        except NotImplementedError:
            pass

    poll_seconds = max(float(os.getenv("INTEGRATION_WORKER_POLL_SECONDS", "2")), 0.2)
    while not _shutdown.is_set():
        try:
            processed = await run_cycle(mode)
        except Exception:
            logger.exception("integration_worker_cycle_failed mode=%s", mode)
            processed = 0
        if once:
            return
        if processed == 0:
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freight durable integration worker")
    parser.add_argument(
        "--mode",
        choices=["all", "fanout", "delivery", "inbox"],
        default="all",
        help="Worker stage to execute.",
    )
    parser.add_argument("--once", action="store_true", help="Run one bounded cycle and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args.mode, args.once))


if __name__ == "__main__":
    main()
