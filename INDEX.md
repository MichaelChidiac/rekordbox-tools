# Rekordbox Tools — Complete Toolkit

A comprehensive set of tools to manage your Traktor music library without relying on Rekordbox GUI.

## 🚀 Quick Start

### Option 1: Easy (Web UI)
```bash
python3.11 sync_web.py
# Open browser → http://localhost:8080
# Click buttons to sync playlists
```

### Option 2: Command Line
```bash
# Sync entire library to USB
python3.11 sync_master.py --to-usb --all

# Pick playlists for USB (interactive)
python3.11 sync_master.py --to-usb --select

# Sync to Rekordbox
python3.11 sync_master.py --to-rekordbox --all
```

---

## 📚 Tools Overview

### Sync & Export (Main Tools)

| Tool | Purpose | Use When |
|------|---------|----------|
| **sync_master.py** | Master orchestrator | You want one command for all sync operations |
| **sync_web.py** | Browser UI | You prefer point-and-click interface |
| **traktor_to_usb.py** | Direct USB export | You need CDJ-compatible USB export |
| **traktor_to_rekordbox.py** | NML → Rekordbox converter | You want Rekordbox alongside Traktor |
| **rebuild_rekordbox_playlists.py** | Playlist sync tool | You modified playlists and need to rebuild |

### Data Management

| Tool | Purpose | Use When |
|------|---------|----------|
| **find_duplicates.py** | Acoustic fingerprint duplicate detector | You have duplicate tracks to identify |
| **merge_duplicates.py** | Merge duplicate track info before removal | You're consolidating duplicate tracks |
| **cleanup_rekordbox_db.py** | Database cleanup | You have orphaned/dead entries in Rekordbox |
| **validate_usb.js** | USB structure validator | You want to verify USB is CDJ-compatible |

### Recovery & Monitoring

| Tool | Purpose | Use When |
|------|---------|----------|
| **traktor_autosave.py** | Auto-save monitor | You want to auto-snapshot your library |
| **pdb_to_traktor.py** | Import history from USB | You want to recover history playlists from USB |
| **read_history.js** | Read Pioneer USB export.pdb | You need to extract history from Pioneer USB |

---

## 🎯 Common Workflows

### Workflow 1: DJ Night — Sync Playlists to USB
```bash
python3.11 sync_master.py --to-usb --select
# Pick playlists in interactive UI
# Done! USB is ready for CDJ
```

### Workflow 2: Weekly Backup — Sync to Rekordbox
```bash
python3.11 sync_master.py --to-rekordbox --all
# Syncs all Traktor playlists, cues, metadata to Rekordbox
```

### Workflow 3: Find & Merge Duplicates
```bash
# Step 1: Find duplicates (acoustic fingerprints)
python3.11 find_duplicates.py

# Step 2: Review report and merge
python3.11 merge_duplicates.py --auto-exact

# Step 3: Delete duplicate files
rm /path/to/duplicate1.flac /path/to/duplicate2.flac
```

### Workflow 4: Multiple USB Drives
```bash
# Sync to USB 1 (party playlists)
python3.11 sync_master.py --to-usb --playlists "01 Events" --usb /Volumes/USB1

# Sync to USB 2 (archive everything)
python3.11 sync_master.py --to-usb --all --usb /Volumes/USB2
```

### Workflow 5: Fast Re-Sync After Adding Tracks
```bash
# Only copy new/changed tracks (much faster)
python3.11 sync_master.py --to-usb --all --sync
```

---

## 📖 Full Documentation

| Document | Purpose |
|----------|---------|
| **SYNC_GUIDE.md** | Complete guide to sync operations |
| **SYNC_QUICKREF.txt** | Quick command reference |
| **README.md** | Tool descriptions and workflows |
| **QUICKSTART.md** | Task-oriented guide for common scenarios |
| **AUTOSAVE.md** | Auto-save & data loss prevention |
| **AUTOSAVE_QUICKREF.txt** | Quick reference for auto-save |

