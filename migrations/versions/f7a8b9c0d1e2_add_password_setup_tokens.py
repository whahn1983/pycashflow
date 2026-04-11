"""add password setup tokens table

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'password_setup_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_password_setup_tokens_token_hash'),
        'password_setup_tokens',
        ['token_hash'],
        unique=True,
    )
    op.create_index(
        op.f('ix_password_setup_tokens_user_id'),
        'password_setup_tokens',
        ['user_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f('ix_password_setup_tokens_user_id'), table_name='password_setup_tokens')
    op.drop_index(op.f('ix_password_setup_tokens_token_hash'), table_name='password_setup_tokens')
    op.drop_table('password_setup_tokens')
