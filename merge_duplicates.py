#!/usr/bin/env python3.11
"""
merge_duplicates.py
===================
Merges duplicate tracks before deleting them, preserving all information.

For each keep/remove pair it:
  1. Backs up collection.nml
  2. Moves playlist entries   — all playlists "remove" was in now point to "keep"
                                (skips if "keep" is already in that playlist)
  3. Merges hot cues / loops  — fills empty hotcue slots in "keep" from "remove"
                                ("keep" wins if both have the same slot)
  4. Merges INFO fields       — fills empty metadata fields in "keep" from "remove"
                                (comment, genre, rating, key, playcount, etc.)
  5. Merges TEMPO / key       — copies from "remove" if "keep" has none
  6. Removes the entry from COLLECTION
  7. Optionally deletes the file from disk (with --delete)

Sources of duplicate pairs
---------------------------
  • Reads groups from fingerprints.db (produced by find_duplicates.py)
  • Or specify a single pair with --keep / --remove

Usage
-----
  # Interactive: step through each duplicate group and confirm each merge
  python3.11 merge_duplicates.py

  # Auto-merge all EXACT duplicates (same recording, safest)
  python3.11 merge_duplicates.py --auto-exact

  # Auto-merge exact + near duplicates (same song, diff format)
  python3.11 merge_duplicates.py --auto-near

  # Merge a specific pair
  python3.11 merge_duplicates.py --keep /path/to/keep.flac --remove /path/to/remove.mp3

  # Preview changes without writing
  python3.11 merge_duplicates.py --dry-run

  # Also delete the removed file from disk
  python3.11 merge_duplicates.py --delete

  # Merge and also remove from Rekordbox master.db
  python3.11 merge_duplicates.py --update-rekordbox
"""

import argparse, json, os, re, shutil, sqlite3, sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import sqlcipher3

# ── Config ──────────────────────────────────────────────────────────────────────
NML_PATH     = Path.home() / "Documents/Native Instruments/Traktor 3.11.1/collection.nml"
MASTER_DB    = Path.home() / "Library/Pioneer/rekordbox/master.db"
MASTER_KEY   = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
CACHE_DB     = Path(__file__).parent / "fingerprints.db"

# ── NML path encoding ──────────────────────────────────────────────────────────
def loc_to_path(location_elem) -> str:
    """Convert a LOCATION element to an absolute filesystem path."""
    dir_ = location_elem.get('DIR', '')
    file_= location_elem.get('FILE', '')
    parts = [p for p in dir_.split('/:') if p]
    return '/' + '/'.join(parts) + '/' + file_

def path_to_primarykey(path: str, volume: str = 'Macintosh HD') -> str:
    """Convert an absolute path to a Traktor PRIMARYKEY string."""
    # e.g. /Users/chidiacm/Music/track.flac
    # → Macintosh HD/:Users/:chidiacm/:Music/:track.flac
    parts = path.lstrip('/').split('/')
    return volume + '/:'  + '/:'.join(parts)

def path_to_location_attrs(path: str, volume: str = 'Macintosh HD') -> dict:
    """Return LOCATION attribs dict from a full path."""
    p = Path(path)
    parts = str(p.parent).lstrip('/').split('/')
    dir_ = '/:' + '/:'.join(parts) + '/:'
    return {
        'DIR':      dir_,
        'FILE':     p.name,
        'VOLUME':   volume,
        'VOLUMEID': volume,
    }

# ── NML helpers ────────────────────────────────────────────────────────────────
def build_path_index(root) -> dict:
    """Return {absolute_path: entry_element} for all COLLECTION entries."""
    index = {}
    collection = root.find('COLLECTION')
    if collection is None:
        return index
    for entry in collection:
        loc = entry.find('LOCATION')
        if loc is not None:
            index[loc_to_path(loc)] = entry
    return index

def build_pk_index(root) -> dict:
    """Return {primarykey_string: [pk_element, ...]} for all playlist entries."""
    pk_index = {}
    for pk in root.iter('PRIMARYKEY'):
        if pk.get('TYPE') == 'TRACK':
            key = pk.get('KEY', '')
            pk_index.setdefault(key, []).append(pk)
    return pk_index

