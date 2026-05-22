"""add last_plaid_realtime_balance_at to user

Persist the Plaid /accounts/balance/get cooldown timestamp on the user so
that deleting and re-adding a Plaid connection does not reset the 24-hour
rate limit. The value is mirrored onto the new PlaidConnection on re-add
and refreshed onto the user when the connection is removed.

Revision ID: 6b8d9f0a2345
Revises: 5a7c8e9f1234
Create Date: 2026-05-22 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6b8d9f0a2345'
down_revision = '5a7c8e9f1234'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('last_plaid_realtime_balance_at', sa.DateTime(), nullable=True)
        )

    # Backfill from any existing PlaidConnection rows so users who already
    # consumed their cooldown window keep it across the upgrade. Uses a
    # correlated subquery for SQLite/PostgreSQL portability.
    bind = op.get_bind()
    user_table = sa.table(
        'user',
        sa.column('id', sa.Integer),
        sa.column('last_plaid_realtime_balance_at', sa.DateTime),
    )
    pc_table = sa.table(
        'plaid_connections',
        sa.column('user_id', sa.Integer),
        sa.column('last_realtime_balance_at', sa.DateTime),
    )
    rows = bind.execute(
        sa.select(
            pc_table.c.user_id,
            sa.func.max(pc_table.c.last_realtime_balance_at).label('ts'),
        )
        .where(pc_table.c.last_realtime_balance_at.isnot(None))
        .group_by(pc_table.c.user_id)
    ).fetchall()
    for user_id, ts in rows:
        bind.execute(
            sa.update(user_table)
            .where(user_table.c.id == user_id)
            .where(user_table.c.last_plaid_realtime_balance_at.is_(None))
            .values(last_plaid_realtime_balance_at=ts)
        )


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('last_plaid_realtime_balance_at')
