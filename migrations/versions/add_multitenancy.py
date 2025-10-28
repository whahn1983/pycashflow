"""Add multi-tenancy support

Revision ID: add_multitenancy
Revises: 7b4195cb191c
Create Date: 2025-10-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'add_multitenancy'
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
            # No users exist - use placeholder (will fail if data exists in other tables)
            first_admin_id = 1

    # Add new columns to User table (without foreign key to avoid circular dependency)
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_global_admin', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('account_owner_id', sa.Integer(), nullable=True))

    # Set first admin as global admin
    conn.execute(text(f"UPDATE user SET is_global_admin = 1 WHERE id = {first_admin_id}"))
    # Set default for is_global_admin to False for all other users
    conn.execute(text(f"UPDATE user SET is_global_admin = 0 WHERE id != {first_admin_id}"))

    # Now add the self-referencing foreign key in a separate batch operation
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_user_account_owner', 'user', ['account_owner_id'], ['id'])

    # Update Schedule table - add user_id and change unique constraint
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('schedule_name_key', type_='unique')

    # Assign existing schedule data to first admin
    conn.execute(text(f"UPDATE schedule SET user_id = {first_admin_id}"))

    # Now recreate schedule table with NOT NULL constraint and new unique constraint
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_schedule_user', 'user', ['user_id'], ['id'])
        batch_op.create_unique_constraint('_user_schedule_uc', ['user_id', 'name'])

    # Update Balance table
    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    conn.execute(text(f"UPDATE balance SET user_id = {first_admin_id}"))

    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_balance_user', 'user', ['user_id'], ['id'])

    # Update Hold table
    with op.batch_alter_table('hold', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    conn.execute(text(f"UPDATE hold SET user_id = {first_admin_id}"))

    with op.batch_alter_table('hold', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_hold_user', 'user', ['user_id'], ['id'])

    # Update Skip table
    with op.batch_alter_table('skip', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    conn.execute(text(f"UPDATE skip SET user_id = {first_admin_id}"))

    with op.batch_alter_table('skip', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_skip_user', 'user', ['user_id'], ['id'])

    # Update Email table
    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('email_email_key', type_='unique')

    conn.execute(text(f"UPDATE email SET user_id = {first_admin_id}"))

    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_email_user', 'user', ['user_id'], ['id'])


def downgrade():
    # Remove composite unique constraint and restore schedule table
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_constraint('_user_schedule_uc', type_='unique')
        batch_op.drop_constraint('fk_schedule_user', type_='foreignkey')
        batch_op.drop_column('user_id')
        batch_op.create_unique_constraint('schedule_name_key', ['name'])

    # Restore email table
    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.drop_constraint('fk_email_user', type_='foreignkey')
        batch_op.drop_column('user_id')
        batch_op.create_unique_constraint('email_email_key', ['email'])

    # Restore skip table
    with op.batch_alter_table('skip', schema=None) as batch_op:
        batch_op.drop_constraint('fk_skip_user', type_='foreignkey')
        batch_op.drop_column('user_id')

    # Restore hold table
    with op.batch_alter_table('hold', schema=None) as batch_op:
        batch_op.drop_constraint('fk_hold_user', type_='foreignkey')
        batch_op.drop_column('user_id')

    # Restore balance table
    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.drop_constraint('fk_balance_user', type_='foreignkey')
        batch_op.drop_column('user_id')

    # Restore user table
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_account_owner', type_='foreignkey')
        batch_op.drop_column('account_owner_id')
        batch_op.drop_column('is_global_admin')
