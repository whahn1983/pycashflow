"""Add multi-tenancy support - simple approach

Revision ID: add_multitenancy_simple
Revises: 7b4195cb191c
Create Date: 2025-10-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'add_multitenancy_simple'
down_revision = '7b4195cb191c'
branch_labels = None
depends_on = None


def upgrade():
    # Get database connection
    conn = op.get_bind()

    # Find first admin user to assign existing data
    result = conn.execute(text("SELECT id FROM user WHERE admin = 1 ORDER BY id LIMIT 1"))
    first_admin_row = result.fetchone()

    if first_admin_row:
        first_admin_id = first_admin_row[0]
    else:
        # If no admin exists, use the first user
        result = conn.execute(text("SELECT id FROM user ORDER BY id LIMIT 1"))
        first_user_row = result.fetchone()
        if first_user_row:
            first_admin_id = first_user_row[0]
        else:
            first_admin_id = 1

    # 1. Update User table - add new columns
    op.add_column('user', sa.Column('is_global_admin', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('user', sa.Column('account_owner_id', sa.Integer(), nullable=True))

    # Set first admin as global admin
    conn.execute(text(f"UPDATE user SET is_global_admin = 1 WHERE id = {first_admin_id}"))
    conn.execute(text(f"UPDATE user SET is_global_admin = 0 WHERE is_global_admin IS NULL"))

    # 2. Update Schedule table
    op.add_column('schedule', sa.Column('user_id', sa.Integer(), nullable=True))
    conn.execute(text(f"UPDATE schedule SET user_id = {first_admin_id}"))

    # 3. Update Balance table
    op.add_column('balance', sa.Column('user_id', sa.Integer(), nullable=True))
    conn.execute(text(f"UPDATE balance SET user_id = {first_admin_id}"))

    # 4. Update Hold table
    op.add_column('hold', sa.Column('user_id', sa.Integer(), nullable=True))
    conn.execute(text(f"UPDATE hold SET user_id = {first_admin_id}"))

    # 5. Update Skip table
    op.add_column('skip', sa.Column('user_id', sa.Integer(), nullable=True))
    conn.execute(text(f"UPDATE skip SET user_id = {first_admin_id}"))

    # 6. Update Email table
    op.add_column('email', sa.Column('user_id', sa.Integer(), nullable=True))
    conn.execute(text(f"UPDATE email SET user_id = {first_admin_id}"))

    # Now use batch operations to update constraints (SQLite compatible)
    # Note: We're NOT making columns NOT NULL or adding foreign keys
    # SQLite will handle this at the model level via SQLAlchemy

    # For schedule: change unique constraint from name to (user_id, name)
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_constraint('schedule_name_key', type_='unique')
        batch_op.create_index('ix_schedule_user_name', ['user_id', 'name'], unique=True)

    # For email: drop unique constraint on email (users can share email configs)
    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.drop_constraint('email_email_key', type_='unique')


def downgrade():
    # Remove indexes
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_index('ix_schedule_user_name')
        batch_op.create_unique_constraint('schedule_name_key', ['name'])

    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.create_unique_constraint('email_email_key', ['email'])

    # Remove columns
    op.drop_column('email', 'user_id')
    op.drop_column('skip', 'user_id')
    op.drop_column('hold', 'user_id')
    op.drop_column('balance', 'user_id')
    op.drop_column('schedule', 'user_id')
    op.drop_column('user', 'account_owner_id')
    op.drop_column('user', 'is_global_admin')
