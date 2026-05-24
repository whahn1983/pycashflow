"""add balance_email_datetime to email table

Tracks the timestamp of the most recent balance email a user's Email
configuration produced. The Plaid cached /accounts/get auto-sync compares
this against Plaid's cached freshness timestamp so a stale cached balance
cannot overwrite a newer email-derived value.

Revision ID: c2d4e8a9b1f3
Revises: e7f8a9b0c1d2
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2d4e8a9b1f3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('email') as batch_op:
        batch_op.add_column(
            sa.Column('balance_email_datetime', sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('email') as batch_op:
        batch_op.drop_column('balance_email_datetime')
