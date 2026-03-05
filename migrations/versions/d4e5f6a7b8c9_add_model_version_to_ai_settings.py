"""add model_version to ai_settings

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ai_settings',
        sa.Column('model_version', sa.String(length=100), nullable=True)
    )


def downgrade():
    op.drop_column('ai_settings', 'model_version')
