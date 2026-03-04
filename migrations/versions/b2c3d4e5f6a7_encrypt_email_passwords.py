"""encrypt email passwords

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Create global_email_settings table (was missing from prior migrations)
    op.create_table('global_email_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=100), nullable=False),
    sa.Column('password', sa.String(length=500), nullable=False),
    sa.Column('smtp_server', sa.String(length=100), nullable=False),
    sa.CheckConstraint('id = 1', name='single_row_check'),
    sa.PrimaryKeyConstraint('id')
    )

    # Increase email.password column size to accommodate Fernet-encrypted tokens
    with op.batch_alter_table('email') as batch_op:
        batch_op.alter_column('password',
            existing_type=sa.String(length=100),
            type_=sa.String(length=500),
            existing_nullable=True)


def downgrade():
    with op.batch_alter_table('email') as batch_op:
        batch_op.alter_column('password',
            existing_type=sa.String(length=500),
            type_=sa.String(length=100),
            existing_nullable=True)

    op.drop_table('global_email_settings')
