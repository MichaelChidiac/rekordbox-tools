# Script Structure Rules — rekordbox-tools (Strict Enforcement)

> These rules apply to all Python scripts in rekordbox-tools.
> There is no service layer, no web framework, no ORM — just standalone Python scripts.
> The equivalent of "service layer rules" for this project is script structure discipline.

---

## Script Architecture

```
User invokes script
    ↓
argparse (CLI parsing + validation)
    ↓
Pre-flight checks (file existence, Rekordbox/Traktor not running)
    ↓
Dry-run preview (if --dry-run)
    ↓
Backup (if writing to master.db or NML)
    ↓
Main operation (DB queries, XML processing, USB export)
    ↓
Post-operation sync (masterPlaylists6.xml if playlists changed)
    ↓
Summary output (counts, paths)
```

---

## Mandatory Script Elements

### 1. Module Docstring

Every script must have a module-level docstring with purpose and usage:

```python
"""
rebuild_rekordbox_playlists.py — Wipe and rebuild all playlists in master.db.

Reads playlist structure from collection.nml, then:
1. Backs up master.db
2. Deletes all playlists from djmdPlaylist
3. Rebuilds playlist hierarchy from NML
4. Regenerates masterPlaylists6.xml

Usage:
    python3.11 rebuild_rekordbox_playlists.py [--dry-run] [--nml PATH]

IMPORTANT:
    Close Traktor before running (NML lock).
    Close Rekordbox before running (master.db lock).
"""
```

### 2. argparse with --dry-run

Every script that writes anything must support `--dry-run`:

```python
def main():
    parser = argparse.ArgumentParser(
        description="Rebuild all playlists in Rekordbox master.db from Traktor NML."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without modifying any files or databases"
    )
    parser.add_argument(
        "--nml",
        type=Path,
        default=TRAKTOR_NML,
        help=f"Path to collection.nml (default: {TRAKTOR_NML})"
    )
    args = parser.parse_args()
    run(nml_path=args.nml, dry_run=args.dry_run)
```

### 3. Pre-flight Checks

```python
def check_prereqs(nml_path: Path, db_path: Path):
    """Check prerequisites before running. Raises SystemExit if not met."""
    if not nml_path.exists():
        print(f"❌ NML not found: {nml_path}", file=sys.stderr)
        sys.exit(1)
    if not db_path.exists():
        print(f"❌ master.db not found: {db_path}", file=sys.stderr)
        sys.exit(1)
```

### 4. Backup Before Write

```python
def run(nml_path: Path, dry_run: bool):
    check_prereqs(nml_path, MASTER_DB)

    if not dry_run:
        backup_master_db(MASTER_DB)

    # ... main logic
```

### 5. Dry-Run Output Format

Dry-run output must be consistent and clearly labeled:

```python
if dry_run:
    print("[dry-run] No files will be modified.")
    print(f"[dry-run] Would read playlists from: {nml_path}")
    print(f"[dry-run] Would delete N playlists from master.db")
    print(f"[dry-run] Would insert M playlists into master.db")
    print(f"[dry-run] Would update: {PLAYLISTS_XML}")
    return
```

### 6. Progress Reporting with tqdm

For operations over ~100 tracks, use `tqdm`:

```python
from tqdm import tqdm

for track in tqdm(tracks, desc="Inserting tracks", unit="track"):
    insert_track(con, track)
```

### 7. Summary Output

End every script with a summary of what was done:

```python
print(f"\n✅ Complete:")
print(f"   Playlists deleted:  {deleted_count}")
print(f"   Playlists inserted: {inserted_count}")
print(f"   Tracks processed:   {track_count}")
print(f"   XML updated:        {PLAYLISTS_XML}")
```

---

## What Goes in a Script vs. What Goes in a Shared Utility

