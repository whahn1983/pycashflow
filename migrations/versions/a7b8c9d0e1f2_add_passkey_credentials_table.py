"""add passkey credentials table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'passkey_credential',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('credential_id', sa.String(length=512), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transports', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('label', sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_passkey_credential_credential_id'), 'passkey_credential', ['credential_id'], unique=True)
    op.create_index(op.f('ix_passkey_credential_user_id'), 'passkey_credential', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_passkey_credential_user_id'), table_name='passkey_credential')
    op.drop_index(op.f('ix_passkey_credential_credential_id'), table_name='passkey_credential')
    op.drop_table('passkey_credential')
