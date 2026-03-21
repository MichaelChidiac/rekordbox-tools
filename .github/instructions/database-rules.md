# Database Rules — rekordbox-tools (Strict Enforcement)

> These rules apply to all database interactions in rekordbox-tools.
> There are two databases: SQLCipher-encrypted `master.db` (owned by Rekordbox) and plain sqlite3 `fingerprints.db` (owned by this project).

---

## The Two Databases

| Database | Format | Owner | Location |
|----------|--------|-------|----------|
| `master.db` | SQLCipher (encrypted) | Rekordbox app | `~/Library/Pioneer/rekordbox/master.db` |
| `exportLibrary.db` | SQLCipher (encrypted) | Pioneer CDJ / Rekordbox | `/Volumes/[USB]/PIONEER/rekordbox/exportLibrary.db` |
| `fingerprints.db` | Plain sqlite3 | rekordbox-tools | `~/projects/rekordbox-tools/fingerprints.db` |

---

## SQLCipher Connection Pattern (master.db and exportLibrary.db)

**Always set all three PRAGMAs. `PRAGMA legacy=4` is CRITICAL — without it, SQLCipher says "file is not a database".**

```python
import sqlcipher3

SQLCIPHER_KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

def open_rekordbox_db(path: str, readonly: bool = True):
    """Open Rekordbox's SQLCipher-encrypted master.db or exportLibrary.db."""
    flags = sqlcipher3.SQLITE_OPEN_READONLY if readonly else sqlcipher3.SQLITE_OPEN_READWRITE
    con = sqlcipher3.connect(path, flags=flags)
    con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")      # 1. Set encryption key
    con.execute("PRAGMA cipher='sqlcipher'")           # 2. Set cipher
    con.execute("PRAGMA legacy=4")                     # 3. CRITICAL — legacy mode
    return con
```

### ❌ WRONG — Missing PRAGMA legacy=4

```python
# ❌ WILL FAIL with "file is not a database"
con.execute(f"PRAGMA key='{key}'")
con.execute("PRAGMA cipher='sqlcipher'")
# Missing PRAGMA legacy=4 → SQLCipher cannot open the file
```

### ❌ WRONG — Hardcoded key in function call

```python
# ❌ Never inline the key string
con.execute("PRAGMA key='402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497'")

# ✅ Always use the module-level constant
con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")
```

---

## fingerprints.db — Plain sqlite3 (NOT SQLCipher)

`fingerprints.db` is a plain SQLite database. **Do not apply SQLCipher PRAGMAs to it.**

```python
import sqlite3
from pathlib import Path

FINGERPRINTS_DB = Path(__file__).parent / "fingerprints.db"

def open_fingerprints_db():
    """Open the fingerprint cache database (plain sqlite3, NOT SQLCipher)."""
    con = sqlite3.connect(FINGERPRINTS_DB)
    # NO PRAGMA key, NO PRAGMA cipher, NO PRAGMA legacy
    return con
```

---

## master.db Write Rules

### Always backup before writing

```python
from datetime import datetime
import shutil
from pathlib import Path

MASTER_DB = Path.home() / "Library/Pioneer/rekordbox/master.db"

def backup_master_db(db_path: Path = MASTER_DB) -> Path:
    """Create a timestamped backup before any write to master.db."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.parent / f"master_backup_{ts}.db"
    shutil.copy2(db_path, backup)
    print(f"✅ Backup created: {backup}")
    return backup

# Pattern: always backup before opening write connection
def apply_changes(dry_run: bool = False):
    if not dry_run:
        backup_master_db()
    con = open_rekordbox_db(MASTER_DB, readonly=False)
    try:
        # mutations
        con.commit()
    except Exception as e:
        con.rollback()
        raise
    finally:
        con.close()
```

### Always use --dry-run for writes

Every function that writes to `master.db` must support a dry-run path:

```python
def rebuild_playlists(dry_run: bool = False):
    """Rebuild all playlists in master.db."""
    if dry_run:
        print("[dry-run] Would delete all playlists and rebuild from NML")
        print(f"[dry-run] Source: {TRAKTOR_NML}")
        return

    backup_master_db()
    con = open_rekordbox_db(MASTER_DB, readonly=False)
    # ... mutations
```

