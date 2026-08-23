"""initial freight platform foundation

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-23
"""

from alembic import op

from app.db import Base
import app.models  # noqa: F401

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep PostGIS available from day one. SQLAlchemy emits each table/index
    # separately, which is compatible with asyncpg prepared statements.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Remove application tables but deliberately leave the shared PostGIS
    # extension installed because it may be used by other schemas.
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
