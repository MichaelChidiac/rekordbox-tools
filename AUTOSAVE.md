# Auto-Save & Data Loss Prevention

This guide covers how to protect your work from being lost when using the Rekordbox tools.

## Problem: Export Failed / Tags Lost

When you:
1. Edit tags/metadata in Traktor or the web UI
2. Hit "Verify" or "Next" 
3. The export fails or crashes
4. Your edits are gone

**Solution:** These tools now auto-save at every checkpoint.

---

## Auto-Save Features

### 1. traktor_autosave.py — Standalone Monitor

Runs in the background and watches your `collection.nml` for changes.

**Start monitoring before editing:**
```bash
python3.11 traktor_autosave.py --watch &
```

Then open Traktor and edit tags. The script will detect each save and confirm.

**Create a snapshot before risky operations:**
```bash
python3.11 traktor_autosave.py --snapshot
# Creates: collection.snapshot_20260319_143015.nml
```

**Stop monitoring:**
```bash
# Press Ctrl+C in the terminal, or find and kill the process
```

---

### 2. traktor_to_usb.py — Built-in Checkpoints

The USB export tool now saves progress at every step:

```
Step                                Status
────────────────────────────────────────────────────────
[1] Load playlists from master.db   ✅ Saved
[2] Playlist selection (--select)   ✅ Checkpoint: "Playlist selection confirmed"
[3] Audio files copied              ✅ Checkpoint: "100 tracks copied"
[4] Playlist manifest written       ✅ Checkpoint: "Playlists written to exportLibrary.db"
[5] masterPlaylists6.xml written    ✅ Checkpoint: "Playlist manifest written"
[6] Sync state saved                ✅ Checkpoint: "Sync state saved, USB export complete"
```

If any step fails, the checkpoint message shows exactly what succeeded before the error.

**Example: If export fails at step 4**
```
❌ Export failed: Permission denied writing to /Volumes/MYUSB/PIONEER/…

✅ Steps completed before failure:
  • Playlist selection confirmed
  • 5,234 audio files copied
  • Playlists written to exportLibrary.db
```

---

### 3. merge_duplicates.py — Auto-Backup on Start

```bash
# Always creates a timestamped backup before making changes:
python3.11 merge_duplicates.py --auto-exact
# Backup: collection.nml.bak_20260317_095023
```

If anything goes wrong, restore:
```bash
cp collection.nml.bak_20260317_095023 collection.nml
```

---

## Best Practices

### Before Major Operations
1. **Always create a snapshot:**
   ```bash
   python3.11 traktor_autosave.py --snapshot
   ```

2. **Verify you're editing the right file:**
   ```bash
   ls -lh ~/Documents/Native\ Instruments/Traktor\ 3.11.1/collection.nml
   ```

### During Long Operations
1. **Start a monitor in a separate terminal:**
   ```bash
   python3.11 traktor_autosave.py --watch
   ```

2. **Watch the checkpoint messages** — they show exactly what's being saved.

### If Export Fails
1. **Read the checkpoint message** — it tells you what succeeded before failure
2. **Fix the issue** (e.g., unmount/remount USB, free disk space)
3. **Restore from snapshot if needed:**
   ```bash
   cp collection.snapshot_TIMESTAMP.nml collection.nml
   ```
4. **Run the export again** — it will re-process only what wasn't completed

---

## File Locations

| File | Purpose | Path |
|------|---------|------|
| **collection.nml** | Traktor library (CURRENT) | `~/Documents/Native Instruments/Traktor 3.11.1/` |
| **collection.backup_*** | Pre-merge snapshot | Same directory |
| **collection.snapshot_*** | Auto-save checkpoint | Same directory |
| **exportLibrary.db** | USB library (written during export) | `/Volumes/MYUSB/PIONEER/rekordbox/` |
| **masterPlaylists6.xml** | Playlist manifest | `/Volumes/MYUSB/PIONEER/rekordbox/` |

---

## Troubleshooting

### "Only 9 tags saved, I did more"
- **Cause:** Export failed mid-way
- **Fix:** Check the checkpoint message to see where it stopped
- **Prevention:** Run `--watch` next time to confirm saves as they happen

### "Export failed — permission denied"
- **Cause:** USB became read-only or unmounted
- **Fix:** Eject and re-mount USB, then re-run export
- **Prevention:** Use `--dry-run` first to validate USB is writable

### "I lost my edits"
- **Cause:** Traktor crashed before saving, or tool crashed before checkpoint
- **Fix:** Restore from `collection.snapshot_*` or `collection.backup_*`
- **Prevention:** Use auto-save monitor (`--watch`) to catch unsaved edits

---

## API: Using Auto-Save in Your Own Scripts

```python
from traktor_to_usb import set_checkpoint_callback, checkpoint, force_checkpoint

# Register a custom save function
def my_save(reason):
    print(f"💾 SAVING: {reason}")
    # Save your data here
    pass

set_checkpoint_callback(my_save)

# Mark work as "in progress"
checkpoint("Before risky operation")

# Do some work...
# checkpoint("Step 1 complete")
# checkpoint("Step 2 complete")

# Force save on exit
force_checkpoint()
```

---

## Summary

- ✅ **Snapshots:** `traktor_autosave.py --snapshot` before risky work
- ✅ **Monitoring:** `traktor_autosave.py --watch` during long operations
- ✅ **Backups:** All tools auto-backup before making changes
- ✅ **Checkpoints:** Export tools save progress at every step
- ✅ **Recovery:** Restore from snapshot if anything fails