---

## masterPlaylists6.xml Sync Rule

**`masterPlaylists6.xml` must always be kept in sync with `master.db`.**

Playlists that exist in `master.db` but not in `masterPlaylists6.xml` are **silently invisible** in Rekordbox's UI — no error, just missing playlists.

After any playlist operation on `master.db`:
1. Read the updated playlist structure from `master.db`
2. Regenerate `masterPlaylists6.xml` to match
3. Write the XML before closing the DB connection

```python
import xml.etree.ElementTree as ET

PLAYLISTS_XML = Path.home() / "Library/Pioneer/rekordbox/masterPlaylists6.xml"

def sync_playlists_xml(con, dry_run: bool = False):
    """Regenerate masterPlaylists6.xml from master.db playlists."""
    rows = con.execute("""
        SELECT id, Name, ParentID, seq
        FROM djmdPlaylist
        ORDER BY seq
    """).fetchall()

    # Build XML tree from rows...
    if dry_run:
        print(f"[dry-run] Would write {len(rows)} playlists to {PLAYLISTS_XML}")
        return

    # ... write XML
```

---

## rb_local_usn Must Never Be NULL

`rb_local_usn` is a Rekordbox internal sequence field. **Rows with NULL `rb_local_usn` are silently ignored by Rekordbox.**

```python
# ✅ Always set rb_local_usn when inserting
con.execute("""
    INSERT INTO djmdContent (rb_local_usn, Title, Artist, ...)
    VALUES (?, ?, ?, ...)
""", (next_usn, title, artist, ...))

# After INSERT, verify
cur = con.execute("SELECT COUNT(*) FROM djmdContent WHERE rb_local_usn IS NULL")
assert cur.fetchone()[0] == 0, "rb_local_usn must never be NULL"
```

---

## Parameterized Queries (Mandatory)

**Never string-concatenate SQL with user input.**

```python
# ✅ CORRECT — parameterized
con.execute("SELECT * FROM djmdContent WHERE Title = ?", (title,))
con.execute("INSERT INTO djmdPlaylist (Name, ParentID) VALUES (?, ?)", (name, parent_id))

# ❌ WRONG — SQL injection risk
con.execute(f"SELECT * FROM djmdContent WHERE Title = '{title}'")
```

---

## Error Handling Pattern

```python
con = None
try:
    con = open_rekordbox_db(db_path, readonly=False)
    # mutations
    con.commit()
except Exception as e:
    if con:
        con.rollback()
    print(f"❌ Database error: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    if con:
        con.close()
```

---

## Query Patterns

### Read all playlists
```python
rows = con.execute("""
    SELECT id, Name, ParentID, seq, Attribute
    FROM djmdPlaylist
    ORDER BY ParentID, seq
""").fetchall()
```

### Check if track exists
```python
row = con.execute(
    "SELECT id FROM djmdContent WHERE FolderPath = ?", (file_path,)
).fetchone()
if row is None:
    # track not in DB
```

### Get max rb_local_usn for next insert
```python
row = con.execute("SELECT MAX(rb_local_usn) FROM djmdContent").fetchone()
next_usn = (row[0] or 0) + 1
```

---

## fingerprints.db Schema

```sql
CREATE TABLE IF NOT EXISTS fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    fingerprint TEXT,
    duration REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## Summary: Do / Don't

### Do
- ✅ Always set all 3 PRAGMAs for SQLCipher connections (key, cipher, legacy=4)
- ✅ Always backup `master.db` before any write
- ✅ Always support `--dry-run` for write operations
- ✅ Always sync `masterPlaylists6.xml` after playlist changes in `master.db`
- ✅ Always use parameterized queries
- ✅ Use plain `sqlite3` for `fingerprints.db`

### Don't
- ❌ Never apply SQLCipher PRAGMAs to `fingerprints.db`
- ❌ Never hardcode the SQLCipher key as a string literal
- ❌ Never write to `master.db` without a backup
- ❌ Never leave `rb_local_usn` as NULL
- ❌ Never ALTER TABLE on Rekordbox's core tables
- ❌ Never write while Rekordbox app is running
