# rekordbox-tools

A toolkit for managing a DJ library across **Traktor**, **Rekordbox**, and **Pioneer USB drives** — without relying on a working Rekordbox installation.

---

## Overview

```
Traktor collection.nml
        │
        ▼
traktor_to_rekordbox.py         ← converts Traktor library to Rekordbox XML
        │
        ├──► rebuild_rekordbox_playlists.py   ← writes playlists into Rekordbox app
        │           (master.db + masterPlaylists6.xml)
        │
        └──► traktor_to_usb.py               ← writes directly to USB drive
                    (exportLibrary.db + ANLZ + audio files)

USB drives
        │
        ├──► read_history.js                 ← read HISTORY playlists from USB
        ├──► pdb_to_traktor.py               ← import USB history into Traktor
        └──► validate_usb.js                 ← validate USB structure/completeness

Library maintenance
        │
        └──► find_duplicates.py             ← detect duplicate tracks (AcoustID / Chromaprint)
```

---

## Scripts

### 1. `traktor_to_rekordbox.py` — Convert Traktor → Rekordbox XML

Reads your Traktor `collection.nml` and produces a `traktor_to_rekordbox.xml` used by our other tools.

**What it converts:**
- All tracks with metadata (title, artist, BPM, key, rating, comment, color)
- Hot cues and memory cues → Rekordbox cue points
- Beat grids
- Full playlist/folder hierarchy (handles `/` in names correctly)
- Smartlist logic (evaluated at export time)
- Traktor color labels → Rekordbox color IDs

**Usage:**
```bash
# Default: reads ~/Documents/Native Instruments/Traktor 3.11.1/collection.nml
# Outputs: ~/projects/rekordbox-tools/traktor_to_rekordbox.xml
python3.11 traktor_to_rekordbox.py

# Custom paths
python3.11 traktor_to_rekordbox.py \
  --nml "/path/to/collection.nml" \
  --out "/path/to/output.xml" \
  --cue-color green
```

> ⚠️ **Close Traktor before running** — Traktor locks the NML while open.

---

### 2. `rebuild_rekordbox_playlists.py` — Rebuild Rekordbox Playlist Library

The **definitive fix** for playlists not showing in Rekordbox. Wipes and rebuilds the entire playlist structure in both `master.db` and `masterPlaylists6.xml`.

**When to use:**
- After updating your Traktor library and wanting to sync to Rekordbox
- When playlists are missing or wrong in Rekordbox's UI
- Full library rebuilds (track data is preserved; only playlists are wiped)

**What it writes:**
- `~/Library/Pioneer/rekordbox/master.db` — `djmdPlaylist` + `djmdSongPlaylist` tables
- `~/Library/Pioneer/rekordbox/masterPlaylists6.xml` — Rekordbox's playlist display manifest

**Key technical detail:** Rekordbox reads `masterPlaylists6.xml` on startup to decide which playlists to display. Any playlist in `master.db` that is **not** also in this XML is silently invisible. This script always keeps them in sync.

**Usage:**
```bash
python3.11 rebuild_rekordbox_playlists.py --dry-run   # preview
python3.11 rebuild_rekordbox_playlists.py             # apply (auto-backs up first)
```

> After running, **restart Rekordbox** to see the updated playlists.

**Typical workflow:**
```bash
python3.11 traktor_to_rekordbox.py        # Step 1: convert Traktor → XML
python3.11 rebuild_rekordbox_playlists.py # Step 2: push into Rekordbox DB
# Restart Rekordbox
```

---

### 3. `cleanup_rekordbox_db.py` — Incremental Rekordbox Sync

Adds missing playlists/tracks **incrementally** without wiping everything. Use for small updates (e.g., a new playlist or a few new tracks).

**When to use:** Small incremental updates. For full rebuilds, use `rebuild_rekordbox_playlists.py` instead.

**Usage:**
```bash
python3.11 cleanup_rekordbox_db.py --dry-run   # preview
python3.11 cleanup_rekordbox_db.py             # apply
```

---

### 4. `traktor_to_usb.py` — Export Directly to Pioneer USB

Exports your Traktor library directly to a Pioneer USB drive, **no Rekordbox app needed**. Produces a USB that CDJ-3000, XDJ-RX3, and XDJ-XZ can read natively.

**What it writes to the USB:**

| Path on USB | Purpose |
|---|---|
| `/PIONEER/rekordbox/exportLibrary.db` | Track/playlist database (CDJ-3000, XDJ-RX3) |
| `/PIONEER/rekordbox/masterPlaylists6.xml` | Playlist display manifest |
| `/PIONEER/USBANLZ/…/ANLZ0000.DAT` | Beat grids, waveforms, cue points |
| `/PIONEER/USBANLZ/…/ANLZ0000.EXT` | Extended analysis (colour waveforms) |
| `/Contents/<Artist>/<track>` | Audio files |