def get_primarykey_for_entry(entry) -> str:
    """Derive the PRIMARYKEY string from a COLLECTION entry's LOCATION."""
    loc = entry.find('LOCATION')
    if loc is None:
        return ''
    vol = loc.get('VOLUME', 'Macintosh HD')
    return path_to_primarykey(loc_to_path(loc), volume=vol)

# ── Merge logic ─────────────────────────────────────────────────────────────────
RATING_RANK = {'': 0, 'None': 0, 'Maybe': 1, 'Good': 2, 'Great': 3}

def merge_entries(keep_entry, remove_entry, dry_run: bool = False) -> dict:
    """
    Merge remove_entry INTO keep_entry (in-place on keep_entry).
    Returns a summary dict of what changed.
    """
    changes = {
        'cues_added': [],
        'info_fields': [],
        'tempo_added': False,
        'key_added': False,
    }

    # ── CUE_V2 merging ──────────────────────────────────────────────────────
    keep_cues   = keep_entry.findall('CUE_V2')
    remove_cues = remove_entry.findall('CUE_V2')

    # Build a set of occupied hotcue slots in "keep"
    keep_hotcue_slots = {
        int(c.get('HOTCUE', -1))
        for c in keep_cues
        if int(c.get('HOTCUE', -1)) >= 0
    }

    # Map keep cues by (TYPE, rounded START) for dedup of non-hotcue cues
    keep_cue_positions = {
        (c.get('TYPE'), round(float(c.get('START', 0))))
        for c in keep_cues
    }

    for cue in remove_cues:
        hotcue = int(cue.get('HOTCUE', -1))
        cue_type = cue.get('TYPE')
        start_rounded = round(float(cue.get('START', 0)))

        if hotcue >= 0:
            # Hotcue slot: only add if keep doesn't have that slot
            if hotcue not in keep_hotcue_slots:
                if not dry_run:
                    new_cue = deepcopy(cue)
                    keep_entry.append(new_cue)
                keep_hotcue_slots.add(hotcue)
                changes['cues_added'].append(
                    f"hotcue {hotcue} @ {cue.get('START')} ({cue.get('NAME')})"
                )
        else:
            # Non-hotcue: add if no identical position+type in keep
            if (cue_type, start_rounded) not in keep_cue_positions:
                if not dry_run:
                    new_cue = deepcopy(cue)
                    keep_entry.append(new_cue)
                keep_cue_positions.add((cue_type, start_rounded))
                changes['cues_added'].append(
                    f"cue type={cue_type} @ {cue.get('START')} ({cue.get('NAME')})"
                )

    # ── INFO merging ─────────────────────────────────────────────────────────
    keep_info   = keep_entry.find('INFO')
    remove_info = remove_entry.find('INFO')

    if remove_info is not None:
        if keep_info is None:
            if not dry_run:
                keep_entry.append(deepcopy(remove_info))
            changes['info_fields'].append('INFO (entire element, was missing)')
        else:
            for attr, val in remove_info.attrib.items():
                if not val:
                    continue
                existing = keep_info.get(attr, '')
                if attr == 'RATING':
                    # Keep the higher rating
                    if RATING_RANK.get(val, 0) > RATING_RANK.get(existing, 0):
                        if not dry_run:
                            keep_info.set(attr, val)
                        changes['info_fields'].append(f"RATING: {existing!r}→{val!r}")
                elif attr == 'PLAYCOUNT':
                    # Sum play counts
                    combined = str(int(existing or 0) + int(val or 0))
                    if combined != existing:
                        if not dry_run:
                            keep_info.set('PLAYCOUNT', combined)
                        changes['info_fields'].append(f"PLAYCOUNT: {existing}+{val}={combined}")
                elif not existing:
                    # Fill empty field
                    if not dry_run:
                        keep_info.set(attr, val)
                    changes['info_fields'].append(f"{attr}: (empty)→{val!r}")

    # ── TEMPO merging ────────────────────────────────────────────────────────
    keep_tempo   = keep_entry.find('TEMPO')
    remove_tempo = remove_entry.find('TEMPO')
    if keep_tempo is None and remove_tempo is not None:
        if not dry_run:
            keep_entry.append(deepcopy(remove_tempo))
        changes['tempo_added'] = True

    # ── MUSICAL_KEY merging ──────────────────────────────────────────────────
    keep_key   = keep_entry.find('MUSICAL_KEY')
    remove_key = remove_entry.find('MUSICAL_KEY')
    if keep_key is None and remove_key is not None:
        if not dry_run:
            keep_entry.append(deepcopy(remove_key))
        changes['key_added'] = True

    return changes

