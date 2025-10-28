"""Add multi-tenancy support v2

Revision ID: add_multitenancy_v2
Revises: 7b4195cb191c
Create Date: 2025-10-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'add_multitenancy_v2'
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
            # No users exist - use placeholder
            first_admin_id = 1

    # For SQLite, we need to recreate tables with proper schema
    # Check if we're using SQLite
    dialect_name = conn.dialect.name

    if dialect_name == 'sqlite':
        # SQLite: Use direct table recreation approach
        # First, clean up any leftover temporary tables from failed migrations
        temp_tables = ['user_new', 'schedule_new', 'balance_new', 'hold_new', 'skip_new', 'email_new']
        for temp_table in temp_tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))

        # 1. USER TABLE
        conn.execute(text("""
            CREATE TABLE user_new (
                id INTEGER PRIMARY KEY,
                email VARCHAR(100) UNIQUE,
                password VARCHAR(100),
                name VARCHAR(1000),
                admin BOOLEAN,
                is_global_admin BOOLEAN,
                account_owner_id INTEGER,
                FOREIGN KEY(account_owner_id) REFERENCES user_new (id)
            )
        """))

        conn.execute(text("""
            INSERT INTO user_new (id, email, password, name, admin, is_global_admin, account_owner_id)
            SELECT id, email, password, name, admin, 0, NULL FROM user
        """))

        conn.execute(text(f"UPDATE user_new SET is_global_admin = 1 WHERE id = {first_admin_id}"))

        conn.execute(text("DROP TABLE user"))
        conn.execute(text("ALTER TABLE user_new RENAME TO user"))

        # 2. SCHEDULE TABLE
        conn.execute(text("""
            CREATE TABLE schedule_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                amount NUMERIC(10, 2),
                frequency VARCHAR(100),
                startdate DATE,
                type VARCHAR(100),
                firstdate DATE,
                FOREIGN KEY(user_id) REFERENCES user (id),
                UNIQUE(user_id, name)
            )
        """))

        conn.execute(text(f"""
            INSERT INTO schedule_new (id, user_id, name, amount, frequency, startdate, type, firstdate)
            SELECT id, {first_admin_id}, name, amount, frequency, startdate, type, firstdate FROM schedule
        """))

        conn.execute(text("DROP TABLE schedule"))
        conn.execute(text("ALTER TABLE schedule_new RENAME TO schedule"))

        # 3. BALANCE TABLE
        conn.execute(text("""
            CREATE TABLE balance_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount NUMERIC(10, 2),
                date DATE,
                FOREIGN KEY(user_id) REFERENCES user (id)
            )
        """))

        conn.execute(text(f"""
            INSERT INTO balance_new (id, user_id, amount, date)
            SELECT id, {first_admin_id}, amount, date FROM balance
        """))

        conn.execute(text("DROP TABLE balance"))
        conn.execute(text("ALTER TABLE balance_new RENAME TO balance"))

        # 4. HOLD TABLE
        conn.execute(text("""
            CREATE TABLE hold_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount NUMERIC(10, 2),
                name VARCHAR(100),
                type VARCHAR(100),
                FOREIGN KEY(user_id) REFERENCES user (id)
            )
        """))

        conn.execute(text(f"""
            INSERT INTO hold_new (id, user_id, amount, name, type)
            SELECT id, {first_admin_id}, amount, name, type FROM hold
        """))

        conn.execute(text("DROP TABLE hold"))
        conn.execute(text("ALTER TABLE hold_new RENAME TO hold"))

        # 5. SKIP TABLE
        conn.execute(text("""
            CREATE TABLE skip_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR(100),
                date DATE,
                amount NUMERIC(10, 2),
                type VARCHAR(100),
                FOREIGN KEY(user_id) REFERENCES user (id)
            )
        """))

        conn.execute(text(f"""
            INSERT INTO skip_new (id, user_id, name, date, amount, type)
            SELECT id, {first_admin_id}, name, date, amount, type FROM skip
        """))

        conn.execute(text("DROP TABLE skip"))
        conn.execute(text("ALTER TABLE skip_new RENAME TO skip"))

        # 6. EMAIL TABLE
        conn.execute(text("""
            CREATE TABLE email_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                email VARCHAR(100) NOT NULL,
                password VARCHAR(100),
                server VARCHAR(100),
                subjectstr VARCHAR(100),
                startstr VARCHAR(100),
                endstr VARCHAR(100),
                FOREIGN KEY(user_id) REFERENCES user (id)
            )
        """))

        conn.execute(text(f"""
            INSERT INTO email_new (id, user_id, email, password, server, subjectstr, startstr, endstr)
            SELECT id, {first_admin_id}, email, password, server, subjectstr, startstr, endstr FROM email
        """))

        conn.execute(text("DROP TABLE email"))
        conn.execute(text("ALTER TABLE email_new RENAME TO email"))

    else:
        # PostgreSQL: Use ALTER TABLE statements
        # Add columns
        op.add_column('user', sa.Column('is_global_admin', sa.Boolean(), nullable=True))
        op.add_column('user', sa.Column('account_owner_id', sa.Integer(), nullable=True))

        conn.execute(text(f"UPDATE user SET is_global_admin = 0"))
        conn.execute(text(f"UPDATE user SET is_global_admin = 1 WHERE id = {first_admin_id}"))

        op.create_foreign_key('fk_user_account_owner', 'user', 'user', ['account_owner_id'], ['id'])

        # Add user_id to other tables
        for table in ['schedule', 'balance', 'hold', 'skip', 'email']:
            op.add_column(table, sa.Column('user_id', sa.Integer(), nullable=True))
            conn.execute(text(f"UPDATE {table} SET user_id = {first_admin_id}"))
            op.alter_column(table, 'user_id', nullable=False)
            op.create_foreign_key(f'fk_{table}_user', table, 'user', ['user_id'], ['id'])

        # Update constraints
        op.drop_constraint('schedule_name_key', 'schedule', type_='unique')
        op.drop_constraint('email_email_key', 'email', type_='unique')
        op.create_unique_constraint('_user_schedule_uc', 'schedule', ['user_id', 'name'])


def downgrade():
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    if dialect_name == 'sqlite':
        # Recreate original tables
        # USER
        conn.execute(text("""
            CREATE TABLE user_old (
                id INTEGER PRIMARY KEY,
                email VARCHAR(100) UNIQUE,
                password VARCHAR(100),
                name VARCHAR(1000),
                admin BOOLEAN
            )
        """))
        conn.execute(text("""
            INSERT INTO user_old (id, email, password, name, admin)
            SELECT id, email, password, name, admin FROM user
        """))
        conn.execute(text("DROP TABLE user"))
        conn.execute(text("ALTER TABLE user_old RENAME TO user"))

        # SCHEDULE
        conn.execute(text("""
            CREATE TABLE schedule_old (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) UNIQUE,
                amount NUMERIC(10, 2),
                frequency VARCHAR(100),
                startdate DATE,
                type VARCHAR(100),
                firstdate DATE
            )
        """))
        conn.execute(text("""
            INSERT INTO schedule_old (id, name, amount, frequency, startdate, type, firstdate)
            SELECT id, name, amount, frequency, startdate, type, firstdate FROM schedule
        """))
        conn.execute(text("DROP TABLE schedule"))
        conn.execute(text("ALTER TABLE schedule_old RENAME TO schedule"))

        # BALANCE
        conn.execute(text("""
            CREATE TABLE balance_old (
                id INTEGER PRIMARY KEY,
                amount NUMERIC(10, 2),
                date DATE
            )
        """))
        conn.execute(text("""
            INSERT INTO balance_old (id, amount, date)
            SELECT id, amount, date FROM balance
        """))
        conn.execute(text("DROP TABLE balance"))
        conn.execute(text("ALTER TABLE balance_old RENAME TO balance"))

        # HOLD
        conn.execute(text("""
            CREATE TABLE hold_old (
                id INTEGER PRIMARY KEY,
                amount NUMERIC(10, 2),
                name VARCHAR(100),
                type VARCHAR(100)
            )
        """))
        conn.execute(text("""
            INSERT INTO hold_old (id, amount, name, type)
            SELECT id, amount, name, type FROM hold
        """))
        conn.execute(text("DROP TABLE hold"))
        conn.execute(text("ALTER TABLE hold_old RENAME TO hold"))

        # SKIP
        conn.execute(text("""
            CREATE TABLE skip_old (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100),
                date DATE,
                amount NUMERIC(10, 2),
                type VARCHAR(100)
            )
        """))
        conn.execute(text("""
            INSERT INTO skip_old (id, name, date, amount, type)
            SELECT id, name, date, amount, type FROM skip
        """))
        conn.execute(text("DROP TABLE skip"))
        conn.execute(text("ALTER TABLE skip_old RENAME TO skip"))

        # EMAIL
        conn.execute(text("""
            CREATE TABLE email_old (
                id INTEGER PRIMARY KEY,
                email VARCHAR(100) UNIQUE,
                password VARCHAR(100),
                server VARCHAR(100),
                subjectstr VARCHAR(100),
                startstr VARCHAR(100),
                endstr VARCHAR(100)
            )
        """))
        conn.execute(text("""
            INSERT INTO email_old (id, email, password, server, subjectstr, startstr, endstr)
            SELECT id, email, password, server, subjectstr, startstr, endstr FROM email
        """))
        conn.execute(text("DROP TABLE email"))
        conn.execute(text("ALTER TABLE email_old RENAME TO email"))

    else:
        # PostgreSQL downgrade
        op.drop_constraint('_user_schedule_uc', 'schedule', type_='unique')
        op.create_unique_constraint('schedule_name_key', 'schedule', ['name'])
        op.create_unique_constraint('email_email_key', 'email', ['email'])

        for table in ['email', 'skip', 'hold', 'balance', 'schedule']:
            op.drop_constraint(f'fk_{table}_user', table, type_='foreignkey')
            op.drop_column(table, 'user_id')

        op.drop_constraint('fk_user_account_owner', 'user', type_='foreignkey')
        op.drop_column('user', 'account_owner_id')
        op.drop_column('user', 'is_global_admin')
