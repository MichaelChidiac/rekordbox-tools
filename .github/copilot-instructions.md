# AI Agent Instructions — rekordbox-tools

## Project Overview

rekordbox-tools is a Python script toolkit for managing DJ libraries across Traktor, Rekordbox, and Pioneer USB drives. It converts Traktor NML collections to Rekordbox XML, rebuilds and syncs playlists in Rekordbox's SQLCipher-encrypted `master.db`, exports libraries directly to Pioneer USB drives, imports USB HISTORY playlists back into Traktor, and detects duplicate tracks via acoustic fingerprinting. There is no web framework, no ORM, and no test suite yet — just standalone Python scripts, two Node.js scripts, and a shared SQLCipher connection pattern.

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language (primary) | Python | 3.11 |
| DB (Rekordbox) | SQLCipher (`sqlcipher3` library) | 4 (legacy mode) |
| DB (fingerprints) | sqlite3 (stdlib, plain) | — |
| XML processing | `xml.etree.ElementTree` (stdlib) | — |
| Acoustic fingerprinting | Chromaprint / `pyrekordbox` | — |
| UI / progress | `questionary`, `tqdm` | — |
| Node.js scripts | `rekordbox-parser` | — |
| Platform | macOS only | — |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `traktor_to_rekordbox.py` | Convert Traktor `collection.nml` → Rekordbox XML |
| `rebuild_rekordbox_playlists.py` | Wipe + rebuild all playlists in `master.db` and `masterPlaylists6.xml` |
| `cleanup_rekordbox_db.py` | Incremental sync — add missing playlists/tracks to existing DB |
| `traktor_to_usb.py` | Export library directly to Pioneer USB drive (no Rekordbox app needed) |
| `sync_master.py` | Master CLI — one command for all operations |
| `pdb_to_traktor.py` | Import USB HISTORY playlist into Traktor's NML (writes timestamped copy) |
| `read_history.js` | Read HISTORY playlists from Pioneer USB (Node.js) |
| `validate_usb.js` | Validate Pioneer USB structure (Node.js) |
| `find_duplicates.py` | Detect duplicate tracks via acoustic fingerprinting (Chromaprint) |

---

## Project Structure

```
rekordbox-tools/
├── traktor_to_rekordbox.py      # NML → Rekordbox XML
├── rebuild_rekordbox_playlists.py
├── cleanup_rekordbox_db.py
├── traktor_to_usb.py
├── sync_master.py               # Master CLI entry point
├── pdb_to_traktor.py
├── find_duplicates.py
├── read_history.js
├── validate_usb.js
├── fingerprints.db              # Chromaprint cache (plain sqlite3, NOT SQLCipher)
├── traktor_to_rekordbox.xml     # Generated output (not committed)
├── tests/                       # pytest tests (being established)
│   └── conftest.py
└── .github/
    ├── copilot-instructions.md  # This file
    ├── agents/
    ├── instructions/
    ├── prompts/
    └── skills/
```

---

## ⚠️ CRITICAL SAFETY RULES

**These rules exist because mistakes can corrupt your Rekordbox library or Traktor collection — there is no easy undo.**

### Rule 1 — NEVER modify `collection.nml` directly

`collection.nml` is Traktor's master collection. It is **sacred**. Any script that writes to NML (e.g., `pdb_to_traktor.py`) must:
1. Create a timestamped backup first: `collection_backup_YYYYMMDD_HHMMSS.nml`
2. Write to the backup copy — never to the original
3. Only update the original after the user explicitly confirms

### Rule 2 — Always `--dry-run` before applying changes to `master.db` or USB

All write operations on `master.db` and USB `exportLibrary.db` must support a `--dry-run` flag that prints what would change without touching the DB.

### Rule 3 — Always backup `master.db` before any write operation

Scripts that write to `master.db` must call a backup function before opening a write connection. Backup path pattern: `master_backup_YYYYMMDD_HHMMSS.db` in the same directory.

### Rule 4 — Close Traktor before reading `collection.nml`

Traktor locks `collection.nml` while running. Reading a locked NML returns stale or corrupted data.

