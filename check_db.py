#!/usr/bin/env python3
"""Check database state and optionally reset for migration"""

import sqlite3
import sys

DB_PATH = 'app/data/db.sqlite'

def check_columns(table_name):
    """Check what columns exist in a table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    conn.close()
    return [col[1] for col in columns]

def remove_columns_if_exist(table_name, columns_to_remove):
    """Remove columns from a table (SQLite requires table recreation)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get current schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    all_columns = cursor.fetchall()

    # Filter out columns we want to remove
    keep_columns = [col for col in all_columns if col[1] not in columns_to_remove]

    if len(keep_columns) == len(all_columns):
        print(f"No columns to remove from {table_name}")
        conn.close()
        return

    print(f"Removing columns {columns_to_remove} from {table_name}...")

    # Build column list for new table
    col_defs = []
    for col in keep_columns:
        col_name = col[1]
        col_type = col[2]
        not_null = "NOT NULL" if col[3] else ""
        default = f"DEFAULT {col[4]}" if col[4] is not None else ""
        pk = "PRIMARY KEY" if col[5] else ""
        col_defs.append(f"{col_name} {col_type} {not_null} {default} {pk}".strip())

    col_names = [col[1] for col in keep_columns]

    # Recreate table without the unwanted columns
    cursor.execute(f"CREATE TABLE {table_name}_temp ({', '.join(col_defs)})")
    cursor.execute(f"INSERT INTO {table_name}_temp SELECT {', '.join(col_names)} FROM {table_name}")
    cursor.execute(f"DROP TABLE {table_name}")
    cursor.execute(f"ALTER TABLE {table_name}_temp RENAME TO {table_name}")

    conn.commit()
    conn.close()
    print(f"Successfully removed columns from {table_name}")

# Check current state
print("=== Current Database State ===\n")

tables_to_check = ['user', 'schedule', 'balance', 'hold', 'skip', 'email']
for table in tables_to_check:
    try:
        cols = check_columns(table)
        print(f"{table}: {', '.join(cols)}")
    except Exception as e:
        print(f"{table}: ERROR - {e}")

print("\n=== Migration Columns ===")
print("New columns that migration will add:")
print("- user: is_global_admin, account_owner_id")
print("- schedule: user_id")
print("- balance: user_id")
print("- hold: user_id")
print("- skip: user_id")
print("- email: user_id")

# Check if migration columns exist
user_cols = check_columns('user')
schedule_cols = check_columns('schedule')

migration_started = False
if 'is_global_admin' in user_cols or 'account_owner_id' in user_cols:
    migration_started = True
    print("\n⚠️  PARTIAL MIGRATION DETECTED!")
    print("Some migration columns already exist.")

if migration_started:
    print("\nOptions:")
    print("1. Remove partially applied migration columns (run with 'reset' argument)")
    print("2. Start with fresh database (backup and delete app/data/db.sqlite)")

    if len(sys.argv) > 1 and sys.argv[1] == 'reset':
        print("\n=== Resetting partial migration ===")

        # Remove migration columns from each table
        remove_columns_if_exist('user', ['is_global_admin', 'account_owner_id'])
        remove_columns_if_exist('schedule', ['user_id'])
        remove_columns_if_exist('balance', ['user_id'])
        remove_columns_if_exist('hold', ['user_id'])
        remove_columns_if_exist('skip', ['user_id'])
        remove_columns_if_exist('email', ['user_id'])

        print("\n✅ Database reset complete! You can now run 'flask db upgrade' again.")
    else:
        print("\nRun: python check_db.py reset")
else:
    print("\n✅ No partial migration detected. Safe to run 'flask db upgrade'")
