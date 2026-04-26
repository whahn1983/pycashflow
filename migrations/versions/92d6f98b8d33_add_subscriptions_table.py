"""add subscriptions table

Revision ID: 92d6f98b8d33
Revises: b3c4d5e6f7a8
Create Date: 2026-04-25 23:58:09.112622

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '92d6f98b8d33'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('subscription',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('environment', sa.String(length=20), nullable=True),
    sa.Column('product_id', sa.String(length=255), nullable=True),
    sa.Column('original_transaction_id', sa.String(length=255), nullable=True),
    sa.Column('latest_transaction_id', sa.String(length=255), nullable=True),
    sa.Column('external_subscription_id', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='inactive', nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('raw_last_verified_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_subscription_user_id_user'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'environment', 'original_transaction_id', name='uq_subscription_apple_original'),
    sa.UniqueConstraint('source', 'external_subscription_id', name='uq_subscription_external_source_id')
    )
    with op.batch_alter_table('subscription', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscription_user_id'), ['user_id'], unique=False)

    _migrate_legacy_user_subscription_fields()


def downgrade():
    with op.batch_alter_table('subscription', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscription_user_id'))

    op.drop_table('subscription')


def _migrate_legacy_user_subscription_fields():
    bind = op.get_bind()
    user_table = sa.table(
        'user',
        sa.column('id', sa.Integer()),
        sa.column('subscription_status', sa.String()),
        sa.column('subscription_source', sa.String()),
        sa.column('subscription_id', sa.String()),
        sa.column('subscription_expiry', sa.DateTime()),
    )
    subscription_table = sa.table(
        'subscription',
        sa.column('user_id', sa.Integer()),
        sa.column('source', sa.String()),
        sa.column('environment', sa.String()),
        sa.column('product_id', sa.String()),
        sa.column('original_transaction_id', sa.String()),
        sa.column('latest_transaction_id', sa.String()),
        sa.column('external_subscription_id', sa.String()),
        sa.column('status', sa.String()),
        sa.column('expires_at', sa.DateTime()),
        sa.column('raw_last_verified_at', sa.DateTime()),
        sa.column('created_at', sa.DateTime()),
        sa.column('updated_at', sa.DateTime()),
    )

    now = datetime.utcnow()
    rows = bind.execute(
        sa.select(
            user_table.c.id,
            user_table.c.subscription_status,
            user_table.c.subscription_source,
            user_table.c.subscription_id,
            user_table.c.subscription_expiry,
        )
    ).fetchall()

    seen_apple = set()
    seen_stripe = set()
    inserts = []
    for row in rows:
        source = (row.subscription_source or '').strip().lower()
        if source in {'', 'none'}:
            continue

        status = (row.subscription_status or 'inactive').strip().lower() or 'inactive'
        subscription_id = (row.subscription_id or '').strip() or None
        if source in {'app_store', 'apple'}:
            source = 'apple'
            # Legacy App Store subscriptions had no explicit environment on
            # `user`. Backfill to sandbox so existing ownership records
            # continue to participate in (source, environment,
            # original_transaction_id) locking.
            environment = 'sandbox'
            original_transaction_id = subscription_id
            latest_transaction_id = subscription_id
            external_subscription_id = None
            apple_key = (source, environment, original_transaction_id)
            if original_transaction_id and apple_key in seen_apple:
                continue
            if original_transaction_id:
                seen_apple.add(apple_key)
        elif source == 'stripe':
            environment = None
            original_transaction_id = None
            latest_transaction_id = None
            external_subscription_id = subscription_id
            stripe_key = (source, external_subscription_id)
            if external_subscription_id and stripe_key in seen_stripe:
                continue
            if external_subscription_id:
                seen_stripe.add(stripe_key)
        else:
            environment = None
            original_transaction_id = None
            latest_transaction_id = None
            external_subscription_id = subscription_id

        inserts.append(
            {
                'user_id': row.id,
                'source': source,
                'environment': environment,
                'product_id': None,
                'original_transaction_id': original_transaction_id,
                'latest_transaction_id': latest_transaction_id,
                'external_subscription_id': external_subscription_id,
                'status': status,
                'expires_at': row.subscription_expiry,
                'raw_last_verified_at': now,
                'created_at': now,
                'updated_at': now,
            }
        )

    if inserts:
        bind.execute(subscription_table.insert(), inserts)
