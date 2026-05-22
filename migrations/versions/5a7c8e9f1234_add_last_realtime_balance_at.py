"""add plaid realtime balance refresh fields

Adds the columns needed to support the manual /accounts/balance/get refresh:

- last_realtime_balance_at: cooldown timestamp claimed before the Plaid call
  so a failed-but-billed call still consumes the 24-hour window and rapid
  double-clicks cannot trigger duplicate paid calls.
- last_realtime_refresh_status / last_realtime_refresh_error: dedicated
  status/error columns so a real-time refresh failure does not overwrite
  the unrelated status of the automatic /accounts/get sync.

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
        batch_op.add_column(
            sa.Column('last_realtime_refresh_status', sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column('last_realtime_refresh_error', sa.String(length=255), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('plaid_connections', schema=None) as batch_op:
        batch_op.drop_column('last_realtime_refresh_error')
        batch_op.drop_column('last_realtime_refresh_status')
        batch_op.drop_column('last_realtime_balance_at')
