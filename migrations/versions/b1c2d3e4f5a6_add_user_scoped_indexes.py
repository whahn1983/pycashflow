"""add user-scoped indexes for hot query paths

Revision ID: b1c2d3e4f5a6
Revises: a8c9d0e1f2a3
Create Date: 2026-04-18 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(op.f('ix_balance_user_id'), 'balance', ['user_id'], unique=False)
    op.create_index('ix_balance_user_id_date_id', 'balance', ['user_id', 'date', 'id'], unique=False)
    op.create_index(op.f('ix_hold_user_id'), 'hold', ['user_id'], unique=False)
    op.create_index(op.f('ix_skip_user_id'), 'skip', ['user_id'], unique=False)
    op.create_index(op.f('ix_email_user_id'), 'email', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_email_user_id'), table_name='email')
    op.drop_index(op.f('ix_skip_user_id'), table_name='skip')
    op.drop_index(op.f('ix_hold_user_id'), table_name='hold')
    op.drop_index('ix_balance_user_id_date_id', table_name='balance')
    op.drop_index(op.f('ix_balance_user_id'), table_name='balance')
