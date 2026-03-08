"""add allowed_sender to email table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('email') as batch_op:
        batch_op.add_column(
            sa.Column('allowed_sender', sa.String(length=200), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('email') as batch_op:
        batch_op.drop_column('allowed_sender')
