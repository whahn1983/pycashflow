"""add last_realtime_balance_at to plaid_connections

Revision ID: 5a7c8e9f1234
Revises: 4553e3440cb6
Create Date: 2026-05-22 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5a7c8e9f1234'
down_revision = '4553e3440cb6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('plaid_connections', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('last_realtime_balance_at', sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('plaid_connections', schema=None) as batch_op:
        batch_op.drop_column('last_realtime_balance_at')
