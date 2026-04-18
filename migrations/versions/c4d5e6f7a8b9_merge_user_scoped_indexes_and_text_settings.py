"""merge user-scoped indexes and text settings heads

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6, a8c9d0e1f2a3
Create Date: 2026-04-18 00:00:00.000000

"""

from alembic import op

import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = ('b1c2d3e4f5a6', 'a8c9d0e1f2a3')
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes_by_table = {
        table_name: {index['name'] for index in inspector.get_indexes(table_name)}
        for table_name in ('balance', 'hold', 'skip', 'email')
        if inspector.has_table(table_name)
    }

    if 'ix_balance_user_id' not in indexes_by_table.get('balance', set()):
        op.create_index(op.f('ix_balance_user_id'), 'balance', ['user_id'], unique=False)

    if 'ix_balance_user_id_date_id' not in indexes_by_table.get('balance', set()):
        op.create_index(
            'ix_balance_user_id_date_id', 'balance', ['user_id', 'date', 'id'], unique=False
        )

    if 'ix_hold_user_id' not in indexes_by_table.get('hold', set()):
        op.create_index(op.f('ix_hold_user_id'), 'hold', ['user_id'], unique=False)

    if 'ix_skip_user_id' not in indexes_by_table.get('skip', set()):
        op.create_index(op.f('ix_skip_user_id'), 'skip', ['user_id'], unique=False)

    if 'ix_email_user_id' not in indexes_by_table.get('email', set()):
        op.create_index(op.f('ix_email_user_id'), 'email', ['user_id'], unique=False)


def downgrade():
    pass