# ── NML write ──────────────────────────────────────────────────────────────────
def save_nml(tree: ET.ElementTree, path: Path):
    """Write NML preserving the original declaration style."""
    # ET doesn't preserve <?xml ...?> + DOCTYPE, write manually
    xml_str = ET.tostring(tree.getroot(), encoding='unicode', xml_declaration=False)
    out = '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n' + xml_str
    path.write_text(out, encoding='utf-8')

def backup_nml(nml_path: Path) -> Path:
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = nml_path.with_name(f"collection.nml.bak_{now}")
    shutil.copy2(nml_path, bak)
    return bak

# ── Core merge operation ───────────────────────────────────────────────────────
def merge_pair(keep_path: str, remove_path: str,
               root, path_index: dict, pk_index: dict,
               dry_run: bool, delete_file: bool) -> dict:
    """
    Perform a single keep/remove merge on the in-memory NML tree.
    Returns result summary dict.
    """
    result = {
        'keep':            keep_path,
        'remove':          remove_path,
        'keep_found':      keep_path in path_index,
        'remove_found':    remove_path in path_index,
        'playlists_moved': 0,
        'playlists_skipped': 0,
        'cues_added':      [],
        'info_fields':     [],
        'entry_removed':   False,
        'file_deleted':    False,
        'errors':          [],
    }

    if not result['keep_found'] and not result['remove_found']:
        result['errors'].append(f"KEEP track not in collection: {keep_path}")
        result['errors'].append(f"REMOVE track not in collection: {remove_path}")
        return result

    # Auto-swap: if keep isn't in the collection but remove is, swap roles.
    # This happens when ranking prefers a disk-only file over the one in Traktor.
    if not result['keep_found'] and result['remove_found']:
        print(f"  ⚡ Auto-swap: KEEP not in collection, swapping keep↔remove")
        keep_path, remove_path = remove_path, keep_path
        result['keep']         = keep_path
        result['remove']       = remove_path
        result['keep_found']   = True
        result['remove_found'] = path_index.get(remove_path) is not None

    if not result['keep_found']:
        result['errors'].append(f"KEEP track not in collection: {keep_path}")
        return result

    # If remove is not in collection, the file exists on disk but was never imported —
    # nothing to merge in NML, but treat as a clean (no-op) success.
    if not result['remove_found']:
        print(f"  ℹ️  REMOVE track not in collection (disk-only file, nothing to merge in NML)")
        result['entry_removed'] = False
        return result

    # ── Guard: same file path means DB artifact, not a real file duplicate ──
    if keep_path == remove_path:
        result['errors'].append(
            "SKIP: keep and remove paths are identical — this is a Rekordbox DB artifact "
            "(same file indexed twice). Run cleanup_rekordbox_db.py to deduplicate."
        )
        return result

    keep_entry   = path_index[keep_path]
    remove_entry = path_index[remove_path]

    # Keys used in PRIMARYKEY elements
    remove_pk_str = get_primarykey_for_entry(remove_entry)
    keep_pk_str   = get_primarykey_for_entry(keep_entry)

    # ── 1. Move playlist entries ────────────────────────────────────────────
    # Find every playlist that contains "remove"
    remove_pks = pk_index.get(remove_pk_str, [])
    keep_pks   = {pk for pk in pk_index.get(keep_pk_str, [])}

    # Determine which playlists "keep" is already in
    keep_playlist_parents = set()
    for pk in keep_pks:
        # Walk up to find the PLAYLIST parent
        # We need to find the ENTRY parent of each PRIMARYKEY, then its PLAYLIST parent
        # Since ElementTree doesn't have parent references, we rely on structure:
        # PLAYLIST > ENTRY > PRIMARYKEY
        pass

    # Simpler approach: collect all PLAYLISTs "keep" is already in
    # by searching all PLAYLISTs for keep_pk_str
    keep_in_playlists = set()  # set of playlist NODE names that already have "keep"
    for node in root.iter('NODE'):
        if node.get('TYPE') == 'PLAYLIST':
            pl = node.find('PLAYLIST')
            if pl is not None:
                for entry in pl.findall('ENTRY'):
                    pk = entry.find('PRIMARYKEY')
                    if pk is not None and pk.get('KEY') == keep_pk_str:
                        keep_in_playlists.add(node.get('NAME', ''))

    # Now process "remove" playlist memberships
    for node in root.iter('NODE'):
        if node.get('TYPE') != 'PLAYLIST':
            continue
        pl = node.find('PLAYLIST')
        if pl is None:
            continue
        pl_name = node.get('NAME', '')
        entries_to_remove = []
        for entry in pl.findall('ENTRY'):
            pk = entry.find('PRIMARYKEY')
            if pk is None or pk.get('KEY') != remove_pk_str:
                continue
            if pl_name in keep_in_playlists:
                # Keep is already here — remove the duplicate entry
                if not dry_run:
                    entries_to_remove.append(entry)
                result['playlists_skipped'] += 1
            else:
                # Move: update key to point to "keep"
                if not dry_run:
                    pk.set('KEY', keep_pk_str)
                keep_in_playlists.add(pl_name)
                result['playlists_moved'] += 1

        for e in entries_to_remove:
            pl.remove(e)
        # Update ENTRIES count
        if not dry_run and (result['playlists_moved'] + result['playlists_skipped'] > 0):
            actual = len(pl.findall('ENTRY'))
            pl.set('ENTRIES', str(actual))

    # ── 2. Merge tags ────────────────────────────────────────────────────────
    changes = merge_entries(keep_entry, remove_entry, dry_run=dry_run)
    result['cues_added']  = changes['cues_added']
    result['info_fields'] = changes['info_fields']
    if changes['tempo_added']:
        result['info_fields'].append('TEMPO (copied from remove)')
    if changes['key_added']:
        result['info_fields'].append('MUSICAL_KEY (copied from remove)')

    # ── 3. Remove entry from COLLECTION ─────────────────────────────────────
    collection = root.find('COLLECTION')
    if collection is not None and not dry_run:
        try:
            collection.remove(remove_entry)
            collection.set('ENTRIES', str(len(list(collection))))
            result['entry_removed'] = True
            # Evict from path_index so a later pair won't try to remove it again
            path_index.pop(remove_path, None)
        except ValueError:
            # Already removed by a previous merge in this run — treat as OK
            result['entry_removed'] = True
            path_index.pop(remove_path, None)
    elif dry_run:
        result['entry_removed'] = True  # would be removed

    # ── 4. Optionally delete the file ────────────────────────────────────────
    if delete_file and not dry_run and os.path.exists(remove_path):
        os.remove(remove_path)
        result['file_deleted'] = True

    return result