| Logic | Location |
|-------|----------|
| SQLCipher connection setup | `utils/db.py` (shared) or script-level constant |
| File path constants | Module-level constants in each script (or `utils/paths.py`) |
| Backup functions | `utils/backup.py` (shared) or defined once per script |
| argparse setup | Always in `main()` of each script |
| Business logic (DB queries, XML transforms) | In the script's own functions |
| NML parsing | Script-level functions (or shared util if used in 3+ scripts) |

---

## Function Design Rules

### Functions receive plain parameters — not argparse Namespace

```python
# ✅ CORRECT — testable without argparse
def rebuild_playlists(nml_path: Path, dry_run: bool = False) -> int:
    """Rebuild all playlists from NML. Returns count of playlists inserted."""
    ...

# ❌ WRONG — untestable (args is an argparse Namespace)
def rebuild_playlists(args):
    nml_path = args.nml
    dry_run = args.dry_run
    ...
```

### Functions return plain values

```python
# ✅ CORRECT — returns count (testable)
def insert_playlists(con, playlists: list[dict]) -> int:
    """Insert playlists into djmdPlaylist. Returns count inserted."""
    count = 0
    for pl in playlists:
        con.execute("INSERT INTO djmdPlaylist ...", ...)
        count += 1
    return count

# ❌ WRONG — prints and returns nothing (untestable)
def insert_playlists(con, playlists):
    for pl in playlists:
        con.execute(...)
    print("Done")
```

### Functions are focused on one concern

```python
# ✅ CORRECT — one function, one job
def parse_nml_playlists(nml_path: Path) -> list[dict]:
    """Parse playlist structure from NML. Returns list of playlist dicts."""
    ...

def build_playlist_tree(playlists: list[dict]) -> dict:
    """Build nested playlist tree from flat list."""
    ...

def write_playlists_to_db(con, tree: dict, dry_run: bool = False) -> int:
    """Write playlist tree to master.db. Returns count written."""
    ...
```

---

## Error Handling Pattern

```python
def run(nml_path: Path, dry_run: bool):
    """Main run function — orchestrates the full operation."""
    check_prereqs(nml_path, MASTER_DB)

    if dry_run:
        print(f"[dry-run] Would process: {nml_path}")
        return

    backup_master_db(MASTER_DB)

    con = None
    try:
        con = open_rekordbox_db(MASTER_DB, readonly=False)
        result = do_the_work(con, nml_path)
        con.commit()
        print(f"✅ Done: {result} items processed")
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted. Rolling back...", file=sys.stderr)
        if con:
            con.rollback()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if con:
            con.rollback()
        sys.exit(1)
    finally:
        if con:
            con.close()
```

---

## Import Order

```python
# 1. Standard library
import argparse
import sys
import shutil
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import sqlite3

# 2. Third-party
import sqlcipher3
from tqdm import tqdm
import questionary

# 3. Local (if utils/ exists)
from utils.db import open_rekordbox_db, SQLCIPHER_KEY
from utils.backup import backup_master_db
from utils.paths import MASTER_DB, PLAYLISTS_XML, TRAKTOR_NML
```

---

## File Path Constants

Define as module-level Path constants — never hardcoded inline:

```python
from pathlib import Path

MASTER_DB = Path.home() / "Library/Pioneer/rekordbox/master.db"
PLAYLISTS_XML = Path.home() / "Library/Pioneer/rekordbox/masterPlaylists6.xml"
TRAKTOR_NML = Path.home() / "Documents/Native Instruments/Traktor 3.11.1/collection.nml"
FINGERPRINTS_DB = Path(__file__).parent / "fingerprints.db"
```

---

## Quality Checklist

Before submitting any script change:
- [ ] Module-level docstring with purpose and usage
- [ ] `--dry-run` supported and clearly labelled in output
- [ ] Backup called before any `master.db` write
- [ ] Functions take plain parameters (not argparse Namespace)
- [ ] Functions return values (not just print)
- [ ] `tqdm` used for loops over >100 items
- [ ] Summary output at the end
- [ ] Syntax check: `python3.11 -m py_compile [script].py`
- [ ] `python3.11 [script].py --help` works correctly
