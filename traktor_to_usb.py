#!/usr/bin/env python3.11
"""
traktor_to_usb.py
=================
Exports Traktor playlists directly to a Pioneer USB drive (no Rekordbox needed).

Selection
---------
  --select          Interactive checkbox UI — pick folders/playlists to export
  --all             Export the entire library
  --playlists NAME  Export specific folder/playlist names

Sync modes (--mode)
-------------------
  update  (default)  Skip existing tracks, update changed metadata, delete only
                     tracks removed from master.db entirely. Always rebuilds
                     the playlist tree from the current selection.
  push               Additive only — copies selected playlists/tracks to USB,
                     never deletes anything, merges into existing playlist tree.
  mirror             USB exactly matches the selected playlists. Wipes + rebuilds
                     playlist tree, deletes tracks not in scope, cleans orphans.

Flags
-----
  --mode MODE       Sync mode: update, push, or mirror (default: update)
  --sync            [Deprecated] Alias for --mode update
  --usb PATH        USB mount point, e.g. /Volumes/MYUSB (auto-detected if omitted)
  --dry-run         Preview what would be written without touching anything

Examples
--------
  python3.11 traktor_to_usb.py --select --usb /Volumes/MYUSB
  python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB --mode update
  python3.11 traktor_to_usb.py --playlists "03 - Events" --usb /Volumes/MYUSB --mode push
  python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB --mode mirror --dry-run
  python3.11 traktor_to_usb.py --select --dry-run

What it writes
--------------
  /PIONEER/rekordbox/exportLibrary.db       CDJ-3000 / XDJ-RX3 / XDJ-XZ
  /PIONEER/rekordbox/masterPlaylists6.xml   playlist display manifest
  /PIONEER/USBANLZ/…/ANLZ0000.DAT/.EXT     waveforms, beat grids, cue points
  /Contents/<Artist>/<track>               audio files

Sync state
----------
  A row is stored in exportLibrary.db djmdProperty (DBID='_sync_state') with
  the highest rb_local_usn seen from master.db at the time of last sync.
  On --sync, only records with rb_local_usn > that value are processed.

Requirements
------------
  python3.11, sqlcipher3, questionary
"""

import argparse, datetime, os, shutil, sys, time, uuid, zlib, atexit
from pathlib import Path

import sqlcipher3 as sqlite3

# ── Auto-save checkpoint handler ────────────────────────────────────────────
_checkpoint_callback = None
_last_save_time = 0
_dirty = False

def set_checkpoint_callback(cb):
    """Register a callback to be called at checkpoint (e.g., to save to disk)."""
    global _checkpoint_callback
    _checkpoint_callback = cb
    atexit.register(force_checkpoint)  # Ensure save on exit

def mark_dirty():
    """Mark that changes have been made."""
    global _dirty
    _dirty = True

def checkpoint(reason=""):
    """Save changes if dirty, with optional reason."""
    global _dirty, _last_save_time
    if _dirty and _checkpoint_callback:
        _checkpoint_callback(reason)
        _dirty = False
        _last_save_time = time.time()

def force_checkpoint():
    """Force a save regardless of dirty state (e.g., on exit)."""
    if _checkpoint_callback:
        _checkpoint_callback("Force save (exit)")

# ── Config ─────────────────────────────────────────────────────────────────────
MASTER_DB  = Path.home() / "Library/Pioneer/rekordbox/master.db"
KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
PIONEER_DIR = "PIONEER"
AUDIO_DIR   = "Contents"

# ── Helpers ────────────────────────────────────────────────────────────────────
def ts():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime('%Y-%m-%d %H:%M:%S.') + f'{now.microsecond//1000:03d} +00:00'

def now_ms():
    return int(time.time() * 1000)

def make_id(s):
    return zlib.crc32(s.encode('utf-8')) & 0xFFFFFFFF

def new_uuid():
    return str(uuid.uuid4())

def to_hex(n):
    return format(int(n), 'X').upper()

def open_db(path, key=KEY):
    con = sqlite3.connect(str(path))
    con.execute(f"PRAGMA key='{key}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")
    con.execute("PRAGMA foreign_keys=OFF")
    return con

# ── Auto-detect USB ────────────────────────────────────────────────────────────
def detect_pioneer_usbs():
    """Return list of mounted Pioneer USB paths."""
    candidates = []
    volumes = Path("/Volumes")
    if not volumes.exists():
        return candidates
    for vol in volumes.iterdir():
        pioneer = vol / PIONEER_DIR
        if pioneer.is_dir():
            candidates.append(vol)
    return sorted(candidates)

