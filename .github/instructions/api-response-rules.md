# Script Output Rules — rekordbox-tools (Strict Enforcement)

> These rules apply to ALL console output from rekordbox-tools Python scripts.
> There are no JSON APIs, no HTTP responses — just terminal output.

---

## Output Principles

1. **Dry-run output is always prefixed with `[dry-run]`**
2. **Success indicators use `✅`**
3. **Warning indicators use `⚠️`**
4. **Error indicators use `❌`**
5. **Progress on long operations uses `tqdm`**
6. **Final summary always shows counts and paths**

---

## Dry-Run Output Format

Every `--dry-run` line must be prefixed with `[dry-run]`:

```python
# ✅ CORRECT
if dry_run:
    print("[dry-run] No files will be modified.")
    print(f"[dry-run] Would read:   {nml_path}")
    print(f"[dry-run] Would delete: {delete_count} playlists from master.db")
    print(f"[dry-run] Would insert: {insert_count} playlists into master.db")
    print(f"[dry-run] Would update: {PLAYLISTS_XML}")
    return

# ❌ WRONG — no prefix, user can't tell what's real vs simulated
print(f"Would delete {delete_count} playlists")
```

---

## Status Indicators

| Symbol | Meaning | When to use |
|--------|---------|-------------|
| `✅` | Success / complete | Operation succeeded, backup created, sync done |
| `⚠️` | Warning / attention needed | Non-fatal issue, something was skipped |
| `❌` | Error | Fatal error before exit |
| `→` | Progress step | Sub-step within a larger operation |

```python
# ✅ Success
print(f"✅ Backup created: {backup_path}")
print(f"✅ Complete: {count} playlists inserted")

# ⚠️ Warning
print(f"⚠️  Track not found in NML: {file_path}")
print(f"⚠️  Skipping {count} tracks with no LOCATION element")

# ❌ Error (then sys.exit(1))
print(f"❌ master.db not found: {MASTER_DB}", file=sys.stderr)
sys.exit(1)

# → Progress step
print(f"→ Parsing NML: {nml_path}")
print(f"→ Building playlist tree...")
print(f"→ Writing to master.db...")
```

---

## Progress Reporting with tqdm

Use `tqdm` for any loop over ~100+ items:

```python
from tqdm import tqdm

# ✅ CORRECT — tqdm with description and unit
for track in tqdm(tracks, desc="Inserting tracks", unit="track"):
    insert_track(con, track)

# For nested operations, nest tqdm bars:
for playlist in tqdm(playlists, desc="Playlists", unit="playlist"):
    for track in tqdm(playlist["tracks"], desc=f"  {playlist['name']}", leave=False):
        ...

# ❌ WRONG — manual counter with print
for i, track in enumerate(tracks):
    print(f"Processing {i}/{len(tracks)}...")
    insert_track(con, track)
```

---

## Summary Output Format

Every script must end with a summary:

```python
print(f"\n{'='*50}")
print(f"✅ {script_name} complete")
print(f"{'='*50}")
print(f"   Source:             {nml_path}")
print(f"   Playlists deleted:  {deleted_count}")
print(f"   Playlists inserted: {inserted_count}")
print(f"   Tracks processed:   {track_count}")
print(f"   XML updated:        {PLAYLISTS_XML}")
print(f"   Backup:             {backup_path}")
if dry_run:
    print(f"\n   [dry-run] — no changes were made")
```

---

## Error Messages

Errors go to `stderr`, then the script exits with code 1:

```python
# ✅ CORRECT
print(f"❌ Error: {e}", file=sys.stderr)
sys.exit(1)

# ✅ For missing required files
if not nml_path.exists():
    print(f"❌ NML file not found: {nml_path}", file=sys.stderr)
    print(f"   Is Traktor installed? Expected: {TRAKTOR_NML}", file=sys.stderr)
    sys.exit(1)

# ❌ WRONG — error to stdout, no exit code
print(f"Error: {e}")
```

### Error Messages Must Be Actionable

Error messages should tell the user what to do:

```python
# ✅ CORRECT — actionable
print(f"❌ Cannot write to master.db: {MASTER_DB}", file=sys.stderr)
print(f"   Is Rekordbox running? Close it before running this script.", file=sys.stderr)

# ❌ WRONG — not actionable
print(f"❌ Database error: permission denied", file=sys.stderr)
```

---

## Backup Confirmation Output

Always print the backup path when a backup is created:

```python
def backup_master_db(db_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.parent / f"master_backup_{ts}.db"
    shutil.copy2(db_path, backup)
    print(f"✅ Backup created: {backup}")
    return backup
```

---

## Interactive Prompts (questionary)

For destructive operations (wipe all playlists, overwrite NML), use `questionary` to confirm:

```python
import questionary

if not dry_run:
    confirmed = questionary.confirm(
        f"This will DELETE all {count} playlists from master.db and rebuild from NML. Continue?",
        default=False
    ).ask()
    if not confirmed:
        print("Aborted.")
        sys.exit(0)
```

**Exception:** If `--force` is passed, skip the confirmation prompt.

---

## --help Output Quality

Every script's `--help` must be clear and include example usage:

```python
parser = argparse.ArgumentParser(
    description="Rebuild all playlists in Rekordbox master.db from Traktor NML.",
    epilog="""
Examples:
  python3.11 rebuild_rekordbox_playlists.py --dry-run
  python3.11 rebuild_rekordbox_playlists.py
  python3.11 rebuild_rekordbox_playlists.py --nml ~/Dropbox/collection.nml

IMPORTANT: Close Traktor and Rekordbox before running.
    """
)
```

---

## Verbosity Levels (Optional)

If a script supports `--verbose`:

```python
parser.add_argument("--verbose", "-v", action="store_true",
                    help="Show detailed per-item output")

# Usage
if args.verbose:
    print(f"  → Track {i}: {title} ({artist})")
```

Without `--verbose`, only show progress bars and summary.

---

## Quality Checklist

Before submitting any script:
- [ ] Dry-run output uses `[dry-run]` prefix on every line
- [ ] Status indicators: `✅` success, `⚠️` warning, `❌` error
- [ ] Errors go to `stderr` and exit with code 1
- [ ] Error messages include actionable guidance
- [ ] `tqdm` used for loops >100 items
- [ ] Final summary shows counts and paths
- [ ] Backup path printed after creating backup
- [ ] Destructive operations use `questionary` confirmation
- [ ] `--help` includes example usage
