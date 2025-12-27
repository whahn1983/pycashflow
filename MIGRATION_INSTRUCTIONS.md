# Database Migration Instructions

## Issue Fixed
This migration fixes the "NOT NULL constraint failed: balance.user_id" error when deleting users. The root cause was that foreign key constraints were not configured with CASCADE DELETE, causing SQLAlchemy to attempt setting user_id to NULL instead of deleting related records.

## Changes Made

### 1. Model Updates (app/models.py)
- Added `ondelete='CASCADE'` to all foreign key definitions:
  - User.account_owner_id
  - Schedule.user_id
  - Balance.user_id
  - Hold.user_id
  - Skip.user_id
  - Email.user_id
- Added `cascade='all, delete-orphan'` to User.guests relationship

### 2. Foreign Key Enforcement (app/__init__.py)
- Added SQLite pragma to enable foreign key constraints
- Foreign keys are now properly enforced at the database level

### 3. Migration File
- Created migration: `migrations/versions/add_cascade_delete_constraints.py`
- This migration recreates foreign key constraints with CASCADE DELETE

## How to Apply

### If using Docker:

1. Connect to the running container:
   ```bash
   docker exec -it <container_name> bash
   ```

2. Run the migration:
   ```bash
   flask db upgrade
   ```

3. Restart the application:
   ```bash
   docker restart <container_name>
   ```

### If running locally:

1. Ensure virtual environment is activated and dependencies are installed

2. Run the migration:
   ```bash
   flask db upgrade
   ```

3. Restart the Flask application

## Verification

After applying the migration:

1. Try deleting a user with associated data (balances, schedules, etc.)
2. The user and all related records should be deleted successfully
3. No "NOT NULL constraint failed" error should occur

## Rollback (if needed)

To rollback this migration:
```bash
flask db downgrade -1
```

Note: This will remove cascade delete behavior, and you'll need to manually handle related records before deleting users.