---

## 🔧 Advanced Usage

### API / Scripting
```python
import subprocess
import sys

# Sync to USB programmatically
def sync_playlists(names, usb_path=None):
    args = [sys.executable, 'sync_master.py', '--to-usb']
    args.extend(['--playlists'] + names)
    if usb_path:
        args.extend(['--usb', usb_path])
    return subprocess.run(args)

# Example: Sync "Events" and "History" playlists
sync_playlists(['Events', 'History'])
```

### Command Line Chaining
```bash
# Full workflow: backup to Rekordbox, then sync to USB
python3.11 sync_master.py --to-rekordbox --all && \
python3.11 sync_master.py --to-usb --all --sync
```

---

## 🔐 File Locations

| Component | Path |
|-----------|------|
| **Traktor library** | `~/Documents/Native Instruments/Traktor 3.11.1/collection.nml` |
| **Rekordbox library** | `~/Library/Pioneer/rekordbox/master.db` |
| **Rekordbox playlist manifest** | `~/Library/Pioneer/rekordbox/masterPlaylists6.xml` |
| **Tools directory** | `~/projects/rekordbox-tools/` |
| **Backups/snapshots** | Same as collection.nml |

---

## 📋 Requirements

### System
- macOS (or Linux with minor modifications)
- Python 3.11+

### Python Packages
```bash
pip3.11 install sqlcipher3 questionary pyacoustid
```

### External Tools
- `fpcalc` (for duplicate detection via AcoustID)
  ```bash
  brew install chromaprint  # macOS
  ```

---

## ✨ Key Features

✅ **One-Command Sync** — sync_master.py orchestrates all operations
✅ **Web UI** — Browser-based interface (no installation needed)
✅ **Incremental Sync** — Only new/changed tracks (fast re-sync)
✅ **Dry-Run Mode** — Preview changes before writing
✅ **Interactive UI** — Checkbox selection of playlists
✅ **Auto-Save** — Snapshot library before risky operations
✅ **Duplicate Detection** — Acoustic fingerprints + metadata matching
✅ **Duplicate Merge** — Consolidate playlists & metadata before deletion
✅ **USB Validation** — Verify Pioneer USB structure
✅ **Rekordbox Bypass** — Direct DB manipulation (no GUI needed)

---

## 🐛 Troubleshooting

### "USB not detected"
```bash
# Use manual path:
python3.11 sync_master.py --to-usb --all --usb /Volumes/MYUSB
```

### "Permission denied"
```bash
# Re-mount USB:
diskutil unmount /Volumes/MYUSB
diskutil mount /Volumes/MYUSB
```

### "Sync failed"
```bash
# Preview with dry-run:
python3.11 sync_master.py --to-usb --all --dry-run

# Check logs in sync_master output
```

### "Lost edits"
```bash
# Restore from backup:
cp ~/Documents/.../collection.snapshot_TIMESTAMP.nml collection.nml
```

---

## 📞 Support

Check documentation files:
- `SYNC_GUIDE.md` — Comprehensive sync guide
- `README.md` — Tool descriptions
- `QUICKSTART.md` — Task-oriented workflows

Run with `--help`:
```bash
python3.11 sync_master.py --help
python3.11 find_duplicates.py --help
python3.11 traktor_autosave.py --help
```

---

## 🎵 Summary

```
Your Music Library Workflow:

  Traktor (Editing)
      ↓
  sync_master.py (Orchestrator)
      ├→ Rekordbox (Backup)
      ├→ USB (CDJ-Compatible Export)
      └→ Local Snapshots (Auto-Save)

  Plus:
    - Duplicate detection & merging
    - USB validation
    - Auto-save checkpoints
    - Interactive UI or CLI
```

Start with `sync_web.py` for easiest experience, or `sync_master.py` for full control.
