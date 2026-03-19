# Sync Master — Complete Guide

Master tool for syncing your Traktor library to Rekordbox and USB drives.

## Quick Start

### Option 1: Command Line (Advanced)
```bash
# Sync entire library to Rekordbox
python3.11 sync_master.py --to-rekordbox --all

# Pick playlists for USB (interactive)
python3.11 sync_master.py --to-usb --select

# Sync all to USB with fast re-sync mode
python3.11 sync_master.py --to-usb --all --sync

# Preview changes without writing
python3.11 sync_master.py --to-usb --all --dry-run
```

### Option 2: Web UI (Easy)
```bash
python3.11 sync_web.py
# Opens: http://localhost:8080
```

---

## Operations

### Sync to Rekordbox
Converts your Traktor collection to Rekordbox format and updates `master.db`.

**When to use:**
- You want to use Rekordbox alongside Traktor
- You need Rekordbox playlists for CDJ/XDJ controllers
- You want to export to Rekordbox-compatible USB

**Command:**
```bash
python3.11 sync_master.py --to-rekordbox --all
```

**What it does:**
1. ✅ Reads your Traktor `collection.nml`
2. ✅ Converts all playlists, cues, grids, metadata
3. ✅ Updates Rekordbox `master.db` (SQLCipher encrypted)
4. ✅ Syncs playlist manifest (`masterPlaylists6.xml`)

---

### Sync to USB
Exports playlists directly to a Pioneer USB drive (no Rekordbox needed).

**When to use:**
- You're playing on CDJ-3000, XDJ-RX3, or XDJ-XZ
- You want a portable library without Rekordbox installed
- You need to sync specific playlists to USB

**Formats supported:**
- FLAC, WAV, AIFF, MP3, AAC, OGG

**Commands:**

```bash
# Interactive: pick playlists
python3.11 sync_master.py --to-usb --select

# Sync entire library
python3.11 sync_master.py --to-usb --all

# Sync specific playlists by name
python3.11 sync_master.py --to-usb --playlists "01 Events" "02 History"

# Incremental sync (only new/changed tracks)
python3.11 sync_master.py --to-usb --all --sync

# Specify USB path (auto-detected if omitted)
python3.11 sync_master.py --to-usb --all --usb /Volumes/MYUSB
```

**What it writes to USB:**
```
/PIONEER/rekordbox/
  ├── exportLibrary.db          ← SQLCipher database (same as master.db schema)
  ├── masterPlaylists6.xml      ← Playlist manifest
  └── USBANLZ/                  ← Waveforms, beat grids, cue points
/Contents/
  ├── Artist Name/              ← Audio files (organized by artist)
  └── Track Name.flac
```

---

## Selection Modes

### --all
Syncs your **entire library**.

```bash
python3.11 sync_master.py --to-usb --all
```

### --select
**Interactive mode** — checkboxes to pick folders/playlists.

```bash
python3.11 sync_master.py --to-usb --select

# Output:
#   ── 01 Events (8 playlists) ──
#     [ ] Wedding 2025
#     [x] Club Night 2025
#     [ ] Fashion Show
#   ── 02 History (5 playlists) ──
#     [x] History 2025
#     ...
#
# Use SPACE to toggle, A to toggle all, ENTER to confirm
```

### --playlists NAME [NAME ...]
Sync specific named playlists.

```bash
python3.11 sync_master.py --to-usb --playlists "01 Events" "History"
```

---

## USB Options

### --sync
**Incremental sync** — only copies new or changed tracks.

Much faster than full re-sync. Saves time and USB wear.

```bash
# First sync (full):
python3.11 sync_master.py --to-usb --all

# Later: sync only changes
python3.11 sync_master.py --to-usb --all --sync
```

### --usb PATH
Manually specify USB mount point (auto-detected if omitted).

```bash
python3.11 sync_master.py --to-usb --all --usb /Volumes/PIONEER_USB
```

### --dry-run
Preview changes **without writing to disk**.

```bash
python3.11 sync_master.py --to-usb --all --dry-run

# Output shows what would be copied:
#   [1/5000] Copying tracks…
#   ✅ Would copy 5000 tracks
#   ✅ Would write 120 playlists
#   (no files actually written)
```

