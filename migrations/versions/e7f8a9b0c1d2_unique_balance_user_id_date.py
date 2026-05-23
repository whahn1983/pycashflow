"""add unique constraint on balance (user_id, date)

Deduplicates same-day balance rows per user, keeping the row with the
highest ``id`` (most recently inserted), then enforces uniqueness at the
database level so application-level upserts cannot race and reintroduce
duplicates.

Revision ID: e7f8a9b0c1d2
Revises: 6b8d9f0a2345
Create Date: 2026-05-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = '6b8d9f0a2345'
branch_labels = None
depends_on = None


def upgrade():
    # Remove duplicate (user_id, date) rows before adding the unique
    # constraint. For each (user_id, date), keep the row with the largest
    # id (most recently inserted). NULL dates are ignored because NULL is
    # not considered equal in unique-constraint comparisons on either
    # SQLite or PostgreSQL.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT b1.id FROM balance b1 "
            "WHERE b1.date IS NOT NULL "
            "AND EXISTS ("
            "  SELECT 1 FROM balance b2 "
            "  WHERE b2.user_id = b1.user_id "
            "    AND b2.date = b1.date "
            "    AND b2.id > b1.id"
            ")"
        )
    ).fetchall()
    duplicate_ids = [row[0] for row in rows]
    if duplicate_ids:
        bind.execute(
            sa.text("DELETE FROM balance WHERE id IN :ids").bindparams(
                sa.bindparam('ids', duplicate_ids, expanding=True)
            )
        )

    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_balance_user_id_date', ['user_id', 'date']
        )


def downgrade():
    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.drop_constraint('uq_balance_user_id_date', type_='unique')
