from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1_800,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@event.listens_for(Session, "after_begin")
def _restore_request_context(session: Session, _transaction: object, connection: object) -> None:
    """Reapply transaction-local tenant context after a commit starts a new transaction."""

    tenant_id = session.info.get("tenant_id")
    actor_id = session.info.get("actor_id")
    if tenant_id:
        connection.execute(  # type: ignore[attr-defined]
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
    if actor_id:
        connection.execute(  # type: ignore[attr-defined]
            text("SELECT set_config('app.actor_id', :actor_id, true)"),
            {"actor_id": str(actor_id)},
        )


async def set_session_context(session: AsyncSession, tenant_id: UUID, actor_id: str) -> None:
    """Set the authoritative tenant/actor context used by PostgreSQL policies."""

    session.info["tenant_id"] = tenant_id
    session.info["actor_id"] = actor_id
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    await session.execute(
        text("SELECT set_config('app.actor_id', :actor_id, true)"),
        {"actor_id": actor_id},
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()
