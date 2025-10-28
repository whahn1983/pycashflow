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

    # Add new columns to User table
    op.add_column('user', sa.Column('is_global_admin', sa.Boolean(), nullable=True))
    op.add_column('user', sa.Column('account_owner_id', sa.Integer(), nullable=True))

    # Set first admin as global admin
    conn.execute(text(f"UPDATE user SET is_global_admin = 1 WHERE id = {first_admin_id}"))

    # Set default for is_global_admin to False for all other users
    conn.execute(text(f"UPDATE user SET is_global_admin = 0 WHERE id != {first_admin_id}"))

    # Add foreign key for account_owner_id (self-referencing)
    op.create_foreign_key('fk_user_account_owner', 'user', 'user', ['account_owner_id'], ['id'])

    # Add user_id columns to data tables (nullable first for migration)
    op.add_column('schedule', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('balance', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('hold', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('skip', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('email', sa.Column('user_id', sa.Integer(), nullable=True))

    # Assign all existing data to first admin
    conn.execute(text(f"UPDATE schedule SET user_id = {first_admin_id}"))
    conn.execute(text(f"UPDATE balance SET user_id = {first_admin_id}"))
    conn.execute(text(f"UPDATE hold SET user_id = {first_admin_id}"))
    conn.execute(text(f"UPDATE skip SET user_id = {first_admin_id}"))
    conn.execute(text(f"UPDATE email SET user_id = {first_admin_id}"))

    # Now make user_id NOT NULL and add foreign keys
    op.alter_column('schedule', 'user_id', nullable=False)
    op.alter_column('balance', 'user_id', nullable=False)
    op.alter_column('hold', 'user_id', nullable=False)
    op.alter_column('skip', 'user_id', nullable=False)
    op.alter_column('email', 'user_id', nullable=False)

    # Add foreign key constraints
    op.create_foreign_key('fk_schedule_user', 'schedule', 'user', ['user_id'], ['id'])
    op.create_foreign_key('fk_balance_user', 'balance', 'user', ['user_id'], ['id'])
    op.create_foreign_key('fk_hold_user', 'hold', 'user', ['user_id'], ['id'])
    op.create_foreign_key('fk_skip_user', 'skip', 'user', ['user_id'], ['id'])
    op.create_foreign_key('fk_email_user', 'email', 'user', ['user_id'], ['id'])

    # Drop old unique constraints
    op.drop_constraint('schedule_name_key', 'schedule', type_='unique')
    op.drop_constraint('email_email_key', 'email', type_='unique')

    # Add composite unique constraint for schedule (user_id, name)
    op.create_unique_constraint('_user_schedule_uc', 'schedule', ['user_id', 'name'])


def downgrade():
    # Remove composite unique constraint
    op.drop_constraint('_user_schedule_uc', 'schedule', type_='unique')

    # Restore old unique constraints
    op.create_unique_constraint('schedule_name_key', 'schedule', ['name'])
    op.create_unique_constraint('email_email_key', 'email', ['email'])

    # Drop foreign keys
    op.drop_constraint('fk_email_user', 'email', type_='foreignkey')
    op.drop_constraint('fk_skip_user', 'skip', type_='foreignkey')
    op.drop_constraint('fk_hold_user', 'hold', type_='foreignkey')
    op.drop_constraint('fk_balance_user', 'balance', type_='foreignkey')
    op.drop_constraint('fk_schedule_user', 'schedule', type_='foreignkey')

    # Remove user_id columns
    op.drop_column('email', 'user_id')
    op.drop_column('skip', 'user_id')
    op.drop_column('hold', 'user_id')
    op.drop_column('balance', 'user_id')
    op.drop_column('schedule', 'user_id')

    # Drop account owner foreign key
    op.drop_constraint('fk_user_account_owner', 'user', type_='foreignkey')

    # Remove new columns from User table
    op.drop_column('user', 'account_owner_id')
    op.drop_column('user', 'is_global_admin')
