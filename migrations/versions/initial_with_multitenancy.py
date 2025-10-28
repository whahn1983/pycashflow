"""Initial migration with multi-tenancy

Revision ID: initial_with_multitenancy
Revises:
Create Date: 2025-10-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'initial_with_multitenancy'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create user table first (other tables reference it)
    op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('password', sa.String(length=100), nullable=True),
        sa.Column('name', sa.String(length=1000), nullable=True),
        sa.Column('admin', sa.Boolean(), nullable=True),
        sa.Column('is_global_admin', sa.Boolean(), nullable=True),
        sa.Column('account_owner_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_user'),
        sa.UniqueConstraint('email', name='uq_user_email'),
        sa.ForeignKeyConstraint(['account_owner_id'], ['user.id'], name='fk_user_account_owner')
    )

    # Create settings table
    op.create_table('settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('value', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_settings'),
        sa.UniqueConstraint('name', name='uq_settings_name')
    )

    # Create schedule table with user_id
    op.create_table('schedule',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('frequency', sa.String(length=100), nullable=True),
        sa.Column('startdate', sa.Date(), nullable=True),
        sa.Column('type', sa.String(length=100), nullable=True),
        sa.Column('firstdate', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_schedule'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_schedule_user'),
        sa.UniqueConstraint('user_id', 'name', name='uq_schedule_user_name')
    )

    # Create balance table with user_id
    op.create_table('balance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('date', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_balance'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_balance_user')
    )

    # Create hold table with user_id
    op.create_table('hold',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('type', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_hold'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_hold_user')
    )

    # Create skip table with user_id
    op.create_table('skip',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('type', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_skip'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_skip_user')
    )

    # Create email table with user_id
    op.create_table('email',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('password', sa.String(length=100), nullable=True),
        sa.Column('server', sa.String(length=100), nullable=True),
        sa.Column('subjectstr', sa.String(length=100), nullable=True),
        sa.Column('startstr', sa.String(length=100), nullable=True),
        sa.Column('endstr', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_email'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_email_user')
    )


def downgrade():
    op.drop_table('email')
    op.drop_table('skip')
    op.drop_table('hold')
    op.drop_table('balance')
    op.drop_table('schedule')
    op.drop_table('settings')
    op.drop_table('user')
