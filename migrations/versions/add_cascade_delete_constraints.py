"""add cascade delete to foreign key constraints

Revision ID: add_cascade_delete
Revises: 67d8fbce85bb
Create Date: 2025-12-27 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_cascade_delete'
down_revision = '67d8fbce85bb'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support ALTER TABLE for foreign keys, so we need to recreate tables
    # We'll use batch operations which handle the table recreation for us

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_user_account_owner', 'user', ['account_owner_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_balance_user', 'user', ['user_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_email_user', 'user', ['user_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('hold', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_hold_user', 'user', ['user_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_schedule_user', 'user', ['user_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('skip', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_skip_user', 'user', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade():
    # Revert to foreign keys without cascade delete

    with op.batch_alter_table('skip', schema=None) as batch_op:
        batch_op.drop_constraint('fk_skip_user', type_='foreignkey')
        batch_op.create_foreign_key(None, 'user', ['user_id'], ['id'])

    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_constraint('fk_schedule_user', type_='foreignkey')
        batch_op.create_foreign_key(None, 'user', ['user_id'], ['id'])

    with op.batch_alter_table('hold', schema=None) as batch_op:
        batch_op.drop_constraint('fk_hold_user', type_='foreignkey')
        batch_op.create_foreign_key(None, 'user', ['user_id'], ['id'])

    with op.batch_alter_table('email', schema=None) as batch_op:
        batch_op.drop_constraint('fk_email_user', type_='foreignkey')
        batch_op.create_foreign_key(None, 'user', ['user_id'], ['id'])

    with op.batch_alter_table('balance', schema=None) as batch_op:
        batch_op.drop_constraint('fk_balance_user', type_='foreignkey')
        batch_op.create_foreign_key(None, 'user', ['user_id'], ['id'])

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_account_owner', type_='foreignkey')
        batch_op.create_foreign_key(None, 'user', ['account_owner_id'], ['id'])