# ── Rekordbox master.db cleanup ────────────────────────────────────────────────
def remove_from_rekordbox(remove_path: str, dry_run: bool):
    """Remove a track from master.db by its file path."""
    con = sqlcipher3.connect(str(MASTER_DB))
    con.execute(f"PRAGMA key='{MASTER_KEY}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")

    row = con.execute(
        "SELECT ID FROM djmdContent WHERE FolderPath=?", (remove_path,)
    ).fetchone()
    if not row:
        con.close()
        return f"Not found in Rekordbox: {remove_path}"

    cid = row[0]
    if not dry_run:
        con.execute("DELETE FROM djmdSongPlaylist WHERE ContentID=?", (cid,))
        con.execute("DELETE FROM djmdCue WHERE ContentID=?", (cid,))
        con.execute("DELETE FROM djmdContent WHERE ID=?", (cid,))
        con.commit()
    con.close()
    return f"Removed ContentID={cid} from Rekordbox"

# ── Duplicate source: fingerprints.db ─────────────────────────────────────────
FORMAT_RANK = {'FLAC': 5, 'WAV': 4, 'AIFF': 3, 'MP3': 2, 'AAC': 1}

def get_file_ext(path: str) -> str:
    return Path(path).suffix.lstrip('.').upper()

def rank_track(path: str, file_size: int, mtime: float = 0.0) -> tuple:
    """Higher score = better quality to keep.
    Tiebreaker: older mtime wins (more likely to have cues/history accumulated)."""
    return (FORMAT_RANK.get(get_file_ext(path), 0), file_size, -(mtime or 0))

