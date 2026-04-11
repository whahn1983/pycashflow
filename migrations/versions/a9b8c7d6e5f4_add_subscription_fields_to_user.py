"""add subscription fields to user

Revision ID: a9b8c7d6e5f4
Revises: f6a7b8c9d0e1
Create Date: 2026-04-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9b8c7d6e5f4'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        'user',
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    ) as batch_op:
        batch_op.add_column(sa.Column('is_account_owner', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('subscription_status', sa.String(length=20), nullable=False, server_default='inactive'))
        batch_op.add_column(sa.Column('subscription_source', sa.String(length=20), nullable=False, server_default='none'))
        batch_op.add_column(sa.Column('subscription_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('subscription_expiry', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_user_owner_user_id_user', 'user', ['owner_user_id'], ['id'])


def downgrade():
    with op.batch_alter_table(
        'user',
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    ) as batch_op:
        batch_op.drop_constraint('fk_user_owner_user_id_user', type_='foreignkey')
        batch_op.drop_column('subscription_expiry')
        batch_op.drop_column('subscription_id')
        batch_op.drop_column('subscription_source')
        batch_op.drop_column('subscription_status')
        batch_op.drop_column('owner_user_id')
        batch_op.drop_column('is_account_owner')