### Rule 5 — Close Rekordbox before writing to `master.db`

Rekordbox holds a write lock on `master.db` while running. Writing to a locked DB will corrupt it.

### Rule 6 — Never hardcode the SQLCipher key in scripts

The SQLCipher key must always come from a constant, environment variable, or config file — never as a string literal inside a function call.

---

## SQLCipher Connection Pattern

**Always set all three PRAGMAs. `PRAGMA legacy=4` is CRITICAL — without it you get "file is not a database".**

```python
import sqlcipher3

SQLCIPHER_KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

def open_rekordbox_db(path: str, readonly: bool = True):
    """Open Rekordbox's SQLCipher-encrypted master.db or exportLibrary.db."""
    flags = sqlcipher3.SQLITE_OPEN_READONLY if readonly else sqlcipher3.SQLITE_OPEN_READWRITE
    con = sqlcipher3.connect(path, flags=flags)
    con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")  # CRITICAL — without this: "file is not a database"
    return con
```

`fingerprints.db` is plain `sqlite3` (NOT SQLCipher) — do not apply the above pattern to it.

---

## Important Invariants

| Invariant | Why it matters |
|-----------|---------------|
| `masterPlaylists6.xml` must stay in sync with `master.db` | Playlists in DB but not in XML are **silently invisible** in Rekordbox UI |
| `rb_local_usn` must never be NULL | Rekordbox silently ignores rows with NULL `rb_local_usn` |
| Playlist names may contain `/` | Use Python tuples as path keys — never split on `/` |
| `export.pdb` vs `exportLibrary.db` | Different Pioneer CDJ models use different formats — check device model before choosing parser |
| `fingerprints.db` is plain sqlite3 | Do not open it with SQLCipher — it will fail to decrypt |

---

## File Paths

| File | Path |
|------|------|
| Rekordbox main DB | `~/Library/Pioneer/rekordbox/master.db` |
| Rekordbox playlist manifest | `~/Library/Pioneer/rekordbox/masterPlaylists6.xml` |
| Traktor collection | `~/Documents/Native Instruments/Traktor 3.11.1/collection.nml` |
| Generated Rekordbox XML | `~/projects/rekordbox-tools/traktor_to_rekordbox.xml` |
| Fingerprint cache | `~/projects/rekordbox-tools/fingerprints.db` |
| Pioneer USB root | `/Volumes/[USB_NAME]/` |
| USB library DB | `/Volumes/[USB_NAME]/PIONEER/rekordbox/exportLibrary.db` |
| USB binary library | `/Volumes/[USB_NAME]/PIONEER/rekordbox/export.pdb` |

---

## Dependencies

```bash
pip3.11 install sqlcipher3 pyrekordbox questionary numpy tqdm
brew install chromaprint
npm install rekordbox-parser  # run from project directory
```

---

## Code Style

### Imports

```python
# Standard library first
import os
import argparse
import shutil
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

# Third-party second
import sqlcipher3
from tqdm import tqdm

# Local application last
# (no package yet — scripts are standalone)
```

### Script Entry Point Pattern

Every script must use `argparse` and support `--dry-run` for any write operation:

```python
def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change without modifying any files")
    args = parser.parse_args()
    ...

if __name__ == "__main__":
    main()
```

### Backup Pattern

```python
def backup_master_db(db_path: Path) -> Path:
    """Create a timestamped backup of master.db before any write operation."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.parent / f"master_backup_{ts}.db"
    shutil.copy2(db_path, backup)
    print(f"✅ Backup created: {backup}")
    return backup
```

### Error Handling

```python
try:
    con = open_rekordbox_db(db_path, readonly=False)
    # ... mutations
    con.commit()
except Exception as e:
    con.rollback()
    print(f"❌ Error: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    con.close()
```

---

## Testing Rules

No test suite exists yet. The test-writer agent is establishing it. When tests are added:

