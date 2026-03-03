"""add scenario table

Revision ID: a1b2c3d4e5f6
Revises: 67d8fbce85bb
Create Date: 2026-03-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '67d8fbce85bb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('scenario',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('frequency', sa.String(length=100), nullable=True),
    sa.Column('startdate', sa.Date(), nullable=True),
    sa.Column('type', sa.String(length=100), nullable=True),
    sa.Column('firstdate', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', name='_user_scenario_uc')
    )


def downgrade():
    op.drop_table('scenario')