---

## Web UI

Easiest way to sync for non-technical users.

**Start:**
```bash
python3.11 sync_web.py
# Opens: http://localhost:8080
```

**Features:**
- 🎯 Choose target (Rekordbox or USB)
- 📋 Choose what to sync (all or interactive)
- ⚙️ Options for USB (incremental, dry-run)
- ✅ Click "Start Sync" — watch progress in real-time

---

## Workflows

### Workflow 1: DJ Night Prep
You're heading out and need your latest playlists on USB.

```bash
# Pick playlists for the night
python3.11 sync_master.py --to-usb --select

# Confirm in the interactive UI, hit ENTER
# Then plug USB into CDJ and play!
```

### Workflow 2: Regular Backup to Rekordbox
Sync your growing Traktor library to Rekordbox weekly.

```bash
python3.11 sync_master.py --to-rekordbox --all
```

### Workflow 3: Fast Re-sync to USB
You added 50 new tracks this week, want to update your USB without full copy.

```bash
python3.11 sync_master.py --to-usb --all --sync
```

### Workflow 4: Multiple USBs
Sync to different USB drives at different times.

```bash
# USB 1: Portable party USB
python3.11 sync_master.py --to-usb --select --usb /Volumes/USB1

# USB 2: Archive USB (all tracks)
python3.11 sync_master.py --to-usb --all --usb /Volumes/USB2
```

---

## Troubleshooting

### "No Pioneer USB detected"
**Problem:** USB drive not recognized as Pioneer/Rekordbox format.

**Solution:**
1. Manually specify path:
   ```bash
   python3.11 sync_master.py --to-usb --all --usb /Volumes/MYUSB
   ```
2. Or format USB first (see separate USB format guide)

### "Permission denied writing to USB"
**Problem:** USB is read-only or file system issues.

**Solution:**
1. Eject and re-mount:
   ```bash
   diskutil unmount /Volumes/MYUSB
   diskutil mount /Volumes/MYUSB
   ```
2. Check permissions:
   ```bash
   ls -la /Volumes/MYUSB/PIONEER/
   ```

### "Export failed — disk full"
**Problem:** USB doesn't have enough space.

**Solution:**
- Use `--select` to sync only essential playlists
- Remove old tracks from USB first
- Use a larger USB drive

### "Only some tracks were synced"
**Problem:** --sync skipped already-synced files.

**Solution:**
- This is intentional! Use `--dry-run` to preview:
  ```bash
  python3.11 sync_master.py --to-usb --all --sync --dry-run
  ```
- To force a full re-sync, delete and re-create the USB library

---

## API / Scripting

Use `sync_master.py` programmatically:

```python
import subprocess
import sys

def sync_to_usb(playlists=None, incremental=False):
    args = [sys.executable, 'sync_master.py', '--to-usb']
    
    if playlists:
        args.extend(['--playlists'] + playlists)
    else:
        args.append('--all')
    
    if incremental:
        args.append('--sync')
    
    return subprocess.run(args)

# Example:
sync_to_usb(['01 Events', 'History'], incremental=True)
```

---

## File Locations

| Component | Location |
|-----------|----------|
| Traktor library | `~/Documents/Native Instruments/Traktor 3.11.1/collection.nml` |
| Rekordbox library | `~/Library/Pioneer/rekordbox/master.db` |
| USB (mounted) | `/Volumes/MYUSB/PIONEER/` |
| This tool | `~/projects/rekordbox-tools/sync_master.py` |
| Web UI | `~/projects/rekordbox-tools/sync_web.py` |

---

## Summary

```
Sync Master

  --to-rekordbox    Update Rekordbox from Traktor
  --to-usb          Export to Pioneer USB (CDJ-compatible)

  --all             Entire library
  --select          Interactive picker
  --playlists NAME  Specific playlists

  --sync            Incremental (USB only)
  --dry-run         Preview without writing
  --usb PATH        USB mount point

Examples:
  python3.11 sync_master.py --to-rekordbox --all
  python3.11 sync_master.py --to-usb --select
  python3.11 sync_master.py --to-usb --all --sync
  python3.11 sync_web.py    # Web UI
```
