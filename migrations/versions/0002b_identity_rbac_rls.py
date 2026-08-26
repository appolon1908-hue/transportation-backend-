"""tenant policies for identity membership and RBAC tables

Revision ID: 0002b_identity_rbac_rls
Revises: 0002_identity_tenancy
Create Date: 2026-08-26
"""

from alembic import op

revision = "0002b_identity_rbac_rls"
down_revision = "0002_identity_tenancy"
branch_labels = None
depends_on = None

_DIRECT_TENANT_TABLES = (
    "platform_organizations",
    "platform_roles",
    "platform_memberships",
)


def _tenant_expression(column: str = "tenant_id") -> str:
    return (
        f"{column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    )


def upgrade() -> None:
    for table in _DIRECT_TENANT_TABLES:
        policy = f"tenant_isolation_{table}"
        expression = _tenant_expression()
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{policy}" ON "{table}"
                USING ({expression})
                WITH CHECK ({expression})'''
        )

    role_expression = (
        "EXISTS (SELECT 1 FROM platform_roles role_scope "
        "WHERE role_scope.id = role_id "
        "AND role_scope.tenant_id = "
        "NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute('ALTER TABLE "platform_role_permissions" ENABLE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "tenant_isolation_platform_role_permissions"
            ON "platform_role_permissions"
            USING ({role_expression})
            WITH CHECK ({role_expression})'''
    )

    membership_expression = (
        "EXISTS (SELECT 1 FROM platform_memberships membership_scope "
        "WHERE membership_scope.id = membership_id "
        "AND membership_scope.tenant_id = "
        "NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute('ALTER TABLE "platform_membership_roles" ENABLE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "tenant_isolation_platform_membership_roles"
            ON "platform_membership_roles"
            USING ({membership_expression})
            WITH CHECK ({membership_expression})'''
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS "tenant_isolation_platform_membership_roles" '
        'ON "platform_membership_roles"'
    )
    op.execute('ALTER TABLE "platform_membership_roles" DISABLE ROW LEVEL SECURITY')
    op.execute(
        'DROP POLICY IF EXISTS "tenant_isolation_platform_role_permissions" '
        'ON "platform_role_permissions"'
    )
    op.execute('ALTER TABLE "platform_role_permissions" DISABLE ROW LEVEL SECURITY')

    for table in reversed(_DIRECT_TENANT_TABLES):
        policy = f"tenant_isolation_{table}"
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
