"""merge alembic heads

Revision ID: 3979d4be8acf
Revises: a2b3c4d5e6f7, a9b8c7d6e5f4, f7a8b9c0d1e2
Create Date: 2026-04-11 23:30:43.030115

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3979d4be8acf'
down_revision = ('a2b3c4d5e6f7', 'a9b8c7d6e5f4', 'f7a8b9c0d1e2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