> **Requirement:** Tracks must have been analyzed in Rekordbox at least once so their ANLZ files exist locally at `~/Library/Pioneer/rekordbox/share/`.

**Selection modes:**

| Flag | Behaviour |
|---|---|
| `--select` | Interactive checkbox UI to pick playlists |
| `--all` | Export the entire library |
| `--playlists NAME …` | Export specific folder/playlist names |
| *(none)* | Defaults to `--select` in an interactive terminal |

**Other flags:**

| Flag | Behaviour |
|---|---|
| `--usb PATH` | USB mount point (auto-detected if omitted) |
| `--sync` | Incremental: only copy new/changed tracks |
| `--dry-run` | Preview without writing anything |

**Usage examples:**
```bash
# Interactive playlist picker (auto-detects USB)
python3.11 traktor_to_usb.py --select

# Full library export to a specific USB
python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB

# Re-sync full library USB (only copies new/changed tracks — much faster)
python3.11 traktor_to_usb.py --all --usb /Volumes/FULL_LIB_USB --sync

# Export just History and Events folders
python3.11 traktor_to_usb.py \
  --playlists "03 - Events" "04 - History" \
  --usb /Volumes/GIG_USB

# Preview what a full export would do
python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB --dry-run
```

**How `--sync` works:**

`--sync` makes re-exports fast after an initial full export:
1. Reads `exportLibrary.db` already on the USB
2. Compares track IDs and `rb_local_usn` timestamps against `master.db`
3. Only copies audio/ANLZ for **new or changed** tracks
4. Removes tracks no longer in scope
5. Always rewrites the playlist structure (fast — no file I/O)
6. Saves a sync checkpoint so the next `--sync` knows exactly what changed

On first run, `--sync` behaves like a full export (no existing DB to compare against).

---

### 5. `read_history.js` — Read HISTORY Playlists from USB

Reads HISTORY playlists from a Pioneer USB's `export.pdb` without Rekordbox.

**Usage:**
```bash
node read_history.js --list                               # list all history playlists
node read_history.js --playlist "HISTORY 008"             # show tracks
node read_history.js --playlist "HISTORY 008" \
  --pdb /Volumes/MYUSB/.PIONEER/rekordbox/export.pdb
```

Default PDB path: `/Volumes/Extreme SSD/.PIONEER/rekordbox/export.pdb`

---

### 6. `pdb_to_traktor.py` — Import USB History into Traktor

Reads a HISTORY playlist from a Pioneer USB's `export.pdb` and adds it as a new playlist in Traktor's `collection.nml`. Always creates a timestamped backup of the NML first.

**Usage:**
```bash
python3.11 pdb_to_traktor.py --playlist "HISTORY 008" --name "2026-03-14 Gig"

# All arguments have sensible defaults — minimum usage:
python3.11 pdb_to_traktor.py --playlist "HISTORY 008"
```

| Argument | Default |
|---|---|
| `--playlist` | *(required)* |
| `--name` | Same as `--playlist` value |
| `--pdb` | `/Volumes/Extreme SSD/.PIONEER/rekordbox/export.pdb` |
| `--nml` | `~/Documents/Native Instruments/Traktor 3.11.1/collection.nml` |

---

### 7. `validate_usb.js` — Validate Pioneer USB Drive

Checks that a Pioneer USB drive is properly structured and complete.

**Checks performed:**
- Audio files present in `/Contents/`
- ANLZ `.DAT` files present for analyzed tracks
- ANLZ `.EXT` files present
- Playlist summary (top 10 playlists by track count)

**Usage:**
```bash
node validate_usb.js                  # auto-detect all Pioneer USBs
node validate_usb.js /Volumes/MYUSB   # specific drive
```

---

### 8. `find_duplicates.py` — Detect Duplicate Tracks

Scans your library with acoustic fingerprinting (Chromaprint) to find duplicate tracks regardless of filename or metadata. Results are cached so the slow first scan only runs once.

**Detection methods:**

| Method | What it catches |
|---|---|
| Exact fingerprint | Same recording in two different files — safe to delete one |
| Near fingerprint | Same recording, different encode or format (e.g. WAV + MP3 of same track) |
| Metadata match | Same Title + Artist — may be different versions (review before deleting) |

**For each duplicate group, the report recommends which file to keep** — preferring lossless formats (FLAC > WAV > AIFF) and larger file sizes as a quality proxy.

**Usage:**
```bash
# First run: fingerprint all tracks (~5 min), then show report
python3.11 find_duplicates.py

# Re-run report instantly (uses cached fingerprints)
python3.11 find_duplicates.py --report-only

# Save report to a file
python3.11 find_duplicates.py --report-only --out duplicates.txt

# Only show exact duplicates (safest to remove)
python3.11 find_duplicates.py --exact-only

# Tighter near-match threshold (default 0.85)
python3.11 find_duplicates.py --similarity 0.90

# Scan just one folder
python3.11 find_duplicates.py --folder "/Volumes/Extreme SSD/music"
```

