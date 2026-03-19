#!/usr/bin/env python3.11
"""
find_duplicates.py
==================
Detects duplicate tracks in your library using acoustic fingerprinting (Chromaprint).

Detection methods
-----------------
  1. Exact fingerprint   — same recording, different files (clear duplicate)
  2. Near fingerprint    — same recording, different encode/format (e.g. WAV + MP3)
  3. Metadata match      — same Title + Artist, different file (possibly different version)

Fingerprints are cached in fingerprints.db so the slow scan only runs once.
Subsequent runs are instant.

Usage
-----
  # First run: fingerprint everything (~5 min), then show duplicates
  python3.11 find_duplicates.py

  # Re-run report instantly (uses cache)
  python3.11 find_duplicates.py --report-only

  # Fingerprint only, no report
  python3.11 find_duplicates.py --scan-only

  # Adjust near-match sensitivity (default 0.85)
  python3.11 find_duplicates.py --similarity 0.90

  # Only show exact duplicates
  python3.11 find_duplicates.py --exact-only

  # Save report to file
  python3.11 find_duplicates.py --out duplicates.txt

  # Scan only specific folder
  python3.11 find_duplicates.py --folder "/Volumes/Extreme SSD/music"

Requirements
------------
  fpcalc (brew install chromaprint), numpy, tqdm, sqlcipher3
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from tqdm import tqdm
import sqlcipher3

# ── Config ──────────────────────────────────────────────────────────────────────
MASTER_DB    = Path.home() / "Library/Pioneer/rekordbox/master.db"
MASTER_KEY   = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
CACHE_DB     = Path(__file__).parent / "fingerprints.db"
FPCALC       = "fpcalc"
MAX_WORKERS  = 8
# fpcalc analyses first N seconds (120 is plenty for uniqueness)
FPCALC_SECS  = 120
SIMILARITY_THRESHOLD = 0.85   # fraction of matching 32-bit integers

# File quality ranking for "keep" recommendation (higher = better)
FORMAT_RANK = {
    4: 5,   # FLAC
    5: 4,   # WAV
    11: 3,  # AIFF
    1: 2,   # MP3
    3: 1,   # AAC
}

# ── Fingerprint cache DB ────────────────────────────────────────────────────────
def open_cache() -> sqlite3.Connection:
    con = sqlite3.connect(str(CACHE_DB))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS fingerprints (
            path        TEXT PRIMARY KEY,
            duration    INTEGER,
            fp_raw      TEXT,        -- JSON array of 32-bit ints
            fp_str      TEXT,        -- base64 fingerprint string
            file_size   INTEGER,
            mtime       REAL,
            error       TEXT
        );
        CREATE TABLE IF NOT EXISTS scan_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    return con

def get_cached_paths(cache: sqlite3.Connection) -> dict:
    """Return {path: mtime} for all already-cached entries (including errors)."""
    return {r[0]: r[1] for r in
            cache.execute("SELECT path, mtime FROM fingerprints").fetchall()}

# ── Fingerprint one file ────────────────────────────────────────────────────────
def fingerprint_file(path: str) -> dict:
    try:
        stat = os.stat(path)
        result = subprocess.run(
            [FPCALC, '-raw', '-length', str(FPCALC_SECS), path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return {'path': path, 'error': result.stderr.strip(),
                    'file_size': stat.st_size, 'mtime': stat.st_mtime}

        data = {}
        for line in result.stdout.strip().splitlines():
            key, _, val = line.partition('=')
            data[key] = val

        # Also get the base64 fingerprint string
        result2 = subprocess.run(
            [FPCALC, '-length', str(FPCALC_SECS), path],
            capture_output=True, text=True, timeout=60
        )
        fp_str = ''
        for line in result2.stdout.strip().splitlines():
            if line.startswith('FINGERPRINT='):
                fp_str = line.split('=', 1)[1]

        raw_ints = [int(x) for x in data.get('FINGERPRINT', '').split(',') if x]
        return {
            'path':      path,
            'duration':  int(data.get('DURATION', 0)),
            'fp_raw':    json.dumps(raw_ints),
            'fp_str':    fp_str,
            'file_size': stat.st_size,
            'mtime':     stat.st_mtime,
            'error':     None,
        }
    except subprocess.TimeoutExpired:
        return {'path': path, 'error': 'timeout', 'file_size': 0, 'mtime': 0}
    except Exception as e:
        return {'path': path, 'error': str(e), 'file_size': 0, 'mtime': 0}

# ── Scan library ────────────────────────────────────────────────────────────────
def load_tracks_from_master(folder_filter: str | None) -> list[dict]:
    """Load all user tracks from master.db."""
    con = sqlcipher3.connect(str(MASTER_DB))
    con.execute(f"PRAGMA key='{MASTER_KEY}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")
    rows = con.execute("""
        SELECT c.ID, c.FolderPath, c.FileNameL, c.Title, c.BPM, c.Length,
               c.FileType, c.BitRate, c.SampleRate, a.Name
        FROM djmdContent c
        LEFT JOIN djmdArtist a ON c.ArtistID = a.ID
        WHERE c.FolderPath IS NOT NULL
          AND c.FolderPath NOT LIKE '%Sampler%'
          AND c.FolderPath NOT LIKE '%OSC_SAMPLER%'
          AND c.FolderPath NOT LIKE '%Demo Track%'
    """).fetchall()
    con.close()

    tracks = []
    for r in rows:
        path = r[1]
        if not path or not os.path.exists(path):
            continue
        if folder_filter and folder_filter not in path:
            continue
        tracks.append({
            'id':       str(r[0]),
            'path':     path,
            'filename': r[2],
            'title':    (r[3] or '').strip(),
            'bpm':      r[4],
            'length':   r[5],
            'filetype': r[6],
            'bitrate':  r[7],
            'artist':   (r[9] or '').strip(),
        })
    return tracks

def run_scan(tracks: list[dict], cache: sqlite3.Connection, force: bool = False):
    """Fingerprint all tracks, updating the cache. Skips already-cached unchanged files."""
    cached = get_cached_paths(cache)

    to_scan = []
    for t in tracks:
        path = t['path']
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        # Skip if cached and file hasn't changed
        if not force and path in cached and cached[path] == mtime:
            continue
        to_scan.append(path)

    if not to_scan:
        print(f"  ✅ All {len(tracks)} tracks already fingerprinted (cache hit)")
        return

    print(f"  Fingerprinting {len(to_scan)} tracks ({len(tracks)-len(to_scan)} cached)…")
    print(f"  Workers: {MAX_WORKERS}  |  Estimated time: ~{len(to_scan)//MAX_WORKERS//5} min")

    batch = []
    def flush_batch():
        if batch:
            cache.executemany("""
                INSERT OR REPLACE INTO fingerprints
                    (path, duration, fp_raw, fp_str, file_size, mtime, error)
                VALUES (:path, :duration, :fp_raw, :fp_str, :file_size, :mtime, :error)
            """, [
                {
                    'path':      r['path'],
                    'duration':  r.get('duration', 0),
                    'fp_raw':    r.get('fp_raw', '[]'),
                    'fp_str':    r.get('fp_str', ''),
                    'file_size': r.get('file_size', 0),
                    'mtime':     r.get('mtime', 0),
                    'error':     r.get('error'),
                }
                for r in batch
            ])
            cache.commit()
            batch.clear()

    errors = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fingerprint_file, p): p for p in to_scan}
        with tqdm(total=len(to_scan), unit='track', ncols=80) as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result.get('error'):
                    errors += 1
                batch.append(result)
                if len(batch) >= 50:
                    flush_batch()
                pbar.update(1)
    flush_batch()

    print(f"  ✅ Done. {errors} errors.")

# ── Similarity helpers ──────────────────────────────────────────────────────────
def fp_similarity(a: list[int], b: list[int]) -> float:
    """
    Fraction of matching 32-bit integers between two fingerprints.
    Aligns to the shorter fingerprint to handle different track lengths.
    """
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    arr_a = np.array(a[:min_len], dtype=np.uint32)
    arr_b = np.array(b[:min_len], dtype=np.uint32)
    # Count positions where XOR has ≤ 4 bits set (very close match)
    xor = np.bitwise_xor(arr_a, arr_b)
    bit_errors = np.unpackbits(xor.view(np.uint8)).reshape(-1, 32).sum(axis=1)
    return float(np.mean(bit_errors <= 4))

# ── Duplicate detection ─────────────────────────────────────────────────────────
def find_duplicates(tracks: list[dict], cache: sqlite3.Connection,
                    similarity_threshold: float, exact_only: bool) -> dict:
    """
    Returns:
        {
          'exact':    [ [track_info, ...], ... ],   # same fingerprint
          'near':     [ [track_info, ...], ... ],   # similar fingerprint
          'metadata': [ [track_info, ...], ... ],   # same title+artist
        }
    """
    # Build lookup: path → fingerprint data (include mtime for age ranking)
    fp_data = {
        r[0]: {'duration': r[1], 'fp_raw': json.loads(r[2] or '[]'),
                'fp_str': r[3], 'file_size': r[4], 'mtime': r[5]}
        for r in cache.execute(
            "SELECT path, duration, fp_raw, fp_str, file_size, mtime FROM fingerprints "
            "WHERE error IS NULL"
        ).fetchall()
    }

    # Enrich tracks with fingerprint data
    enriched = []
    for t in tracks:
        fp = fp_data.get(t['path'])
        if fp:
            enriched.append({**t, **fp})

    print(f"\n  Analysing {len(enriched)} fingerprinted tracks…")

    # ── 1. Exact fingerprint duplicates ─────────────────────────────────────
    from collections import defaultdict
    exact_groups = defaultdict(list)
    for t in enriched:
        if t['fp_str']:
            exact_groups[t['fp_str']].append(t)

    # Separate real file duplicates (different paths) from DB artifacts (same path indexed twice)
    exact_dupes = []
    db_artifacts = []   # same file path, multiple DB entries — reported separately
    for group in exact_groups.values():
        if len(group) < 2:
            continue
        unique_paths = {t['path'] for t in group}
        if len(unique_paths) == 1:
            db_artifacts.append(group)  # same physical file, double-indexed
        else:
            exact_dupes.append(group)

    # ── 2. Metadata duplicates (same title + artist) ─────────────────────
    meta_groups = defaultdict(list)
    for t in enriched:
        if t['title'] and t['artist']:
            key = (t['title'].lower(), t['artist'].lower())
            meta_groups[key].append(t)
    meta_dupes = [g for g in meta_groups.values() if len(g) > 1]
    # Remove exact duplicates already caught above (avoid double-reporting)
    exact_paths_sets = [{t['path'] for t in g} for g in exact_dupes]
    meta_dupes = [
        g for g in meta_dupes
        if not any({t['path'] for t in g} == s for s in exact_paths_sets)
    ]

    if exact_only:
        return {'exact': exact_dupes, 'near': [], 'metadata': meta_dupes}

    # ── 3. Near fingerprint duplicates ────────────────────────────────────
    # Group by similar duration first to reduce comparisons
    # Duration bucket: round to nearest 10 seconds
    duration_buckets = defaultdict(list)
    for t in enriched:
        dur = t['duration']
        # Check a few nearby buckets to catch minor duration differences
        bucket = (dur // 10) * 10
        duration_buckets[bucket].append(t)

    already_matched = set()  # paths already in an exact group
    for g in exact_dupes:
        for t in g:
            already_matched.add(t['path'])

    near_groups_map = {}  # path → group_id
    near_groups = []

    print("  Computing near-match fingerprint similarities…")
    # Only compare within duration buckets (±10s)
    checked = 0
    for bucket, bucket_tracks in tqdm(duration_buckets.items(), ncols=80, unit='bucket'):
        # Include adjacent bucket tracks for ±10s tolerance
        nearby = (
            bucket_tracks +
            duration_buckets.get(bucket - 10, []) +
            duration_buckets.get(bucket + 10, [])
        )
        # Remove exact dupes
        nearby = [t for t in nearby if t['path'] not in already_matched]
        # Deduplicate list (tracks appear in multiple buckets)
        seen_paths = set()
        unique_nearby = []
        for t in nearby:
            if t['path'] not in seen_paths:
                seen_paths.add(t['path'])
                unique_nearby.append(t)
        nearby = unique_nearby

        for i, a in enumerate(nearby):
            for b in nearby[i+1:]:
                if a['path'] == b['path']:
                    continue
                checked += 1
                sim = fp_similarity(a['fp_raw'], b['fp_raw'])
                if sim >= similarity_threshold:
                    # Merge into same group
                    ga = near_groups_map.get(a['path'])
                    gb = near_groups_map.get(b['path'])
                    if ga is None and gb is None:
                        gid = len(near_groups)
                        near_groups.append([a, b])
                        near_groups_map[a['path']] = gid
                        near_groups_map[b['path']] = gid
                    elif ga is None:
                        near_groups[gb].append(a)
                        near_groups_map[a['path']] = gb
                    elif gb is None:
                        near_groups[ga].append(b)
                        near_groups_map[b['path']] = ga
                    # if both already in groups: skip (could merge but rare edge case)

    # Remove near-matches that are already in exact groups
    near_dupes = [g for g in near_groups if len(g) > 1]

    return {'exact': exact_dupes, 'near': near_dupes, 'metadata': meta_dupes,
            'db_artifacts': db_artifacts}

# ── Report formatting ───────────────────────────────────────────────────────────
FILE_TYPES = {1: 'MP3', 3: 'AAC', 4: 'FLAC', 5: 'WAV', 11: 'AIFF'}

def format_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"

def format_duration(secs: int) -> str:
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"

def rank_track(t: dict) -> tuple:
    """Higher score = better quality to keep.
    Tiebreaker: older mtime wins (more likely to have cues/history accumulated)."""
    mtime = t.get('mtime', 0) or 0
    return (FORMAT_RANK.get(t.get('filetype', 0), 0), t.get('file_size', 0), -mtime)

def format_group(tracks: list[dict], idx: int, group_type: str) -> list[str]:
    lines = [f"\n  [{group_type} #{idx+1}]"]
    sorted_tracks = sorted(tracks, key=rank_track, reverse=True)
    for i, t in enumerate(sorted_tracks):
        tag    = "  ✅ KEEP   " if i == 0 else "  ❌ REMOVE "
        # Prefer extension from path over DB FileType (more reliable)
        ext = Path(t['path']).suffix.lstrip('.').upper()
        fmt = ext if ext in ('MP3','FLAC','WAV','AIFF','AAC','OGG','M4A') \
              else FILE_TYPES.get(t.get('filetype'), f"type{t.get('filetype')}")
        size   = format_size(t.get('file_size', 0))
        dur    = format_duration(t.get('duration', t.get('length', 0) // 1000))
        br     = f"{t.get('bitrate', 0)} kbps" if t.get('bitrate') else ""
        artist = t.get('artist', '')
        title  = t.get('title', t.get('filename', ''))
        lines.append(f"  {tag}  {fmt:<5} {size:>10}  {dur}  {br:<10}  {artist} – {title}")
        lines.append(f"             {t['path']}")
    return lines

def build_report(dupes: dict, similarity_threshold: float) -> str:
    lines = [
        "=" * 78,
        "  DUPLICATE TRACK REPORT",
        "=" * 78,
        f"  Similarity threshold: {similarity_threshold:.0%}",
        "",
    ]

    exact  = dupes['exact']
    near   = dupes['near']
    meta   = dupes['metadata']
    artifacts = dupes.get('db_artifacts', [])

    # Summary
    total_removable = sum(len(g) - 1 for g in exact + near)
    lines += [
        f"  Exact duplicates (same recording):  {len(exact)} groups",
        f"  Near duplicates  (same song, diff format/encode): {len(near)} groups",
        f"  Metadata matches (same title+artist, diff file):  {len(meta)} groups",
        f"  DB artifacts     (same file path, double-indexed): {len(artifacts)} groups",
        f"",
        f"  Suggested removals: {total_removable} files",
        "=" * 78,
    ]

    if exact:
        lines.append(f"\n{'─'*78}")
        lines.append(f"  EXACT DUPLICATES ({len(exact)} groups)")
        lines.append(f"  Same recording — safe to remove the lower-quality file")
        lines.append(f"{'─'*78}")
        for i, group in enumerate(exact):
            lines.extend(format_group(group, i, 'EXACT'))

    if near:
        lines.append(f"\n{'─'*78}")
        lines.append(f"  NEAR DUPLICATES ({len(near)} groups, similarity ≥ {similarity_threshold:.0%})")
        lines.append(f"  Same recording, different encode/format — verify before removing")
        lines.append(f"{'─'*78}")
        for i, group in enumerate(near):
            lines.extend(format_group(group, i, 'NEAR'))

    if meta:
        lines.append(f"\n{'─'*78}")
        lines.append(f"  METADATA MATCHES ({len(meta)} groups)")
        lines.append(f"  Same Title + Artist — may be different versions (radio/extended)")
        lines.append(f"  Review manually before removing anything")
        lines.append(f"{'─'*78}")
        for i, group in enumerate(meta):
            lines.extend(format_group(group, i, 'META'))

    if artifacts:
        lines.append(f"\n{'─'*78}")
        lines.append(f"  DB ARTIFACTS ({len(artifacts)} groups)")
        lines.append(f"  Same file indexed multiple times in Rekordbox — run cleanup_rekordbox_db.py")
        lines.append(f"{'─'*78}")
        for group in artifacts:
            path = group[0]['path']
            ids  = [str(t.get('rb_id', '?')) for t in group]
            lines.append(f"  {path}")
            lines.append(f"    → Rekordbox IDs: {', '.join(ids)}  (safe to deduplicate via DB cleanup)")

    lines.append("\n" + "=" * 78)
    return "\n".join(lines)

# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--report-only', action='store_true',
                    help='Skip scanning, use existing cache only')
    ap.add_argument('--scan-only',   action='store_true',
                    help='Fingerprint tracks, do not generate report')
    ap.add_argument('--force',       action='store_true',
                    help='Re-fingerprint all tracks even if cached')
    ap.add_argument('--similarity',  type=float, default=SIMILARITY_THRESHOLD,
                    help=f'Near-match threshold 0-1 (default: {SIMILARITY_THRESHOLD})')
    ap.add_argument('--exact-only',  action='store_true',
                    help='Only report exact fingerprint duplicates')
    ap.add_argument('--folder',      metavar='PATH',
                    help='Only scan tracks under this folder path')
    ap.add_argument('--out',         metavar='FILE',
                    help='Save report to this file')
    args = ap.parse_args()

    print(f"\n{'='*78}")
    print(f"  find_duplicates.py  —  Acoustic fingerprint duplicate detector")
    print(f"  Cache: {CACHE_DB}")
    print(f"{'='*78}\n")

    cache = open_cache()
    tracks = load_tracks_from_master(args.folder)
    print(f"  Found {len(tracks)} user tracks on disk")

    if not args.report_only:
        run_scan(tracks, cache, force=args.force)

    if args.scan_only:
        print("\n  Scan complete. Run without --scan-only to generate the report.")
        cache.close()
        return

    dupes = find_duplicates(tracks, cache, args.similarity, args.exact_only)
    cache.close()

    report = build_report(dupes, args.similarity)
    print(report)

    if args.out:
        Path(args.out).write_text(report, encoding='utf-8')
        print(f"\n  Report saved to: {args.out}")

    # Final stats
    total_exact = sum(len(g) - 1 for g in dupes['exact'])
    total_near  = sum(len(g) - 1 for g in dupes['near'])
    print(f"\n  Suggested removals: {total_exact + total_near} files")
    print(f"  Run with --out report.txt to save\n")

if __name__ == '__main__':
    main()