# ── Schema ─────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS djmdContent (
    ID VARCHAR(255) PRIMARY KEY, FolderPath VARCHAR(255), FileNameL VARCHAR(255),
    Title VARCHAR(255), ArtistID VARCHAR(255), BPM INTEGER, Length INTEGER,
    FileType INTEGER DEFAULT 1, BitRate INTEGER, SampleRate INTEGER,
    Commnt VARCHAR(255), Rating INTEGER DEFAULT 0, ColorID INTEGER DEFAULT 0,
    KeyID INTEGER, UUID VARCHAR(255),
    rb_data_status INTEGER DEFAULT 257,
    rb_local_data_status INTEGER DEFAULT 0, rb_local_deleted TINYINT DEFAULT 0,
    rb_local_synced TINYINT DEFAULT 0, rb_local_usn BIGINT,
    created_at DATETIME, updated_at DATETIME
);
CREATE TABLE IF NOT EXISTS djmdArtist (
    ID VARCHAR(255) PRIMARY KEY, Name VARCHAR(255), UUID VARCHAR(255),
    rb_data_status INTEGER DEFAULT 0, rb_local_data_status INTEGER DEFAULT 0,
    rb_local_deleted TINYINT DEFAULT 0, rb_local_synced TINYINT DEFAULT 0,
    rb_local_usn BIGINT, created_at DATETIME, updated_at DATETIME
);
CREATE TABLE IF NOT EXISTS djmdPlaylist (
    ID VARCHAR(255) PRIMARY KEY, Seq INTEGER, Name VARCHAR(255),
    Attribute INTEGER DEFAULT 0, ParentID VARCHAR(255) DEFAULT 'root',
    SmartList TEXT, UUID VARCHAR(255),
    rb_data_status INTEGER DEFAULT 0, rb_local_data_status INTEGER DEFAULT 0,
    rb_local_deleted TINYINT DEFAULT 0, rb_local_synced TINYINT DEFAULT 0,
    rb_local_usn BIGINT, created_at DATETIME, updated_at DATETIME
);
CREATE TABLE IF NOT EXISTS djmdSongPlaylist (
    ID VARCHAR(255) PRIMARY KEY, PlaylistID VARCHAR(255), ContentID VARCHAR(255),
    TrackNo INTEGER, UUID VARCHAR(255),
    rb_data_status INTEGER DEFAULT 0, rb_local_data_status INTEGER DEFAULT 0,
    rb_local_deleted TINYINT DEFAULT 0, rb_local_synced TINYINT DEFAULT 0,
    rb_local_usn BIGINT, created_at DATETIME, updated_at DATETIME
);
CREATE TABLE IF NOT EXISTS djmdCue (
    ID VARCHAR(255) PRIMARY KEY, ContentID VARCHAR(255),
    InMsec INTEGER, InFrame INTEGER DEFAULT 0, InMpegFrame INTEGER DEFAULT 0,
    InMpegAbs INTEGER DEFAULT 0, OutMsec INTEGER DEFAULT -1,
    OutFrame INTEGER DEFAULT 0, OutMpegFrame INTEGER DEFAULT 0,
    OutMpegAbs INTEGER DEFAULT 0, Kind INTEGER DEFAULT 0,
    Color INTEGER DEFAULT -1, ColorTableIndex INTEGER DEFAULT -1,
    ActiveLoop INTEGER DEFAULT 0, Comment VARCHAR(255),
    BeatLoopSize INTEGER DEFAULT 0, CueMicrosec INTEGER DEFAULT 0,
    ContentUUID VARCHAR(255), UUID VARCHAR(255),
    rb_data_status INTEGER DEFAULT 0, rb_local_data_status INTEGER DEFAULT 0,
    rb_local_deleted TINYINT DEFAULT 0, rb_local_synced TINYINT DEFAULT 0,
    rb_local_usn BIGINT, created_at DATETIME, updated_at DATETIME
);
CREATE TABLE IF NOT EXISTS djmdKey (
    ID INTEGER PRIMARY KEY, ScaleName VARCHAR(255), Seq INTEGER
);
CREATE TABLE IF NOT EXISTS djmdColor (
    ID INTEGER PRIMARY KEY, ColorCode INTEGER, SortKey INTEGER, Name VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS djmdProperty (
    DBID VARCHAR(255) PRIMARY KEY, DeviceID VARCHAR(255), LocalPath VARCHAR(255),
    UUID VARCHAR(255), rb_local_usn BIGINT, created_at DATETIME, updated_at DATETIME
);
"""

def init_usb_db(usb_con, usb_path: Path):
    usb_con.executescript(SCHEMA_SQL)
    master = open_db(MASTER_DB)
    for k in master.execute("SELECT ID, ScaleName, Seq FROM djmdKey").fetchall():
        usb_con.execute("INSERT OR IGNORE INTO djmdKey VALUES (?,?,?)", k)
    for c in master.execute("SELECT ID, ColorCode, SortKey, Name FROM djmdColor").fetchall():
        usb_con.execute("INSERT OR IGNORE INTO djmdColor VALUES (?,?,?,?)", c)
    master.close()
    db_id  = str(make_id(str(usb_path)))
    dev_id = new_uuid()
    usb_con.execute(
        "INSERT OR IGNORE INTO djmdProperty VALUES (?,?,?,?,1,?,?)",
        (db_id, dev_id, '/', new_uuid(), ts(), ts()))
    usb_con.commit()

# ── Sync state helpers ─────────────────────────────────────────────────────────
SYNC_STATE_KEY = '_sync_state'

def get_last_sync_usn(usb_con) -> int:
    """Return the max rb_local_usn from the previous sync, or 0 if first sync."""
    r = usb_con.execute(
        "SELECT rb_local_usn FROM djmdProperty WHERE DBID=?",
        (SYNC_STATE_KEY,)
    ).fetchone()
    return int(r[0]) if r and r[0] is not None else 0

def save_sync_usn(usb_con, usn: int):
    usb_con.execute(
        "INSERT OR REPLACE INTO djmdProperty (DBID,DeviceID,LocalPath,UUID,rb_local_usn,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (SYNC_STATE_KEY, '', '', new_uuid(), usn, ts(), ts()))
    usb_con.commit()

# ── Playlist tree ──────────────────────────────────────────────────────────────
def get_playlist_tree(con):
    """Return dict: tuple-path → (id_str, attribute)"""
    def recurse(parent_id, prefix):
        out = {}
        for r in con.execute(
            "SELECT ID, Name, Attribute FROM djmdPlaylist WHERE ParentID=? ORDER BY Seq",
            (str(parent_id),)
        ).fetchall():
            path = prefix + (r[1],)
            out[path] = (str(r[0]), r[2])
            out.update(recurse(r[0], path))
        return out
    tree = {}
    for r in con.execute(
        "SELECT ID, Name, Attribute FROM djmdPlaylist WHERE ParentID='root' ORDER BY Seq"
    ).fetchall():
        path = (r[1],)
        tree[path] = (str(r[0]), r[2])
        tree.update(recurse(r[0], path))
    return tree

def collect_playlist_ids(tree, selected_roots):
    """Return set of playlist IDs under any of the selected root names."""
    selected = set()
    for path, (pl_id, attr) in tree.items():
        if attr == 0:
            if not selected_roots or any(seg in selected_roots for seg in path):
                selected.add(pl_id)
    return selected

# ── Interactive playlist selector ──────────────────────────────────────────────
def run_selector(tree) -> list:
    """
    Show a two-level checkbox menu:
      • Top-level folders shown as headers
      • Selecting a folder toggles all its children
      • Individual playlists can be checked independently
    Returns list of selected playlist IDs.
    """
    try:
        import questionary
        from questionary import Choice, Separator
    except ImportError:
        print("questionary not installed. Run: pip3.11 install questionary")
        sys.exit(1)

    # Build ordered list of choices
    choices = []
    # Gather top-level items
    top_level = [(path, info) for path, info in tree.items() if len(path) == 1]
    top_level.sort(key=lambda x: x[0])

    for (top_path, (top_id, top_attr)) in top_level:
        if top_attr == 1:  # folder
            # Count playlists inside
            children_playlists = [
                (path, pl_id) for path, (pl_id, attr) in tree.items()
                if attr == 0 and len(path) > 1 and path[0] == top_path[0]
            ]
            choices.append(Separator(f"\n── {top_path[0]} ({len(children_playlists)} playlists) ──"))
            # Add sub-folder and playlist entries
            for path, (pl_id, attr) in sorted(tree.items()):
                if attr == 0 and len(path) >= 2 and path[0] == top_path[0]:
                    indent = "  " * (len(path) - 1)
                    label = indent + " / ".join(path[1:])
                    choices.append(Choice(title=label, value=pl_id))
        else:  # root-level playlist
            choices.append(Choice(title=top_path[0], value=top_id))

    if not choices:
        print("No playlists found in library.")
        sys.exit(1)

    print("\n  Use SPACE to select, A to toggle all, ENTER to confirm\n")
    selected = questionary.checkbox(
        "Select playlists to export:",
        choices=choices,
        style=questionary.Style([
            ('qmark',         'fg:#00bcd4 bold'),
            ('question',      'bold'),
            ('answer',        'fg:#00bcd4 bold'),
            ('pointer',       'fg:#00bcd4 bold'),
            ('highlighted',   'fg:#00bcd4 bold'),
            ('selected',      'fg:#00bcd4'),
            ('separator',     'fg:#888888'),
            ('instruction',   'fg:#888888'),
        ])
    ).ask()

    if selected is None:
        print("Cancelled.")
        sys.exit(0)

    # Auto-save checkpoint: user made a playlist selection
    checkpoint("Playlist selection confirmed")
    return selected  # list of pl_id strings

# ── Core export ────────────────────────────────────────────────────────────────
MODE_LABELS = {'update': 'library update', 'push': 'selective push', 'mirror': 'mirror sync'}

def export_to_usb(usb_path: Path, playlist_ids: set, tree: dict, mode: str = 'update', dry_run: bool = False, fetch_nas: bool = False):
    usb_rb_dir  = usb_path / PIONEER_DIR / "rekordbox"
    usb_anlz    = usb_path / PIONEER_DIR / "USBANLZ"
    usb_audio   = usb_path / AUDIO_DIR
    usb_db_path = usb_rb_dir / "exportLibrary.db"

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Exporting to: {usb_path}")
    print(f"  Mode: {MODE_LABELS.get(mode, mode)}")
    print(f"  Playlists: {len(playlist_ids)}")

    # ── Open master.db ────────────────────────────────────────────────────────
    master = open_db(MASTER_DB)
    max_master_usn = master.execute("SELECT MAX(rb_local_usn) FROM djmdContent").fetchone()[0] or 0

    # ── Determine which content IDs to process ────────────────────────────────
    if playlist_ids:
        ph = ','.join('?' * len(playlist_ids))
        all_content_ids = set(
            r[0] for r in master.execute(
                f"SELECT DISTINCT ContentID FROM djmdSongPlaylist WHERE PlaylistID IN ({ph})",
                list(playlist_ids)
            ).fetchall()
        )
    else:
        all_content_ids = set(
            r[0] for r in master.execute("SELECT ID FROM djmdContent").fetchall()
        )
    print(f"  Total tracks in scope: {len(all_content_ids)}")

    # ── Determine existing USB state ─────────────────────────────────────────
    existing_ids = set()
    last_usn = 0
    if usb_db_path.exists():
        usb_con_check = open_db(usb_db_path)
        last_usn = get_last_sync_usn(usb_con_check)
        existing_ids = set(
            r[0] for r in usb_con_check.execute("SELECT ID FROM djmdContent").fetchall()
        )
        usb_con_check.close()
        print(f"  Last sync USN: {last_usn}  →  master USN: {max_master_usn}")

    # ── Compute tracks to process and deletions based on mode ────────────────
    changed_ids = set()

    if mode == 'update':
        # New tracks: in scope but not yet on USB
        new_ids = all_content_ids - existing_ids
        # Changed tracks: already on USB but updated since last sync
        if last_usn > 0:
            changed_ids = {r[0] for r in master.execute(
                "SELECT ID FROM djmdContent WHERE rb_local_usn > ?", (last_usn,)
            ).fetchall()} & existing_ids
        # Delete only tracks completely gone from master.db
        all_master_ids = set(r[0] for r in master.execute(
            "SELECT ID FROM djmdContent"
        ).fetchall())
        deleted_ids = existing_ids - all_master_ids
        tracks_to_process = new_ids | changed_ids
        print(f"  New: {len(new_ids)}  Changed: {len(changed_ids)}  Deleted: {len(deleted_ids)}")

    elif mode == 'push':
        # Only add tracks not already on USB — never delete
        tracks_to_process = all_content_ids - existing_ids
        deleted_ids = set()
        print(f"  New: {len(tracks_to_process)}  (push mode — no deletions)")

    elif mode == 'mirror':
        # New tracks: in scope but not on USB
        new_ids = all_content_ids - existing_ids
        # Changed tracks: on USB and updated since last sync, within scope
        if last_usn > 0:
            changed_ids = {r[0] for r in master.execute(
                "SELECT ID FROM djmdContent WHERE rb_local_usn > ?", (last_usn,)
            ).fetchall()} & all_content_ids
        # Delete tracks no longer in scope
        deleted_ids = existing_ids - all_content_ids
        tracks_to_process = new_ids | changed_ids
        print(f"  New: {len(new_ids)}  Changed: {len(changed_ids)}  Deleted: {len(deleted_ids)}")

    # ── Load track metadata ────────────────────────────────────────────────────
    tracks = {}
    if tracks_to_process:
        ph2 = ','.join('?' * len(tracks_to_process))
        for r in master.execute(f"""
            SELECT c.ID, c.FolderPath, c.FileNameL, c.Title, c.BPM, c.Length,
                   c.FileType, c.BitRate, c.SampleRate, c.Commnt, c.Rating,
                   c.ColorID, c.KeyID, c.UUID, a.Name
            FROM djmdContent c
            LEFT JOIN djmdArtist a ON c.ArtistID = a.ID
            WHERE c.ID IN ({ph2})
        """, list(tracks_to_process)).fetchall():
            tracks[r[0]] = r

    # ANLZ mapping for tracks to process
    anlz_map = {}
    if tracks_to_process:
        for r in master.execute(
            f"SELECT ContentID, Path, rb_local_path FROM contentFile WHERE ContentID IN ({ph2})",
            list(tracks_to_process)
        ).fetchall():
            anlz_map.setdefault(r[0], []).append((r[1], r[2]))

    # Cue points for tracks to process
    cues = {}
    if tracks_to_process:
        for r in master.execute(
            f"SELECT * FROM djmdCue WHERE ContentID IN ({ph2})",
            list(tracks_to_process)
        ).fetchall():
            cues.setdefault(r[1], []).append(r)

    master.close()

    # ── NAS lookup for missing tracks ──────────────────────────────────────────
    nas_available = {}
    if fetch_nas:
        try:
            from nas_lookup import lookup_nas_tracks, check_traktor_ml_reachable, TRAKTOR_ML_API
            # Collect paths of all tracks to check which are missing locally
            missing_paths = []
            for cid, row in tracks.items():
                folder_path = row[1]
                if folder_path and not Path(folder_path).exists():
                    missing_paths.append(folder_path)
            if missing_paths:
                nas_available = lookup_nas_tracks(missing_paths)
                nas_reachable = check_traktor_ml_reachable()
                if nas_available and not nas_reachable:
                    print(f"  ⚠️  {len(nas_available)} tracks found on NAS but traktor-ml API is unreachable")
                    print(f"      Start the server and SSH tunnel to fetch them")
                    nas_available = {}
                elif nas_available:
                    total_size = sum(t.size_bytes for t in nas_available.values())
                    print(f"  🌐 NAS: {len(nas_available)} tracks available ({total_size / 1_048_576:.0f} MB)")
        except ImportError:
            print("  ⚠️  nas_lookup.py not found — --fetch-nas disabled")
            fetch_nas = False

    if dry_run:
        # Count local vs NAS vs truly missing
        local_count = 0
        nas_count = len(nas_available)
        truly_missing = 0
        for cid, row in tracks.items():
            folder_path = row[1]
            if folder_path and Path(folder_path).exists():
                local_count += 1
            elif folder_path and folder_path in nas_available:
                pass  # already counted in nas_count
            else:
                truly_missing += 1

        print(f"\n  Would copy {local_count} local audio files")
        if fetch_nas and nas_count > 0:
            total_nas_size = sum(t.size_bytes for t in nas_available.values())
            print(f"  Would fetch {nas_count} tracks from NAS ({total_nas_size / 1_048_576:.0f} MB)")
        if truly_missing > 0:
            print(f"  ⚠️  {truly_missing} tracks unavailable (not local or NAS)")
        print(f"  Would copy {sum(len(v) for v in anlz_map.values())} ANLZ files")
        if deleted_ids:
            print(f"  Would remove {len(deleted_ids)} deleted tracks from DB")
        if mode == 'push':
            print(f"  Would merge {len(playlist_ids)} playlists into existing tree (push — no wipe)")
        elif mode == 'mirror':
            print(f"  Would rebuild playlist tree ({len(playlist_ids)} playlists, mirror — exact match)")
            print(f"  Would clean up orphaned tracks not in any playlist")
        else:
            print(f"  Would rebuild playlist tree ({len(playlist_ids)} playlists)")
        return

    # ── Prepare directories + DB ───────────────────────────────────────────────
    for d in [usb_rb_dir, usb_anlz, usb_audio]:
        d.mkdir(parents=True, exist_ok=True)

    is_fresh = not usb_db_path.exists()
    usb_con = open_db(usb_db_path)
    if is_fresh:
        init_usb_db(usb_con, usb_path)

    usn = 1  # USN to stamp all our writes with

    # ── Artist cache ──────────────────────────────────────────────────────────
    artist_cache = {}
    def get_or_insert_artist(name):
        if not name:
            return None
        if name in artist_cache:
            return artist_cache[name]
        aid = str(make_id(f"artist:{name}"))
        usb_con.execute("""INSERT OR IGNORE INTO djmdArtist
            (ID,Name,UUID,rb_data_status,rb_local_data_status,rb_local_deleted,
             rb_local_synced,rb_local_usn,created_at,updated_at)
            VALUES (?,?,?,0,0,0,0,?,?,?)""",
            (aid, name, new_uuid(), usn, ts(), ts()))
        artist_cache[name] = aid
        return aid

    # ── Remove deleted tracks ─────────────────────────────────────────────────
    if deleted_ids:
        ph_del = ','.join('?' * len(deleted_ids))
        usb_con.execute(f"DELETE FROM djmdSongPlaylist WHERE ContentID IN ({ph_del})", list(deleted_ids))
        usb_con.execute(f"DELETE FROM djmdCue WHERE ContentID IN ({ph_del})", list(deleted_ids))
        usb_con.execute(f"DELETE FROM djmdContent WHERE ID IN ({ph_del})", list(deleted_ids))
        print(f"  🗑  Removed {len(deleted_ids)} deleted tracks")

    # ── Copy audio + ANLZ, insert into DB ─────────────────────────────────────
    copied_audio = 0
    skipped_audio = 0
    copied_anlz  = 0
    missing_audio = []
    fetched_from_nas = 0
    nas_fetch_failed = 0

    total = len(tracks)
    for i, (cid, row) in enumerate(tracks.items(), 1):
        if i % 200 == 0 or i == total:
            print(f"  [{i}/{total}] Processing tracks…", end='\r')

        (db_id, folder_path, filename, title, bpm, length, ftype,
         bitrate, samplerate, comment, rating, color_id, key_id, track_uuid, artist_name) = row

        # Audio
        artist_slug = (artist_name or 'Unknown').replace('/', '_').replace(':', '_')[:50]
        src_audio = Path(folder_path) if folder_path else None
        got_audio = False

        if src_audio and src_audio.exists():
            # File exists locally — copy to USB
            dst_dir = usb_audio / artist_slug
            dst_dir.mkdir(exist_ok=True)
            dst_audio = dst_dir / filename
            if not dst_audio.exists():
                shutil.copy2(src_audio, dst_audio)
                copied_audio += 1
            else:
                skipped_audio += 1
            got_audio = True

        elif fetch_nas and folder_path and folder_path in nas_available:
            # File missing locally but available on NAS — download to USB
            from nas_lookup import download_from_nas, TRAKTOR_ML_API
            dst_dir = usb_audio / artist_slug
            dst_dir.mkdir(exist_ok=True)
            dst_audio = dst_dir / filename
            if dst_audio.exists():
                skipped_audio += 1
                got_audio = True
            else:
                nas_info = nas_available[folder_path]
                if download_from_nas(folder_path, dst_audio, TRAKTOR_ML_API, nas_info.file_hash):
                    fetched_from_nas += 1
                    got_audio = True
                else:
                    nas_fetch_failed += 1

        if not got_audio:
            if cid in existing_ids:
                # Track already on USB — keep its audio, just update DB entry
                usb_audio_rel = f"/{AUDIO_DIR}/{artist_slug}/{filename}"
                skipped_audio += 1
            else:
                # Track is genuinely missing — skip entirely
                if folder_path:
                    missing_audio.append(folder_path)
                continue

        else:
            usb_audio_rel = f"/{AUDIO_DIR}/{artist_slug}/{filename}"

        # ANLZ
        for (usb_anlz_path, local_anlz_path) in anlz_map.get(cid, []):
            if not local_anlz_path:
                continue
            src = Path(local_anlz_path)
            if not src.exists():
                continue
            rel_parts = Path(usb_anlz_path.lstrip('/')).parts
            if len(rel_parts) >= 3 and rel_parts[0] == 'PIONEER' and rel_parts[1] == 'USBANLZ':
                dst_anlz = usb_path / PIONEER_DIR / 'USBANLZ' / Path(*rel_parts[2:])
            else:
                dst_anlz = usb_anlz / Path(usb_anlz_path.lstrip('/'))
            dst_anlz.parent.mkdir(parents=True, exist_ok=True)
            if not dst_anlz.exists():
                shutil.copy2(src, dst_anlz)
                copied_anlz += 1

        # DB: content
        artist_id = get_or_insert_artist(artist_name)
        usb_con.execute("""INSERT OR REPLACE INTO djmdContent (
            ID,FolderPath,FileNameL,Title,ArtistID,BPM,Length,
            FileType,BitRate,SampleRate,Commnt,Rating,ColorID,KeyID,
            UUID,rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
            rb_local_usn,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,257,0,0,0,?,?,?)""",
            (str(db_id), usb_audio_rel, filename, title or filename,
             artist_id, bpm, length, ftype, bitrate, samplerate,
             comment, rating, color_id, key_id,
             track_uuid or new_uuid(), usn, ts(), ts()))

        # DB: cues (replace on sync to pick up changes)
        usb_con.execute(f"DELETE FROM djmdCue WHERE ContentID=?", (str(db_id),))
        for cue in cues.get(cid, []):
            usb_con.execute("""INSERT OR IGNORE INTO djmdCue (
                ID,ContentID,InMsec,InFrame,InMpegFrame,InMpegAbs,
                OutMsec,OutFrame,OutMpegFrame,OutMpegAbs,Kind,Color,
                ColorTableIndex,ActiveLoop,Comment,BeatLoopSize,CueMicrosec,
                ContentUUID,UUID,rb_data_status,rb_local_data_status,
                rb_local_deleted,rb_local_synced,rb_local_usn,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,?,?,?)""",
                (cue[0], str(db_id), cue[2], cue[3], cue[4], cue[5],
                 cue[6], cue[7], cue[8], cue[9], cue[10], cue[11],
                 cue[12], cue[13], cue[14], cue[15], cue[16],
                 cue[17], cue[18], usn, ts(), ts()))

    print()  # newline after progress
    usb_con.commit()
    print(f"  ✅ Audio:  {copied_audio} local, {skipped_audio} already present, {len(missing_audio)} missing")
    if fetch_nas:
        print(f"  🌐 NAS:   {fetched_from_nas} fetched, {nas_fetch_failed} failed")
    print(f"  ✅ ANLZ:   {copied_anlz} new files")

    # ── Rebuild playlist structure ────────────────────────────────────────────
    if mode == 'push':
        # Push mode: merge into existing playlist tree (don't wipe)
        existing_playlist_ids = set(
            str(r[0]) for r in usb_con.execute("SELECT ID FROM djmdPlaylist").fetchall()
        )
        existing_song_keys = set(
            (str(r[0]), str(r[1])) for r in usb_con.execute(
                "SELECT PlaylistID, ContentID FROM djmdSongPlaylist"
            ).fetchall()
        )
    else:
        # Update / mirror: wipe and rebuild from scratch
        usb_con.execute("DELETE FROM djmdPlaylist")
        usb_con.execute("DELETE FROM djmdSongPlaylist")
        existing_playlist_ids = set()
        existing_song_keys = set()

    # Build ancestor paths for all selected playlists
    master = open_db(MASTER_DB)

    needed_paths = set()
    for path, (pl_id, attr) in tree.items():
        if attr == 0 and pl_id in playlist_ids:
            for i in range(1, len(path) + 1):
                needed_paths.add(path[:i])

    # Determine which content IDs are valid on USB for playlist links
    usb_valid_ids = set(
        str(r[0]) for r in usb_con.execute("SELECT ID FROM djmdContent").fetchall()
    )

    manifest_nodes = []
    pl_count = fold_count = link_count = 0
    sibling_seq = {}

    for path in sorted(needed_paths, key=lambda p: (len(p), p)):
        item = tree.get(path)
        if not item:
            continue
        pl_id, attr = item
        parent_path  = path[:-1]
        parent_db_id = tree.get(parent_path, ('root',))[0] if parent_path else 'root'

        seq_key = str(parent_db_id)
        seq = sibling_seq.get(seq_key, 0)
        sibling_seq[seq_key] = seq + 1

        manifest_nodes.append((int(pl_id), int(parent_db_id) if parent_db_id != 'root' else 0, attr))

        if mode == 'push' and str(pl_id) in existing_playlist_ids:
            # Push mode: playlist already exists — don't recreate, just add new tracks
            if attr == 0:
                pl_count += 1
                links = master.execute(
                    "SELECT ID, ContentID, TrackNo FROM djmdSongPlaylist WHERE PlaylistID=?",
                    (str(pl_id),)
                ).fetchall()
                for link in links:
                    if str(link[1]) in usb_valid_ids and (str(pl_id), str(link[1])) not in existing_song_keys:
                        usb_con.execute("""INSERT OR IGNORE INTO djmdSongPlaylist
                            (ID,PlaylistID,ContentID,TrackNo,UUID,
                             rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                             rb_local_usn,created_at,updated_at) VALUES (?,?,?,?,?,0,0,0,0,?,?,?)""",
                            (str(link[0]), str(pl_id), str(link[1]), link[2],
                             new_uuid(), usn, ts(), ts()))
                        link_count += 1
            else:
                fold_count += 1
        else:
            usb_con.execute("""INSERT OR REPLACE INTO djmdPlaylist
                (ID,Seq,Name,Attribute,ParentID,UUID,
                 rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                 rb_local_usn,created_at,updated_at) VALUES (?,?,?,?,?,?,0,0,0,0,?,?,?)""",
                (str(pl_id), seq, path[-1], attr,
                 str(parent_db_id) if parent_db_id != 'root' else 'root',
                 new_uuid(), usn, ts(), ts()))

            if attr == 0:
                pl_count += 1
                links = master.execute(
                    "SELECT ID, ContentID, TrackNo FROM djmdSongPlaylist WHERE PlaylistID=?",
                    (str(pl_id),)
                ).fetchall()
                for link in links:
                    if str(link[1]) in usb_valid_ids:
                        usb_con.execute("""INSERT OR IGNORE INTO djmdSongPlaylist
                            (ID,PlaylistID,ContentID,TrackNo,UUID,
                             rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                             rb_local_usn,created_at,updated_at) VALUES (?,?,?,?,?,0,0,0,0,?,?,?)""",
                            (str(link[0]), str(pl_id), str(link[1]), link[2],
                             new_uuid(), usn, ts(), ts()))
                        link_count += 1
            else:
                fold_count += 1

    master.close()
    usb_con.commit()
    checkpoint("Tracks & playlists committed to DB")
    print(f"  ✅ Playlists: {pl_count} playlists, {fold_count} folders, {link_count} links")

    # ── Mirror mode: orphan cleanup ───────────────────────────────────────────
    if mode == 'mirror':
        orphan_rows = usb_con.execute(
            "SELECT c.ID, c.FolderPath FROM djmdContent c WHERE NOT EXISTS "
            "(SELECT 1 FROM djmdSongPlaylist sp WHERE sp.ContentID = c.ID)"
        ).fetchall()
        if orphan_rows:
            orphan_ids = [r[0] for r in orphan_rows]
            orphan_paths = [r[1] for r in orphan_rows]
            ph_orph = ','.join('?' * len(orphan_ids))
            usb_con.execute(f"DELETE FROM djmdCue WHERE ContentID IN ({ph_orph})", orphan_ids)
            usb_con.execute(f"DELETE FROM djmdContent WHERE ID IN ({ph_orph})", orphan_ids)
            # Delete orphan audio files from USB
            for fpath in orphan_paths:
                if fpath:
                    audio_file = usb_path / fpath.lstrip('/')
                    if audio_file.exists():
                        audio_file.unlink()
            usb_con.commit()
            print(f"  🧹 Cleaned up {len(orphan_ids)} orphaned tracks")

        # Scan /Contents/ for audio files not in DB
        db_paths = set(
            r[0] for r in usb_con.execute("SELECT FolderPath FROM djmdContent").fetchall()
            if r[0]
        )
        audio_dir = usb_path / AUDIO_DIR
        if audio_dir.exists():
            stale_files = 0
            for audio_file in audio_dir.rglob('*'):
                if audio_file.is_file():
                    rel_path = '/' + str(audio_file.relative_to(usb_path))
                    if rel_path not in db_paths:
                        audio_file.unlink()
                        stale_files += 1
            # Clean up empty artist directories
            for d in audio_dir.iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            if stale_files:
                print(f"  🧹 Removed {stale_files} stale audio files from {AUDIO_DIR}/")

    # ── Push mode: rebuild manifest from USB DB to include all playlists ──────
    if mode == 'push':
        manifest_nodes = []
        for r in usb_con.execute(
            "SELECT ID, ParentID, Attribute FROM djmdPlaylist ORDER BY Seq"
        ).fetchall():
            parent_dec = 0 if str(r[1]) == 'root' else int(r[1])
            manifest_nodes.append((int(r[0]), parent_dec, r[2]))

    # ── masterPlaylists6.xml ───────────────────────────────────────────────────
    xml_manifest = usb_rb_dir / "masterPlaylists6.xml"
    ts_ms = now_ms()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '',
        '<MASTER_PLAYLIST Version="3.0.0" AutomaticSync="0">',
        '  <PRODUCT Name="rekordbox" Version="6.8.5" Company="Pioneer DJ"/>',
        '  <PLAYLISTS>',
    ]
    for (dec_id, parent_dec_id, attribute) in manifest_nodes:
        parent_hex = to_hex(parent_dec_id) if parent_dec_id != 0 else '0'
        lines.append(
            f'    <NODE Id="{to_hex(dec_id)}" ParentId="{parent_hex}" '
            f'Attribute="{attribute}" Timestamp="{ts_ms}" Lib_Type="0" CheckType="0"/>'
        )
    lines += ['  </PLAYLISTS>', '</MASTER_PLAYLIST>', '']
    xml_manifest.write_text('\n'.join(lines), encoding='utf-8')
    checkpoint("Playlist manifest written")

    # ── Save sync state ────────────────────────────────────────────────────────
    save_sync_usn(usb_con, max_master_usn)
    usb_con.close()
    checkpoint("Sync state saved, USB export complete")

    if missing_audio:
        print(f"\n  ⚠️  {len(missing_audio)} audio files not found locally:")
        for p in missing_audio[:5]:
            print(f"     {p}")
        if len(missing_audio) > 5:
            print(f"     … and {len(missing_audio)-5} more")

    print(f"\n  ✅ Done → {usb_path}")
    print(f"     exportLibrary.db : {usb_db_path}")
    print(f"     masterPlaylists6.xml : {xml_manifest}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument('--select',    action='store_true', help='Interactive UI to select playlists')
    scope.add_argument('--all',       action='store_true', help='Export entire library')
    scope.add_argument('--playlists', nargs='+', metavar='NAME',
                      help='Folder/playlist names to export')

    ap.add_argument('--usb',      metavar='PATH', help='USB mount point (auto-detected if omitted)')
    ap.add_argument('--mode',     choices=['update', 'push', 'mirror'], default=None,
                    help='Sync mode: update (skip existing, clean deleted), push (additive only), mirror (exact match)')
    ap.add_argument('--sync',     action='store_true',
                    help='[Deprecated] Alias for --mode update')
    ap.add_argument('--dry-run',  action='store_true', help='Preview without writing')
    ap.add_argument('--fetch-nas', action='store_true',
                    help='Fetch missing tracks from NAS via traktor-ml (requires server + SSH tunnel)')
    args = ap.parse_args()

    # Resolve sync mode
    if args.mode:
        sync_mode = args.mode
    elif args.sync:
        print("  ⚠️  --sync is deprecated, use --mode update")
        sync_mode = 'update'
    else:
        sync_mode = 'update'  # default

    try:
        # ── Resolve USB path ──────────────────────────────────────────────────────
        if args.usb:
            usb_path = Path(args.usb)
            if not usb_path.exists() and not args.dry_run:
                ap.error(f"USB path not found: {usb_path}")
            elif not usb_path.exists() and args.dry_run:
                # For dry-run, use the path even if it doesn't exist
                pass
        else:
            candidates = detect_pioneer_usbs()
            if not candidates:
                if not args.dry_run:
                    ap.error("No Pioneer USB drive detected. Plug in your USB or use --usb PATH.")
                else:
                    # For dry-run preview, use a placeholder path
                    usb_path = Path("/Volumes/PIONEER")
                    print(f"📋 DRY-RUN MODE: No USB detected. Previewing with placeholder: {usb_path}")
            elif len(candidates) == 1:
                usb_path = candidates[0]
                print(f"Auto-detected USB: {usb_path}")
            else:
                # Multiple USBs — ask which one
                try:
                    import questionary
                    usb_path = Path(questionary.select(
                        "Multiple Pioneer USBs detected. Which one?",
                        choices=[str(p) for p in candidates]
                    ).ask())
                except ImportError:
                    print("Multiple USBs found:")
                    for i, p in enumerate(candidates):
                        print(f"  [{i}] {p}")
                    idx = int(input("Select index: "))
                    usb_path = candidates[idx]

        if not args.dry_run:
            # Ensure USB is writable
            test_file = usb_path / ".copilot_write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except OSError as e:
                ap.error(f"USB is read-only or not writable: {e}")

        # ── Load playlist tree from master.db ────────────────────────────────────
        master = open_db(MASTER_DB)
        tree = get_playlist_tree(master)
        master.close()

        # ── Determine selected playlist IDs ──────────────────────────────────────
        if args.select:
            selected_ids = run_selector(tree)
            if not selected_ids:
                print("Nothing selected. Exiting.")
                sys.exit(0)
            playlist_ids = set(selected_ids)
        elif args.all:
            playlist_ids = {pl_id for _, (pl_id, attr) in tree.items() if attr == 0}
        elif args.playlists:
            playlist_ids = collect_playlist_ids(tree, args.playlists)
            if not playlist_ids:
                top = sorted({p[0] for p in tree})
                ap.error(
                    f"No playlists found matching: {args.playlists}\n"
                    "Available top-level folders:\n" +
                    '\n'.join(f"  • {n}" for n in top)
                )
        else:
            # No mode given: default to --select if interactive, else print help
            if sys.stdin.isatty():
                selected_ids = run_selector(tree)
                playlist_ids = set(selected_ids) if selected_ids else set()
                if not playlist_ids:
                    print("Nothing selected. Exiting.")
                    sys.exit(0)
            else:
                ap.print_help()
                sys.exit(1)

        export_to_usb(usb_path, playlist_ids, tree, sync_mode, args.dry_run, args.fetch_nas)
        print("\n✅ Export completed successfully")

    except Exception as e:
        print(f"\n❌ Export failed: {e}")
        checkpoint(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
