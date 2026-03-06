"""add 2fa fields to user table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user',
        sa.Column('twofa_enabled', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column('user',
        sa.Column('twofa_secret', sa.String(length=500), nullable=True)
    )
    op.add_column('user',
        sa.Column('twofa_backup_codes', sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column('user', 'twofa_backup_codes')
    op.drop_column('user', 'twofa_secret')
    op.drop_column('user', 'twofa_enabled')