- Test runner: `python3.11 -m pytest tests/ -x`
- Test file per script: `tests/test_traktor_to_rekordbox.py`, etc.
- Unit test conversion logic without needing actual Pioneer hardware or Rekordbox DB
- Use fixture files (small synthetic NML/XML) — no real library files in tests
- Never write to `~/Library/Pioneer/` from tests

---

## Security Rules

- **Never hardcode the SQLCipher key** — use a module-level constant or env var
- **Never commit `master.db` or `collection.nml`** — these are user data files
- **Use parameterized queries** — never string-concatenate SQL with user input
- **Always dry-run** before any destructive write operation
- **Backup before write** — `master.db` backup is mandatory before mutations

---

## Do / Don't

### Do

- ✅ Always set `PRAGMA legacy=4` when connecting to SQLCipher DBs
- ✅ Always create a timestamped backup before writing to `master.db`
- ✅ Always support `--dry-run` on any script that modifies files or databases
- ✅ Keep `masterPlaylists6.xml` in sync with `master.db` after playlist changes
- ✅ Use tuple keys for playlist paths (not string splits on `/`)
- ✅ Print progress with `tqdm` for any operation over ~100 tracks
- ✅ Write to a timestamped NML copy — never to the original `collection.nml`
- ✅ Check `rb_local_usn` is never NULL after DB writes

### Don't

- ❌ Never modify `collection.nml` directly
- ❌ Never hardcode the SQLCipher key as a string literal in function calls
- ❌ Never write to `master.db` without a backup
- ❌ Never apply changes without `--dry-run` testing first
- ❌ Never run scripts that read `collection.nml` while Traktor is open
- ❌ Never run scripts that write to `master.db` while Rekordbox is open
- ❌ Never use `export.pdb` (binary Pioneer format) and `exportLibrary.db` interchangeably
- ❌ Never open `fingerprints.db` with SQLCipher

---

## Sub-Agents

Specialized agent files live in `.github/agents/`. Use them for focused work:

| Agent | File | Use for |
|-------|------|---------|
| task-orchestrator | `.github/agents/task-orchestrator.md` | Automate parallelized agent dispatch |
| planner | `.github/agents/planner.md` | Feature planning, issue generation |
| scripts | `.github/agents/backend.md` | Python script changes, SQLCipher, XML, Pioneer USB patterns |
| test-writer | `.github/agents/test-writer.md` | Writing pytest tests |
| refactor | `.github/agents/refactor.md` | Extract shared utilities, restructure scripts |
| migration | `.github/agents/migration.md` | Schema changes to master.db or fingerprints.db |
| pattern-enforcer | `.github/agents/pattern-enforcer.md` | Bulk consistency fixes across all scripts |

---

## Feature Preservation Rules (MANDATORY)

**Never silently remove, disable, or break existing script behavior.**

Before modifying any script:
1. Read the script's `argparse` options — preserve all existing flags
2. Check whether the script is called from `sync_master.py` — keep the interface stable
3. Never remove `--dry-run` support from any script that has it

When in doubt:
- Add a deprecation comment instead of deleting
- Keep old CLI flags as aliases when renaming
- Ask the user before changing script behavior that could corrupt library data

---

## Automatic Request Routing (AUTO-DETECT-WORKFLOW)

Claude/Copilot automatically detects your request type and routes to the appropriate workflow:

| Request Type | Keywords | Auto Action |
|---|---|---|
| Feature | Add, Implement, Build, New | → PLANNING-WORKFLOW-GUIDE |
| Bug fix | Bug, Fix, Error, Broken | → Quick dispatch to scripts agent |
| Refactor | Split, Reorganize, Extract | → refactor agent |
| Test | Test, Coverage, Write tests | → test-writer agent |
| Code review | Review, Check, Issues | → code-review agent |
| Status | Status, Done, Complete | → Query SQL todos + git history |
| Question | How, Why, What, Explain | → Documentation + examples |
| Raw requirements | Multi-concern bundle | → REQUIREMENTS-INTAKE |

**Key Rule:** Claude will NOT auto-dispatch agents without explicit approval.
**Explicit dispatch triggers:** "Yes", "Go ahead", "Automate", "Execute", "Dispatch"