def load_duplicate_pairs_from_cache(group_type: str = 'exact') -> list[tuple[str, str]]:
    """
    Re-run duplicate detection using the cached fingerprints.
    Returns list of (keep_path, remove_path) tuples.
    group_type: 'exact', 'near', or 'all'
    """
    if not CACHE_DB.exists():
        print("No fingerprint cache found. Run find_duplicates.py first.")
        sys.exit(1)

    sys.path.insert(0, str(Path(__file__).parent))
    from find_duplicates import (
        load_tracks_from_master, find_duplicates, open_cache
    )

    tracks = load_tracks_from_master(None)
    cache  = open_cache()

    include_near = group_type in ('near', 'all')
    dupes = find_duplicates(tracks, cache, similarity_threshold=0.85,
                            exact_only=(group_type == 'exact'))
    cache.close()

    pairs = []
    groups = dupes['exact']
    if include_near:
        groups += dupes['near']

    for group in groups:
        # Skip DB artifacts (same physical file indexed multiple times)
        unique_paths = {t['path'] for t in group}
        if len(unique_paths) == 1:
            continue  # DB artifact — handled by cleanup_rekordbox_db.py

        # Sort by quality: best first = keep; rest = remove
        sorted_group = sorted(group, key=lambda t: rank_track(t['path'], t.get('file_size', 0), t.get('mtime', 0.0)), reverse=True)
        keep = sorted_group[0]
        for remove in sorted_group[1:]:
            pairs.append((keep['path'], remove['path']))
    return pairs

# ── Report helpers ─────────────────────────────────────────────────────────────
def fmt_size(n):
    for u in ('B','KB','MB','GB'):
        if n < 1024: return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} GB"

def print_result(r: dict, idx: int, total: int):
    tag = f"[{idx}/{total}]"
    status = "✅ OK" if not r['errors'] else "❌ ERROR"
    print(f"\n{tag} {status}")
    print(f"  KEEP  : {r['keep']}")
    print(f"  REMOVE: {r['remove']}")
    if r['errors']:
        for e in r['errors']:
            print(f"  ⚠️  {e}")
        return
    print(f"  Playlists moved : {r['playlists_moved']} | already in playlist (skipped): {r['playlists_skipped']}")
    if r['cues_added']:
        print(f"  Cues merged     : {len(r['cues_added'])}")
        for c in r['cues_added'][:3]:
            print(f"    + {c}")
        if len(r['cues_added']) > 3:
            print(f"    … and {len(r['cues_added'])-3} more")
    if r['info_fields']:
        print(f"  Info merged     : {', '.join(r['info_fields'][:4])}")
    if r['entry_removed']:
        print(f"  COLLECTION entry removed")
    if r['file_deleted']:
        print(f"  File deleted from disk")

# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = ap.add_mutually_exclusive_group()
    src.add_argument('--auto-exact', action='store_true',
                     help='Merge all exact duplicate groups automatically')
    src.add_argument('--auto-near',  action='store_true',
                     help='Merge all exact + near duplicate groups automatically')
    src.add_argument('--keep',   metavar='PATH', help='Path of track to KEEP')

    ap.add_argument('--remove',  metavar='PATH',
                    help='Path of track to REMOVE (required with --keep)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Preview without writing any changes')
    ap.add_argument('--delete',  action='store_true',
                    help='Delete the removed track file from disk')
    ap.add_argument('--update-rekordbox', action='store_true',
                    help='Also remove the track from Rekordbox master.db')
    ap.add_argument('--yes',     action='store_true',
                    help='Skip per-merge confirmation prompts')
    ap.add_argument('--nml',     metavar='PATH', default=str(NML_PATH),
                    help=f'Path to collection.nml (default: {NML_PATH})')
    args = ap.parse_args()

    nml_path = Path(args.nml)
    if not nml_path.exists():
        ap.error(f"NML not found: {nml_path}")

    # ── Build pairs list ──────────────────────────────────────────────────────
    if args.keep:
        if not args.remove:
            ap.error("--remove is required with --keep")
        pairs = [(args.keep, args.remove)]
        interactive = False
    elif args.auto_exact:
        print("Loading exact duplicate groups from fingerprints cache…")
        pairs = load_duplicate_pairs_from_cache('exact')
        interactive = False
    elif args.auto_near:
        print("Loading exact + near duplicate groups from fingerprints cache…")
        pairs = load_duplicate_pairs_from_cache('near')
        interactive = False
    else:
        # Interactive: load pairs and prompt for each
        print("Loading duplicate groups from fingerprints cache…")
        pairs = load_duplicate_pairs_from_cache('exact')
        interactive = True

    if not pairs:
        print("No duplicate pairs found. Run find_duplicates.py first.")
        sys.exit(0)

    print(f"\n{'='*70}")
    print(f"  merge_duplicates.py  —  {len(pairs)} pair(s) to process")
    print(f"  NML: {nml_path}")
    print(f"  Mode: {'DRY RUN — no changes will be written' if args.dry_run else 'LIVE'}")
    if args.delete:
        print(f"  ⚠️  --delete is set: removed files WILL be deleted from disk")
    print(f"{'='*70}\n")

    if not args.dry_run and not args.yes and not interactive:
        resp = input(f"Proceed with {len(pairs)} merge(s)? [y/N] ").strip().lower()
        if resp != 'y':
            print("Aborted.")
            sys.exit(0)

    # ── Load NML ──────────────────────────────────────────────────────────────
    ET.register_namespace('', '')
    tree = ET.parse(str(nml_path))
    root = tree.getroot()
    path_index = build_path_index(root)
    pk_index   = build_pk_index(root)

    # ── Backup ────────────────────────────────────────────────────────────────
    if not args.dry_run:
        bak = backup_nml(nml_path)
        print(f"  Backup: {bak}\n")

    # ── Process pairs ─────────────────────────────────────────────────────────
    results = []
    skipped = 0

    for i, (keep_path, remove_path) in enumerate(pairs, 1):
        keep_ext   = get_file_ext(keep_path)
        remove_ext = get_file_ext(remove_path)
        keep_size  = os.path.getsize(keep_path)  if os.path.exists(keep_path)   else 0
        remove_size= os.path.getsize(remove_path) if os.path.exists(remove_path) else 0

        if interactive:
            print(f"\n{'─'*70}")
            print(f"  Pair {i}/{len(pairs)}")
            print(f"  ✅ KEEP   {keep_ext:<5} {fmt_size(keep_size):>10}  {keep_path}")
            print(f"  ❌ REMOVE {remove_ext:<5} {fmt_size(remove_size):>10}  {remove_path}")
            resp = input("  Merge? [y/N/s(wap)/q(uit)] ").strip().lower()
            if resp == 'q':
                print("Quit.")
                break
            elif resp == 's':
                keep_path, remove_path = remove_path, keep_path
                print(f"  Swapped: now keeping {Path(keep_path).name}")
            elif resp != 'y':
                skipped += 1
                continue

        result = merge_pair(
            keep_path, remove_path,
            root, path_index, pk_index,
            dry_run=args.dry_run,
            delete_file=args.delete
        )
        results.append(result)
        print_result(result, i, len(pairs))

        if args.update_rekordbox and not result['errors']:
            msg = remove_from_rekordbox(remove_path, args.dry_run)
            print(f"  Rekordbox: {msg}")

        # Rebuild pk_index incrementally (paths have changed)
        if not args.dry_run and not result['errors']:
            pk_index = build_pk_index(root)

    # ── Save NML ──────────────────────────────────────────────────────────────
    processed = [r for r in results if not r['errors']]
    if not args.dry_run and processed:
        save_nml(tree, nml_path)
        print(f"\n  ✅ Saved {nml_path}")
    elif args.dry_run:
        print(f"\n  [DRY RUN] NML not written")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_playlists = sum(r['playlists_moved'] for r in processed)
    total_cues      = sum(len(r['cues_added']) for r in processed)
    errors          = [r for r in results if r['errors']]

    print(f"\n{'='*70}")
    print(f"  Merged:           {len(processed)} pairs")
    print(f"  Skipped:          {skipped}")
    print(f"  Errors:           {len(errors)}")
    print(f"  Playlists moved:  {total_playlists}")
    print(f"  Cues merged:      {total_cues}")
    if args.delete:
        deleted = sum(1 for r in processed if r.get('file_deleted'))
        print(f"  Files deleted:    {deleted}")
    print(f"{'='*70}\n")

    if errors:
        print("Errors:")
        for r in errors:
            print(f"  {r['remove']}: {r['errors']}")

if __name__ == '__main__':
    main()
