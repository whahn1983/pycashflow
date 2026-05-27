"""add last_manual_balance_entry_at to user

Tracks when PyCashFlow last accepted a manual balance entry (web form or
iOS API) for a user. The Plaid cached /accounts/get auto-sync compares this
against Plaid's cached freshness timestamp so a stale cached balance cannot
overwrite a newer manually-entered value. This is purely a freshness
timestamp; it is not the balance row date and carries no balance provenance.

Revision ID: f8b1c2d3e4a5
Revises: c2d4e8a9b1f3
Create Date: 2026-05-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8b1c2d3e4a5'
down_revision = 'c2d4e8a9b1f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('last_manual_balance_entry_at', sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('last_manual_balance_entry_at')