**Fingerprint cache:** Stored at `fingerprints.db` in the project directory. Re-fingerprints only when a file's modification time changes. Use `--force` to re-scan everything.

---

## Recommended Workflows

### Update Rekordbox after editing Traktor library
```bash
python3.11 traktor_to_rekordbox.py           # 1. convert NML → XML
python3.11 rebuild_rekordbox_playlists.py    # 2. push into Rekordbox DB
# 3. Restart Rekordbox
```

### Export a gig USB (pick what you want)
```bash
python3.11 traktor_to_usb.py --select --usb /Volumes/GIG_USB
```

### Re-sync full-library USB after adding new tracks
```bash
python3.11 traktor_to_rekordbox.py                          # update XML if needed
python3.11 traktor_to_usb.py --all --usb /Volumes/FULL_USB --sync
```

### Import a gig history into Traktor
```bash
node read_history.js --list                                  # see playlists on USB
python3.11 pdb_to_traktor.py --playlist "HISTORY 008" --name "2026-03-14 Gig"
# Restart Traktor
```

### Check a USB is properly exported
```bash
node validate_usb.js
```

---

## Key Technical Details

### Opening master.db (SQLCipher)

```python
import sqlcipher3 as sqlite3
con = sqlite3.connect("~/Library/Pioneer/rekordbox/master.db")
con.execute("PRAGMA key='402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497'")
con.execute("PRAGMA cipher='sqlcipher'")
con.execute("PRAGMA legacy=4")   # ← without this you get "file is not a database"
```

`exportLibrary.db` on USB drives uses the **same key and same schema**.

### The invisible playlist bug (`masterPlaylists6.xml`)

Rekordbox reads `~/Library/Pioneer/rekordbox/masterPlaylists6.xml` at startup. Any `djmdPlaylist` row **not** represented as a `<NODE>` in this file is silently invisible in the UI, regardless of what's in `master.db`.

```xml
<NODE Id="C77E885B" ParentId="0" Attribute="1" Timestamp="1741123456789" Lib_Type="0" CheckType="0"/>
```
- `Id` = uppercase hex of the `djmdPlaylist.ID` decimal value
- `ParentId="0"` = root level
- `Attribute`: `1` = folder, `0` = playlist

`rebuild_rekordbox_playlists.py` and `traktor_to_usb.py` both keep this file in sync automatically.

### Required fields on all inserted DB rows

| Field | Rule |
|---|---|
| `rb_local_usn` | Must not be NULL — Rekordbox silently ignores NULL-usn rows |
| `djmdPlaylist.Seq` | Must not be NULL — use max sibling Seq + 1 |

### Playlist names with `/` in them

Names like `2026/03/14 Aocram` or `Minimal / Deep Tech` contain literal slash characters. All scripts use **Python tuples** (not `/`-joined strings) as path keys internally to avoid treating these as path separators.

### export.pdb vs exportLibrary.db

| | `export.pdb` | `exportLibrary.db` |
|---|---|---|
| Format | Pioneer DeviceSQL binary | SQLCipher (same as master.db) |
| Used by | CDJ-2000NXS2 and older | CDJ-3000, XDJ-RX3, XDJ-XZ |
| Readable | `rekordbox-parser` (Node.js) | `sqlcipher3` (Python) |
| Writable | No library available | Yes — same schema as master.db |

`traktor_to_usb.py` writes `exportLibrary.db` only. For CDJ-2000NXS2 support, export via the Rekordbox app after using `rebuild_rekordbox_playlists.py`.

---

## Dependencies

```bash
# Python (install once)
pip3.11 install sqlcipher3 pyrekordbox questionary numpy tqdm

# Chromaprint (for duplicate detection)
brew install chromaprint

# Node.js (run once from the project directory)
cd ~/projects/rekordbox-tools && npm install rekordbox-parser
```

| Package | Used by |
|---|---|
| `sqlcipher3` | All scripts that touch `master.db` / `exportLibrary.db` |
| `pyrekordbox` | USB validation, ANLZ file reading |
| `questionary` | `traktor_to_usb.py --select` interactive UI |
| `numpy` | `find_duplicates.py` fingerprint similarity |
| `tqdm` | `find_duplicates.py` progress bar |
| `chromaprint` (brew) | `find_duplicates.py` — provides the `fpcalc` binary |
| `rekordbox-parser` | `read_history.js`, `validate_usb.js` |

---

## File Locations Reference

| File | Path |
|---|---|
| Rekordbox main database | `~/Library/Pioneer/rekordbox/master.db` |
| Rekordbox playlist manifest | `~/Library/Pioneer/rekordbox/masterPlaylists6.xml` |
| Rekordbox local ANLZ files | `~/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/` |
| Traktor collection | `~/Documents/Native Instruments/Traktor 3.11.1/collection.nml` |
| Generated Rekordbox XML | `~/projects/rekordbox-tools/traktor_to_rekordbox.xml` |
