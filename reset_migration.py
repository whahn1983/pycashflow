#!/usr/bin/env python3
"""Reset database to pre-migration state"""

import sqlite3
import os

DB_PATH = 'app/data/db.sqlite'

def table_exists(conn, table_name):
    """Check if a table exists"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def get_columns(conn, table_name):
    """Get list of columns in a table"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [col[1] for col in cursor.fetchall()]

def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)

    print("=== Checking for partially migrated tables ===\n")

    # Check for new tables created by failed migration
    new_tables = ['user_new', 'schedule_new', 'balance_new', 'hold_new', 'skip_new', 'email_new']
    old_tables = ['user_old', 'schedule_old', 'balance_old', 'hold_old', 'skip_old', 'email_old']

    found_new = [t for t in new_tables if table_exists(conn, t)]
    found_old = [t for t in old_tables if table_exists(conn, t)]

    if found_new:
        print(f"⚠️  Found partially created tables: {', '.join(found_new)}")
        print("Dropping these tables...\n")
        for table in found_new:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        print("✅ Cleaned up partial migration tables\n")

    if found_old:
        print(f"⚠️  Found old backup tables: {', '.join(found_old)}")
        print("Dropping these tables...\n")
        for table in found_old:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        print("✅ Cleaned up old backup tables\n")

    # Check if migration columns exist in main tables
    print("=== Checking main tables ===\n")

    tables_to_check = {
        'user': ['is_global_admin', 'account_owner_id'],
        'schedule': ['user_id'],
        'balance': ['user_id'],
        'hold': ['user_id'],
        'skip': ['user_id'],
        'email': ['user_id']
    }

    migration_columns_found = False

    for table, migration_cols in tables_to_check.items():
        if table_exists(conn, table):
            current_cols = get_columns(conn, table)
            found_migration_cols = [col for col in migration_cols if col in current_cols]

            if found_migration_cols:
                migration_columns_found = True
                print(f"⚠️  Table '{table}' has migration columns: {', '.join(found_migration_cols)}")
            else:
                print(f"✅ Table '{table}' is in original state")
        else:
            print(f"❌ Table '{table}' does not exist!")

    if migration_columns_found:
        print("\n⚠️  WARNING: Migration columns found in main tables!")
        print("This means the migration partially succeeded.")
        print("\nYour options:")
        print("1. Manually remove migration columns (complex)")
        print("2. Backup data, delete database, recreate (recommended)")
        print("3. Try to complete migration manually")

        response = input("\nDo you want to backup your database? (yes/no): ").lower()
        if response == 'yes':
            backup_path = DB_PATH + '.backup'
            import shutil
            shutil.copy2(DB_PATH, backup_path)
            print(f"✅ Database backed up to {backup_path}")

            response2 = input("\nDelete current database and start fresh? (yes/no): ").lower()
            if response2 == 'yes':
                conn.close()
                os.remove(DB_PATH)
                print("✅ Database deleted. Run 'flask db upgrade' to create fresh database with migration applied.")
            else:
                print("Database kept. You'll need to manually fix the migration state.")
        else:
            print("No changes made.")
    else:
        print("\n✅ Database is in original pre-migration state!")
        print("You can safely run 'flask db upgrade' now.")

    conn.close()

if __name__ == '__main__':
    main()
