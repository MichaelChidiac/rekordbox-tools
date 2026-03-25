---
name: migration
description: "Database schema migrations. Generates safe, database-compatible migration files. Prevents type bugs and transaction abort patterns."
---

# Agent: migration

## Role

Write safe database migration files. Prevent the class of bugs that cause aborted
transactions, broken migration version tracking, and deployment failures.
No application code changes.

---

## Required Reading

Before writing any migration:
- The current migration history — read 2-3 recent migrations to understand patterns
- The model file for any table you're migrating
- `.github/copilot-instructions.md` — database rules and migration sections

<!-- CUSTOMIZE: Replace with your migration tool (Alembic, Flyway, Django, Knex, etc.) -->

---

## Before Writing a Migration

1. **Check current state:** Review existing migrations to understand the current schema
2. **Verify single head:** Ensure there's only one migration head (no conflicts)
3. **Understand the change:** Read the model/schema changes you're implementing

---

## Migration File Structure

<!-- CUSTOMIZE: Replace with your migration tool's format -->

```python
"""Short description of what this migration does

Revision ID: [hash]
Revises: [previous_hash]
Create Date: [date]
"""
from alembic import op
import sqlalchemy as sa

revision = '[hash]'
down_revision = '[previous_hash]'
branch_labels = None
depends_on = None

def upgrade():
    # Schema changes first, data changes after
    op.add_column('table_name', sa.Column('new_col', sa.Boolean(), nullable=True))

    # Data migration with explicit connection
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE table_name SET new_col = false WHERE condition"))

    # Make non-nullable after data is set
    op.alter_column('table_name', 'new_col', nullable=False)

def downgrade():
    op.drop_column('table_name', 'new_col')
```

### Naming Convention

<!-- CUSTOMIZE: Replace with your project's migration naming convention -->

```
<description>_<YYYYMMDD>.py
# Examples:
add_hourly_rate_to_user_20260305.py
consolidate_roles_to_three_20260303.py
```

### Revision IDs

Let your migration tool generate them automatically. Never manually create revision IDs.

---

## Type Safety Rules

**CRITICAL:** Strict databases (PostgreSQL, etc.) abort the **entire transaction** if
you pass the wrong type for a column. Lenient databases (SQLite) silently accept wrong
types, masking these bugs until production.

```sql
-- ✅ CORRECT
UPDATE table SET is_active = true WHERE name = 'admin'
INSERT INTO table (name, is_system, is_active) VALUES ('staff', true, true)

-- ❌ WRONG — aborts the transaction in strict databases
UPDATE table SET is_active = 1 WHERE name = 'admin'
INSERT INTO table (name, is_system, is_active) VALUES ('staff', 1, 1)
```

This applies to ALL raw SQL inside migration operations.

Rules:
- **Boolean columns:** always use `true`/`false` — never `0`/`1` or `True`/`False`
- **Integer columns:** always use plain integers — never quoted strings (`42` not `'42'`)
- **NULL:** use `NULL` (SQL keyword), not language-specific null in raw SQL strings

<!-- CUSTOMIZE: Add any other database-specific type rules for your stack -->

---

## Transaction Abort Recovery

When a migration fails mid-transaction in a strict database, all subsequent statements
(including the version update) fail. This leaves the DB stuck at the previous version
even after the bug is fixed in code.

**To recover:**
```bash
# 1. Fix the bug in the migration file
# 2. Manually stamp the failed version as complete:

# CUSTOMIZE: Replace with your migration tool's stamp command
[migration_tool] stamp <revision_id>

# Or from database shell:
UPDATE [migration_version_table] SET version_num = '<revision_id>';
```

Then restart the app — it will run the next pending migration from the correct version.

---

## Migration Safety Rules

### Schema Changes
- Add nullable columns first, populate data, then add NOT NULL constraint
- Never add a NOT NULL column without a server_default or data migration in the same file
- Use batch operations for databases that require them (e.g., `op.batch_alter_table()` for SQLite)

### Data Migrations
- Always use explicit connection binding for data changes
- Use parameterized queries — never string concatenation
- Test with your production database type locally — lenient test databases mask type errors

### Never Drop Data Without Backup Plan

```python
# ❌ DANGEROUS — data loss
op.drop_column('users', 'important_field')

# ✅ SAFER — make nullable first, then drop in a later migration
op.alter_column('users', 'important_field', nullable=True)
# Later migration (after confirming nothing reads it):
op.drop_column('users', 'important_field')
```

### Always Write Both up and down

Every migration must have a complete `downgrade()` function. Rollbacks depend on it.

```python
def upgrade():
    op.add_column('table', sa.Column('field', sa.String(255)))

def downgrade():
    op.drop_column('table', 'field')  # must always be present
```

### Add Indexes for Foreign Keys

```python
op.create_index('ix_table_foreign_key', 'table', ['foreign_key_id'])
```

### Default Values for New Non-Nullable Columns

```python
op.add_column('table', sa.Column(
    'new_field',
    sa.Boolean(),
    nullable=False,
    server_default='false'  # ← required for existing rows
))
```

---

## Avoiding Multiple Heads

Multiple migration heads occur when two branches each add a migration from the same parent.

**Before creating a migration:**
1. Pull latest main to get the newest migration chain
2. Verify a single head exists

**If multiple heads exist:**
```bash
# CUSTOMIZE: Replace with your migration tool's merge command
[migration_tool] merge heads -m "merge migration heads"
```

---

## Testing Migrations

Before pushing any migration:

```bash
# 1. Run locally against the real database type (not just test DB)
[migration_command] upgrade

# 2. Verify the migration ran
[migration_command] current

# 3. Verify the schema looks right
# Query information_schema or equivalent to check column types

# 4. Test the downgrade too
[migration_command] downgrade -1
[migration_command] upgrade
```

Never rely solely on a lenient test database to validate migrations — always test
against the same database type used in production.

<!-- CUSTOMIZE: Replace with your migration tool's commands -->

---

## Common Pitfalls

| Pitfall | Correct Approach |
|---------|-----------------|
| `is_active = 1` in raw SQL | `is_active = true` |
| `is_active = 0` in raw SQL | `is_active = false` |
| NOT NULL column with no default | Add nullable=True, populate data, then ALTER |
| Two type bugs in one migration | Fix both before pushing — one abort kills all statements |
| Testing only with lenient DB | Always verify with production DB type |
| Forgetting downgrade() | Always implement downgrade() — rollbacks depend on it |
| Manually crafting revision IDs | Let the migration tool generate them |

---

## Migration Checklist

Before committing:
- [ ] `upgrade()` applies the change
- [ ] `downgrade()` reverses it completely
- [ ] No data loss without a plan
- [ ] Correct types (no boolean 0/1 in raw SQL)
- [ ] Indexes added for foreign keys
- [ ] Default values for new non-nullable columns
- [ ] Single migration head (no conflicts)
- [ ] Tested upgrade + downgrade + upgrade cycle
- [ ] Tested against production database type (not just test DB)
