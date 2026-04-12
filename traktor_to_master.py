#!/usr/bin/env python3.11
"""
traktor_to_master.py — Sync Traktor playlists directly to Rekordbox master.db.

Bypasses the intermediate XML step entirely:
  collection.nml → master.db + masterPlaylists6.xml

Usage:
    python3.11 traktor_to_master.py --all [--nml PATH] [--dry-run]
    python3.11 traktor_to_master.py --playlists "04 - History" "03 - Events" [--dry-run]
    python3.11 traktor_to_master.py --playlists "2024-01" --dry-run

Arguments:
    --all                   Sync every playlist in the collection
    --playlists NAME ...    Sync playlists whose path contains any of the given names
    --nml PATH              Path to collection.nml (default: ~/Documents/…)
    --dry-run               Print what would change; do NOT write anything

Safety:
    - Always backs up master.db before any writes
    - Never touches collection.nml
    - rb_local_usn is never NULL
"""

import argparse
import datetime
import shutil
import sys
import time
import uuid
import zlib
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import unquote

import sqlcipher3

from config import MASTER_DB_KEY
from tag_config import (
    parse_comment_tags, load_tag_categories, save_tag_categories,
    merge_new_tags, classify_tag, classify_all_tags, DEFAULT_CONFIG_PATH,
)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ── Constants ─────────────────────────────────────────────────────────────────

MASTER_DB     = Path.home() / "Library/Pioneer/rekordbox/master.db"
PLAYLISTS_XML = Path.home() / "Library/Pioneer/rekordbox/masterPlaylists6.xml"
DEFAULT_NML   = Path.home() / "Documents/Native Instruments/Traktor 3.11.1/collection.nml"

EXT_TO_FTYPE = {
    'mp3': 1, 'aif': 10, 'aiff': 10, 'wav': 11,
    'm4a': 6, 'flac': 45, 'ogg': 8,
}

# Traktor color index → Rekordbox decimal color integer (RGB packed)
TRAKTOR_TO_RB_COLOR = {
    0:  None,
    1:  16711680,   # Red     #FF0000
    2:  16737792,   # Orange  #FF6600
    3:  16776960,   # Yellow  #FFFF00
    4:  52224,      # Green   #00CC00
    5:  52479,      # Blue    #00CCFF
    6:  8388736,    # Purple  #800080
    7:  16711935,   # Magenta #FF00FF
    8:  65280,      # Lime    #00FF00
    9:  65535,      # Cyan    #00FFFF
    10: 16744448,   # Amber   #FF8000
    11: 8388608,    # Maroon  #800000
    12: 32768,      # DkGreen #008000
    13: 8421376,    # Olive   #808000
    14: 128,        # Navy    #000080
    15: 4915330,    # Teal    #4B0082
}

# Traktor cue TYPE → Rekordbox cue type integer
# Traktor: 0=cue, 1=fade-in, 2=fade-out, 3=load, 4=grid(skip), 5=loop
TRAKTOR_CUE_TYPE_TO_RB = {
    0: 0,    # cue    → cue
    1: 1,    # fade-in
    2: 2,    # fade-out
    3: 3,    # load
    4: None, # grid marker — handled as beat grid, not a cue
    5: 4,    # loop
}


# ── DB Helpers ────────────────────────────────────────────────────────────────

def now_ts() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime('%Y-%m-%d %H:%M:%S.') + f'{now.microsecond // 1000:03d} +00:00'

def now_ms() -> int:
    return int(time.time() * 1000)

def make_id(s: str) -> str:
    """Stable CRC32-based string ID. Returns a decimal string, e.g. '3271463592'."""
    return str(zlib.crc32(s.encode('utf-8')) & 0xFFFFFFFF)

def to_hex(n) -> str:
    """Convert decimal integer/string to uppercase hex (no 0x prefix)."""
    return format(int(n), 'X').upper()

def new_uuid() -> str:
    return str(uuid.uuid4())

def next_usn(con) -> int:
    """Return max(rb_local_usn) + 1 across all DJ tables. Call ONCE per session."""
    m = 0
    for tbl in ('djmdPlaylist', 'djmdContent', 'djmdSongPlaylist', 'djmdCue',
                'djmdMyTag', 'djmdSongMyTag'):
        v = con.execute(f'SELECT MAX(rb_local_usn) FROM {tbl}').fetchone()[0]
        if v and v > m:
            m = v
    return m + 1

def open_db(path: Path):
    """
    Open Rekordbox's SQLCipher-encrypted master.db for read-write.
    PRAGMA legacy=4 is CRITICAL — without it SQLCipher raises "file is not a database".
    """
    con = sqlcipher3.connect(str(path))
    con.execute(f"PRAGMA key='{MASTER_DB_KEY}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")   # CRITICAL
    con.execute("PRAGMA foreign_keys=OFF")
    return con

def backup_master_db(db_path: Path) -> Path:
    """Create a timestamped backup of master.db before any write operation."""
    ts      = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup  = db_path.parent / f'master_backup_{ts}.db'
    shutil.copy2(db_path, backup)
    print(f'Backing up master.db → {backup.name}')
    return backup


# ── NML Parsing (adapted from traktor_to_rekordbox.py) ───────────────────────

def _parse_location(loc_el) -> str:
    """
    Build a file://localhost URI from a Traktor LOCATION element.
    Traktor DIR uses /: as path separator; we normalise to /.
    """
    if loc_el is None:
        return ''
    volume = loc_el.get('VOLUME', '')
    dir_   = loc_el.get('DIR', '')
    file_  = loc_el.get('FILE', '')
    path   = (dir_ + file_).replace('/:', '/')
    if volume and volume != 'Macintosh HD':
        full = f'/Volumes/{volume}{path}'
    else:
        full = path
    encoded = full.replace(' ', '%20').replace('&', '%26')
    return f'file://localhost{encoded}'


def _location_to_fspath(location_uri: str) -> str:
    """Decode a file://localhost URI to a plain filesystem path."""
    return unquote(location_uri.replace('file://localhost', ''))


def parse_tracks(root) -> dict:
    """
    Parse all ENTRY elements from the NML root.

    Returns:
        dict mapping traktor_key (volume+dir+file) → track dict with fields:
        title, artist, album, genre, bpm, key, rating, comment, filesize,
        bitrate, playtime, import_date, label, color_idx, rb_color,
        location (file:// URI), filename, cues (list), grid (list).
    """
    tracks   = {}
    track_id = 1

    collection = root.find('COLLECTION')
    if collection is None:
        return tracks

    for entry in collection.findall('ENTRY'):
        loc = entry.find('LOCATION')
        if loc is None:
            continue

        vol         = loc.get('VOLUME', '')
        dir_        = loc.get('DIR', '')
        file_       = loc.get('FILE', '')
        traktor_key = f'{vol}{dir_}{file_}'

        info   = entry.find('INFO')
        tempo  = entry.find('TEMPO')
        album  = entry.find('ALBUM')

        bpm_raw = tempo.get('BPM', '0') if tempo is not None else '0'
        try:
            bpm = f'{float(bpm_raw):.2f}'
        except ValueError:
            bpm = '0.00'

        color_idx = int(entry.get('COLOR', '0') or '0')

        t = {
            'id':          track_id,
            'traktor_key': traktor_key,
            'title':       entry.get('TITLE', ''),
            'artist':      entry.get('ARTIST', ''),
            'album':       album.get('TITLE', '') if album is not None else '',
            'genre':       info.get('GENRE', '')         if info is not None else '',
            'comment':     info.get('COMMENT', '')       if info is not None else '',
            'key':         info.get('KEY', '')           if info is not None else '',
            'rating':      str(int(info.get('RANKING', '0') or '0') // 51)
                           if info is not None else '0',  # 0-255 → 0-5
            'playtime':    info.get('PLAYTIME', '0')    if info is not None else '0',
            'bitrate':     str(int(info.get('BITRATE', '0') or '0') // 1000)
                           if info is not None else '0',
            'filesize':    info.get('FILESIZE', '0')    if info is not None else '0',
            'import_date': (info.get('IMPORT_DATE', '') or '').replace('/', '-')
                           if info is not None else '',
            'label':       info.get('LABEL', '')         if info is not None else '',
            'bpm':         bpm,
            'color_idx':   color_idx,
            'rb_color':    TRAKTOR_TO_RB_COLOR.get(color_idx),
            'location':    _parse_location(loc),   # file://localhost URI
            'filename':    file_,
            'cues':        [],
            'grid':        [],
            'tags':        [],  # [bracket] tags from comment — filled below
        }

        # Extract [bracket] tags from comment field
        t['tags'] = parse_comment_tags(t['comment'])

        for cue in entry.findall('CUE_V2'):
            cue_type_traktor = int(cue.get('TYPE', '0'))
            rb_type          = TRAKTOR_CUE_TYPE_TO_RB.get(cue_type_traktor)

            start_sec = float(cue.get('START', '0')) / 1000.0  # Traktor stores ms

            if cue_type_traktor == 4:
                # Beat grid marker → store separately, not inserted as djmdCue
                t['grid'].append({'start': f'{start_sec:.3f}', 'bpm': bpm})
                continue

            if rb_type is None:
                continue

            hotcue  = int(cue.get('HOTCUE', '-1'))
            len_raw = float(cue.get('LEN', '0'))
            c = {
                'name':  cue.get('NAME', ''),
                'type':  rb_type,
                'start': f'{start_sec:.3f}',
                'num':   str(hotcue),
            }
            if cue_type_traktor == 5:  # loop — store end time
                c['end'] = f'{(start_sec + len_raw / 1000.0):.3f}'

            t['cues'].append(c)

        tracks[traktor_key] = t
        track_id += 1

    return tracks


def make_track_lookup(tracks: dict) -> dict:
    """Build a per-track field dict used by smartlist query evaluation."""
    lookup = {}
    for key, t in tracks.items():
        lookup[key] = {
            'COMMENT':    t['comment'].lower(),
            'GENRE':      t['genre'].lower(),
            'COLOR':      str(t['color_idx']),
            'LABEL':      t['label'].lower(),
            'PLAYCOUNT':  '0',
            'IMPORTDATE': t['import_date'],
            'FILEPATH':   t['location'].lower(),
        }
    return lookup


def eval_smartlist_query(query_raw: str, track_fields: dict) -> bool:
    """
    Evaluate a Traktor smartlist query against a track's field dict.
    Supports: $FIELD % "value" (contains), == != > < >= <=, & (AND), | (OR), ! (NOT).
    """
    q = unescape(query_raw)

    def tokenize(s):
        tokens = []
        i = 0
        while i < len(s):
            if s[i] in '()':
                tokens.append(s[i]); i += 1
            elif s[i:i+2] in ('>=', '<=', '!='):
                tokens.append(s[i:i+2]); i += 2
            elif s[i] in ('%', '>', '<', '=', '&', '|', '!'):
                if s[i] == '=' and tokens and tokens[-1] in ('>', '<', '!'):
                    tokens[-1] += '='; i += 1
                else:
                    tokens.append(s[i]); i += 1
            elif s[i] == '$':
                j = i + 1
                while j < len(s) and (s[j].isalnum() or s[j] == '_'):
                    j += 1
                tokens.append('$' + s[i+1:j]); i = j
            elif s[i] == '"':
                j = i + 1
                while j < len(s) and s[j] != '"':
                    j += 1
                tokens.append(s[i+1:j]); i = j + 1
            elif s[i].isspace():
                i += 1
            else:
                j = i
                while j < len(s) and not s[j].isspace() and s[j] not in '()&|!%<>=':
                    j += 1
                tokens.append(s[i:j]); i = j
        return tokens

    tokens = tokenize(q)
    pos    = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume():
        v = tokens[pos[0]]; pos[0] += 1; return v

    def parse_or():
        left = parse_and()
        while peek() == '|':
            consume()
            left = left or parse_and()
        return left

    def parse_and():
        left = parse_not()
        while peek() == '&':
            consume()
            left = left and parse_not()
        return left

    def parse_not():
        if peek() == '!':
            consume()
            return not parse_atom()
        return parse_atom()

    def parse_atom():
        if peek() == '(':
            consume()
            val = parse_or()
            if peek() == ')':
                consume()
            return val
        tok = peek()
        if tok and tok.startswith('$'):
            field = consume()[1:]
            op    = consume()
            val   = consume().lower()
            fv    = track_fields.get(field, '').lower()
            if op == '%':   return val in fv
            if op == '==':  return fv == val
            if op == '!=':  return fv != val
            if op == '>':   return fv > val
            if op == '<':   return fv < val
            if op == '>=':  return fv >= val
            if op == '<=':  return fv <= val
        return False

    try:
        return parse_or()
    except Exception:
        return False


def expand_smartlist(query_raw: str, track_lookup: dict) -> list:
    """Return list of traktor_keys whose fields match the smartlist query."""
    return [key for key, fields in track_lookup.items()
            if eval_smartlist_query(query_raw, fields)]


def parse_playlist_tree(root, tracks: dict, track_lookup: dict) -> list:
    """
    Parse the PLAYLISTS NODE tree from the NML root element.

    Returns a nested list of node dicts:
      Folder: {'type': 'folder', 'name': str, 'children': [...]}
      Playlist: {'type': 'playlist', 'name': str, 'keys': [traktor_key, ...]}

    Smartlists are expanded to regular playlists by evaluating their query.
    """
    playlists_el = root.find('PLAYLISTS')
    if playlists_el is None:
        return []
    root_node = playlists_el.find('NODE')
    if root_node is None:
        return []

    stats = {'playlists': 0, 'folders': 0, 'smartlists': 0, 'smart_expanded': 0}

    def walk(node_el):
        ntype = node_el.get('TYPE', '')
        name  = node_el.get('NAME', '')

        if ntype == 'FOLDER':
            stats['folders'] += 1
            children = []
            subnodes = node_el.find('SUBNODES')
            if subnodes is not None:
                for child in subnodes.findall('NODE'):
                    result = walk(child)
                    if result:
                        children.append(result)
            return {'type': 'folder', 'name': name, 'children': children}

        elif ntype == 'PLAYLIST':
            stats['playlists'] += 1
            playlist_el = node_el.find('PLAYLIST')
            keys = []
            if playlist_el is not None:
                for entry in playlist_el.findall('ENTRY'):
                    pk = entry.find('PRIMARYKEY')
                    if pk is not None:
                        keys.append(pk.get('KEY', ''))
            return {'type': 'playlist', 'name': name, 'keys': keys}

        elif ntype == 'SMARTLIST':
            stats['smartlists'] += 1
            sl_el = node_el.find('SMARTLIST')
            if sl_el is None:
                return {'type': 'playlist', 'name': name + ' [smart]', 'keys': []}
            se    = sl_el.find('SEARCH_EXPRESSION')
            query = se.get('QUERY', '') if se is not None else ''
            if query:
                keys = expand_smartlist(query, track_lookup)
                stats['smart_expanded'] += 1
            else:
                keys = []
            return {'type': 'playlist', 'name': name, 'keys': keys}

        return None

    result   = []
    subnodes = root_node.find('SUBNODES')
    if subnodes is not None:
        for child in subnodes.findall('NODE'):
            node = walk(child)
            if node:
                result.append(node)

    print(f'  Parsed {stats["folders"]} folders, {stats["playlists"]} playlists, '
          f'{stats["smartlists"]} smartlists ({stats["smart_expanded"]} expanded)')
    return result


# ── Playlist Filtering ────────────────────────────────────────────────────────

def collect_playlists(tree: list, selected_names: set) -> list:
    """
    Walk the NML playlist tree and collect all matching playlists.

    A playlist matches if any segment of its path tuple appears in selected_names.
    Pass an empty set to collect everything (equivalent to --all).

    IMPORTANT: path segments are kept as tuple elements — never joined/split on '/'
    so that playlist names that legitimately contain '/' are handled correctly.

    Returns:
        List of (path_tuple, playlist_node) pairs, in traversal order.
        path_tuple: tuple of str, e.g. ('04 - History', '- AS', '2024-01')
        playlist_node: dict with 'keys' list of traktor_keys
    """
    results = []

    def walk(node, path_tuple):
        if node['type'] == 'folder':
            new_path = path_tuple + (node['name'],)
            for child in node.get('children', []):
                walk(child, new_path)
        elif node['type'] == 'playlist':
            full_path = path_tuple + (node['name'],)
            if not selected_names or any(seg in selected_names for seg in full_path):
                results.append((full_path, node))

    for top_node in tree:
        walk(top_node, ())

    return results


# ── DB Write Helpers ──────────────────────────────────────────────────────────

def tonality_to_key_id(ton: str, key_map: dict) -> int:
    """
    Convert a Traktor key notation (Camelot wheel, e.g. '8A', '11B') to
    the Rekordbox djmdKey.ID integer.
    """
    if not ton:
        return 0
    # Traktor uses A/B suffix (8A = 8Am in Camelot), Rekordbox ScaleName uses M/D
    camelot = ton[:-1] + ('M' if ton.upper().endswith('A') else 'D')
    return key_map.get(camelot.upper(), 0)


def num_to_cue_kind(num: int) -> int:
    """
    Map a Traktor hotcue number to a Rekordbox djmdCue.Kind value.
    num < 0  → memory cue (Kind=0)
    num 0-2  → hot cue 1-3 (Kind 1-3)
    num 3+   → hot cue 4+ (Kind 5+, skipping Kind=4 which Rekordbox reserves for loops)
    """
    if num < 0:  return 0
    if num < 3:  return num + 1
    return num + 2


def get_or_create_folder(con, path_parts: list, parent_id='root', usn: int = 0) -> str:
    """
    Recursively ensure that every folder in path_parts exists in djmdPlaylist
    (Attribute=1), creating missing ones as needed.

    Returns the ID of the deepest folder (or parent_id if path_parts is empty).

    IMPORTANT: path_parts is a plain list of name strings; folder names containing
    '/' are safe because we never split on '/' here.
    """
    if not path_parts:
        return str(parent_id)
    name     = path_parts[0]
    existing = con.execute(
        'SELECT ID FROM djmdPlaylist WHERE Name=? AND ParentID=? AND Attribute=1',
        (name, str(parent_id))).fetchone()
    if existing:
        folder_id = str(existing[0])
    else:
        folder_id = make_id(f'folder:{parent_id}:{name}')
        max_seq   = con.execute(
            'SELECT COALESCE(MAX(Seq), -1) FROM djmdPlaylist WHERE ParentID=?',
            (str(parent_id),)).fetchone()[0]
        con.execute("""INSERT INTO djmdPlaylist
            (ID,Seq,Name,Attribute,ParentID,UUID,
             rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
             rb_local_usn,created_at,updated_at)
            VALUES (?,?,?,1,?,?,0,0,0,0,?,?,?)""",
            (folder_id, max_seq + 1, name, str(parent_id), new_uuid(),
             usn, now_ts(), now_ts()))
    return get_or_create_folder(con, path_parts[1:], folder_id, usn)


# ── masterPlaylists6.xml ──────────────────────────────────────────────────────

def build_manifest_from_db(con) -> list:
    """
    Walk the entire DB playlist tree and return manifest_nodes:
    list of (decimal_id, parent_decimal_id, attribute) tuples.

    parent_decimal_id=0 means the node's ParentID is 'root'.
    This is what masterPlaylists6.xml <NODE> elements encode.
    """
    manifest_nodes = []

    def recurse(parent_db_id, parent_dec_id):
        rows = con.execute(
            'SELECT ID, Attribute FROM djmdPlaylist WHERE ParentID=? ORDER BY Seq',
            (str(parent_db_id),)
        ).fetchall()
        for (db_id, attr) in rows:
            try:
                dec_id = int(db_id)
            except (ValueError, TypeError):
                continue
            manifest_nodes.append((dec_id, parent_dec_id, attr))
            recurse(db_id, dec_id)

    root_rows = con.execute(
        "SELECT ID, Attribute FROM djmdPlaylist WHERE ParentID='root' ORDER BY Seq"
    ).fetchall()
    for (db_id, attr) in root_rows:
        try:
            dec_id = int(db_id)
        except (ValueError, TypeError):
            continue
        manifest_nodes.append((dec_id, 0, attr))
        recurse(db_id, dec_id)

    return manifest_nodes


def write_playlists_xml(xml_path: Path, manifest_nodes: list, dry_run: bool):
    """
    Write masterPlaylists6.xml.

    Reconstructs the file from manifest_nodes (built from DB state), so it
    always reflects the full current playlist tree — existing entries are
    preserved, new ones appended.
    """
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
            f'Attribute="{attribute}" Timestamp="{ts_ms}" '
            f'Lib_Type="0" CheckType="0"/>'
        )
    lines += ['  </PLAYLISTS>', '</MASTER_PLAYLIST>', '']
    content = '\n'.join(lines)

    print(f'Updating masterPlaylists6.xml ({len(manifest_nodes)} nodes) …')
    if not dry_run:
        xml_path.write_text(content, encoding='utf-8')
    print('  Done.')


# ── Core Sync: Tracks ─────────────────────────────────────────────────────────

def sync_tracks(con, selected_tracks: dict, usn: int) -> tuple:
    """
    Insert new tracks into djmdContent and their cue points into djmdCue.
    Tracks already present in DB (by FolderPath) are skipped — not updated.

    Args:
        con:             Open SQLCipher connection (read-write)
        selected_tracks: {traktor_key: track_dict} — all tracks needed by selected playlists
        usn:             Session USN counter (obtained once via next_usn)

    Returns:
        (path_to_content_id, new_count, skipped_count)
        path_to_content_id: {filesystem_path: content_id_str} for ALL selected tracks
    """
    # Load existing FolderPath → ID map from DB
    db_paths = {
        r[0]: str(r[1])
        for r in con.execute('SELECT FolderPath, ID FROM djmdContent').fetchall()
    }

    # Key map: Rekordbox ScaleName (e.g. "8AM") → KeyID
    key_map = {
        r[1].upper(): r[0]
        for r in con.execute('SELECT ID, ScaleName FROM djmdKey').fetchall()
    }

    # Artist lookup/insert cache (name → ID)
    artist_cache = {
        r[0]: str(r[1])
        for r in con.execute('SELECT Name, ID FROM djmdArtist').fetchall()
    }

    def get_or_create_artist(name: str):
        if not name:
            return None
        if name in artist_cache:
            return artist_cache[name]
        aid = make_id(f'artist:{name}')
        # Guard against CRC32 collision where same ID maps to different name
        if con.execute('SELECT 1 FROM djmdArtist WHERE ID=? AND Name!=?',
                       (aid, name)).fetchone():
            aid = make_id(f'artist:{name}:v2')
        if not con.execute('SELECT 1 FROM djmdArtist WHERE ID=?', (aid,)).fetchone():
            con.execute("""INSERT INTO djmdArtist
                (ID,Name,UUID,rb_data_status,rb_local_data_status,
                 rb_local_deleted,rb_local_synced,created_at,updated_at)
                VALUES (?,?,?,0,0,0,0,?,?)""",
                (aid, name, new_uuid(), now_ts(), now_ts()))
        artist_cache[name] = aid
        return aid

    # Partition into new vs. already-present
    to_insert           = []   # [(fs_path, track_dict), ...]
    path_to_content_id  = {}   # populated for both new and existing

    for tkey, t in selected_tracks.items():
        fs_path = _location_to_fspath(t['location'])
        if fs_path in db_paths:
            path_to_content_id[fs_path] = db_paths[fs_path]
        else:
            to_insert.append((fs_path, t))

    new_count     = 0
    skipped_count = len(path_to_content_id)

    if not to_insert:
        return path_to_content_id, new_count, skipped_count

    # Optional progress bar for large inserts
    iterable = (
        tqdm(to_insert, desc='  Inserting tracks', unit='track')
        if HAS_TQDM and len(to_insert) > 50
        else to_insert
    )

    for fs_path, t in iterable:
        suffix     = Path(fs_path).suffix.lstrip('.').lower()
        ftype      = EXT_TO_FTYPE.get(suffix, 1)
        bpm_int    = round(float(t['bpm']) * 100)   # Rekordbox stores BPM * 100 as integer
        length_sec = int(float(t['playtime']))
        bitrate    = int(t['bitrate'])
        samplerate = 44100  # Traktor NML does not reliably expose samplerate
        key_id     = tonality_to_key_id(t['key'], key_map) or None
        artist_id  = get_or_create_artist(t['artist'])

        content_id = make_id(f'track:{fs_path}')
        # CRC32 collision guard
        if con.execute('SELECT 1 FROM djmdContent WHERE ID=?',
                       (content_id,)).fetchone():
            content_id = make_id(f'track:{fs_path}:v2')

        track_uuid = new_uuid()

        con.execute("""INSERT INTO djmdContent (
            ID,FolderPath,FileNameL,Title,ArtistID,BPM,Length,
            FileType,BitRate,SampleRate,Commnt,Rating,ColorID,KeyID,
            UUID,rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
            rb_local_usn,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,257,0,0,0,?,?,?)""",
            (content_id, fs_path, t['filename'], t['title'], artist_id,
             bpm_int, length_sec, ftype, bitrate, samplerate,
             t['comment'], key_id, track_uuid, usn, now_ts(), now_ts()))

        # Insert cue points
        for cue in t['cues']:
            num    = int(cue['num'])
            inmsc  = round(float(cue['start']) * 1000)
            end_f  = float(cue.get('end', '-0.001'))
            outmsc = round(end_f * 1000) if end_f > 0 else -1
            kind   = num_to_cue_kind(num)
            # Kind=0 → memory cue (green=3); Kind>0 → hot cue (default colour=-1)
            color  = 3 if kind == 0 else -1
            cue_id = make_id(f'cue:{content_id}:{kind}:{inmsc}')
            con.execute("""INSERT OR IGNORE INTO djmdCue (
                ID,ContentID,InMsec,InFrame,InMpegFrame,InMpegAbs,
                OutMsec,OutFrame,OutMpegFrame,OutMpegAbs,
                Kind,Color,ColorTableIndex,ActiveLoop,Comment,
                BeatLoopSize,CueMicrosec,ContentUUID,UUID,
                rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                rb_local_usn,created_at,updated_at)
                VALUES (?,?,?,0,0,0,?,0,0,0,?,?,-1,0,?,0,0,?,?,0,0,0,0,?,?,?)""",
                (cue_id, content_id, inmsc, outmsc, kind, color,
                 cue.get('name', '') or '', track_uuid, new_uuid(),
                 usn, now_ts(), now_ts()))

        path_to_content_id[fs_path] = content_id
        new_count += 1

    con.commit()
    return path_to_content_id, new_count, skipped_count


# ── Core Sync: Playlists ──────────────────────────────────────────────────────

def sync_playlists(con, selected_playlists: list, tracks: dict,
                   path_to_content_id: dict, usn: int) -> int:
    """
    Insert/update playlists in djmdPlaylist + djmdSongPlaylist.

    For each playlist in selected_playlists:
      - Creates any missing parent folders via get_or_create_folder()
      - Creates the playlist row if not already present
      - Appends track links for tracks not already in the playlist

    TrackNo is 1-based and sequential, continuing after any existing links.

    Returns:
        Number of playlists processed.
    """
    pl_count = 0

    for path_tuple, playlist_node in selected_playlists:
        # ── Ensure parent folder hierarchy exists ─────────────────────────────
        pl_name           = path_tuple[-1]
        parent_path_parts = list(path_tuple[:-1])   # DO NOT split on '/' — use tuple segments
        parent_id         = get_or_create_folder(con, parent_path_parts, 'root', usn)

        # ── Get or create the playlist row itself (Attribute=0) ───────────────
        pl_id = make_id(f'playlist:{parent_id}:{pl_name}')
        if not con.execute('SELECT 1 FROM djmdPlaylist WHERE ID=?', (pl_id,)).fetchone():
            max_seq = con.execute(
                'SELECT COALESCE(MAX(Seq), -1) FROM djmdPlaylist WHERE ParentID=?',
                (str(parent_id),)).fetchone()[0]
            con.execute("""INSERT INTO djmdPlaylist
                (ID,Seq,Name,Attribute,ParentID,UUID,
                 rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                 rb_local_usn,created_at,updated_at)
                VALUES (?,?,?,0,?,?,0,0,0,0,?,?,?)""",
                (pl_id, max_seq + 1, pl_name, str(parent_id), new_uuid(),
                 usn, now_ts(), now_ts()))

        # ── Link tracks → playlist (skip already-linked) ──────────────────────
        existing_links = {
            str(r[0])
            for r in con.execute(
                'SELECT ContentID FROM djmdSongPlaylist WHERE PlaylistID=?',
                (pl_id,)).fetchall()
        }
        seq = con.execute(
            'SELECT COALESCE(MAX(TrackNo), 0) FROM djmdSongPlaylist WHERE PlaylistID=?',
            (pl_id,)).fetchone()[0]

        for tkey in playlist_node['keys']:
            t = tracks.get(tkey)
            if t is None:
                continue
            fs_path    = _location_to_fspath(t['location'])
            content_id = path_to_content_id.get(fs_path)
            if content_id is None:
                continue
            if str(content_id) in existing_links:
                continue
            seq  += 1
            sp_id = make_id(f'sp:{pl_id}:{seq}:{content_id}')
            con.execute("""INSERT OR IGNORE INTO djmdSongPlaylist
                (ID,PlaylistID,ContentID,TrackNo,UUID,
                 rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                 rb_local_usn,created_at,updated_at)
                VALUES (?,?,?,?,?,0,0,0,0,?,?,?)""",
                (sp_id, pl_id, str(content_id), seq, new_uuid(),
                 usn, now_ts(), now_ts()))

        con.commit()

        track_count  = len([k for k in playlist_node['keys'] if tracks.get(k)])
        path_display = ' / '.join(path_tuple)
        print(f'  ✅ {path_display} ({track_count} tracks)')
        pl_count += 1

    return pl_count


# ── MyTag Sync ────────────────────────────────────────────────────────────────

def sync_mytags(con, tracks: dict, path_to_content_id: dict,
                tag_categories: dict, usn: int) -> tuple:
    """
    Insert MyTag categories, tags, and track-tag links into master.db.

    Tables:
      djmdMyTag     — tag definitions (categories as parents, tags as children)
      djmdSongMyTag — track-tag associations

    Returns:
        (categories_created, tags_created, links_created)
    """
    ts = now_ts()
    cats_created = 0
    tags_created = 0
    links_created = 0

    # Collect all unique tags across all tracks
    all_tags = set()
    for t in tracks.values():
        for tag in t.get('tags', []):
            all_tags.add(tag)

    if not all_tags:
        return (0, 0, 0)

    # Build category→tags mapping
    cat_tags: dict[str, list[str]] = {}
    for tag in sorted(all_tags):
        cat = classify_tag(tag, tag_categories)
        cat_tags.setdefault(cat, []).append(tag)

    # Insert category rows (Attribute=1 = folder/category)
    cat_id_map: dict[str, str] = {}  # category_name → ID
    seq = 0
    for cat_name in sorted(cat_tags.keys()):
        cat_id = make_id(f'mytag-cat:{cat_name}')
        # Collision guard
        existing = con.execute("SELECT ID FROM djmdMyTag WHERE ID=?", (cat_id,)).fetchone()
        if existing is None:
            con.execute("""INSERT OR IGNORE INTO djmdMyTag
                (ID, Seq, Name, Attribute, ParentID, UUID,
                 rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                 usn, rb_local_usn, created_at, updated_at)
                VALUES (?,?,?,1,NULL,?,0,0,0,0,?,?,?,?)""",
                (cat_id, seq, cat_name, new_uuid(), usn, usn, ts, ts))
            cats_created += 1
        cat_id_map[cat_name] = cat_id
        seq += 1

    # Insert tag rows (Attribute=0 = tag/leaf)
    tag_id_map: dict[str, str] = {}  # tag_name_lower → ID
    for cat_name, tag_list in sorted(cat_tags.items()):
        parent_id = cat_id_map[cat_name]
        tag_seq = 0
        for tag_name in sorted(tag_list):
            tag_id = make_id(f'mytag:{tag_name}')
            existing = con.execute("SELECT ID FROM djmdMyTag WHERE ID=?", (tag_id,)).fetchone()
            if existing is None:
                con.execute("""INSERT OR IGNORE INTO djmdMyTag
                    (ID, Seq, Name, Attribute, ParentID, UUID,
                     rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                     usn, rb_local_usn, created_at, updated_at)
                    VALUES (?,?,?,0,?,?,0,0,0,0,?,?,?,?)""",
                    (tag_id, tag_seq, tag_name, parent_id, new_uuid(), usn, usn, ts, ts))
                tags_created += 1
            tag_id_map[tag_name.lower()] = tag_id
            tag_seq += 1

    # Insert track-tag links into djmdSongMyTag
    track_no_counter: dict[str, int] = {}  # tag_id → next TrackNo
    for traktor_key, t in tracks.items():
        content_id = path_to_content_id.get(t.get('location', ''))
        if not content_id:
            continue
        for tag_name in t.get('tags', []):
            tag_id = tag_id_map.get(tag_name.lower())
            if not tag_id:
                continue
            link_id = make_id(f'mytag-link:{tag_id}:{content_id}')
            track_no = track_no_counter.get(tag_id, 0)
            track_no_counter[tag_id] = track_no + 1
            existing = con.execute(
                "SELECT ID FROM djmdSongMyTag WHERE ID=?", (link_id,)
            ).fetchone()
            if existing is None:
                con.execute("""INSERT OR IGNORE INTO djmdSongMyTag
                    (ID, MyTagID, ContentID, TrackNo, UUID,
                     rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                     usn, rb_local_usn, created_at, updated_at)
                    VALUES (?,?,?,?,?,0,0,0,0,?,?,?,?)""",
                    (link_id, tag_id, str(content_id), track_no, new_uuid(),
                     usn, usn, ts, ts))
                links_created += 1

    con.commit()
    return (cats_created, tags_created, links_created)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Sync Traktor playlists directly to Rekordbox master.db.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--all', action='store_true',
                      help='Sync the entire Traktor collection')
    mode.add_argument('--playlists', metavar='NAME', nargs='+',
                      help='Sync playlists whose path contains any of these names')
    parser.add_argument('--nml', metavar='PATH', default=str(DEFAULT_NML),
                        help=f'Path to collection.nml (default: {DEFAULT_NML})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would change without writing anything')
    tag_group = parser.add_mutually_exclusive_group()
    tag_group.add_argument('--tags', action='store_true', default=True,
                           help='Enable comment-to-MyTag conversion (default: on)')
    tag_group.add_argument('--no-tags', action='store_true',
                           help='Skip MyTag conversion')
    args = parser.parse_args()
    do_tags = args.tags and not args.no_tags

    nml_path = Path(args.nml)

    # ── Pre-flight checks ─────────────────────────────────────────────────────
    if not nml_path.exists():
        print(f'❌ collection.nml not found: {nml_path}', file=sys.stderr)
        sys.exit(1)
    if not MASTER_DB.exists():
        print(f'❌ master.db not found: {MASTER_DB}', file=sys.stderr)
        sys.exit(1)

    # ── 1. Parse NML ─────────────────────────────────────────────────────────
    print(f'Reading {nml_path} …')
    nml_tree     = ET.parse(str(nml_path))
    nml_root     = nml_tree.getroot()

    tracks        = parse_tracks(nml_root)
    track_lookup  = make_track_lookup(tracks)
    playlist_tree = parse_playlist_tree(nml_root, tracks, track_lookup)

    total_pl = len(collect_playlists(playlist_tree, set()))
    print(f'Parsed {len(tracks)} tracks, {total_pl} playlists')

    # ── 2. Filter playlists ───────────────────────────────────────────────────
    selected_names     = set() if args.all else set(args.playlists or [])
    selected_playlists = collect_playlists(playlist_tree, selected_names)

    if not selected_playlists:
        print('❌ No playlists matched the given names. Exiting.', file=sys.stderr)
        sys.exit(1)

    # Gather unique tracks referenced by the selected playlists
    selected_track_keys = set()
    for _, pl_node in selected_playlists:
        selected_track_keys.update(pl_node['keys'])
    selected_tracks = {k: tracks[k] for k in selected_track_keys if k in tracks}

    # ── 3. Dry run ─────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f'\n[DRY RUN] Would sync {len(selected_playlists)} playlists, '
              f'{len(selected_tracks)} unique tracks\n')
        for path_tuple, pl_node in selected_playlists:
            track_count  = len([k for k in pl_node['keys'] if tracks.get(k)])
            path_display = ' / '.join(path_tuple)
            print(f'  {path_display} ({track_count} tracks)')

        # MyTag dry-run preview
        if do_tags:
            tag_categories = load_tag_categories()
            all_tags = set()
            for t in selected_tracks.values():
                all_tags.update(t.get('tags', []))
            if all_tags:
                cat_breakdown = classify_all_tags(sorted(all_tags), tag_categories)
                # Count potential links
                link_count = sum(
                    len(t.get('tags', [])) for t in selected_tracks.values()
                )
                print(f'\n🏷️  MyTag conversion:')
                print(f'  Would create {len(cat_breakdown)} categories')
                print(f'  Would create {len(all_tags)} tags across categories')
                print(f'  Would create up to {link_count} track-tag links')
                print(f'  Category breakdown:')
                for cat, tags in sorted(cat_breakdown.items()):
                    tag_preview = ', '.join(tags[:5])
                    if len(tags) > 5:
                        tag_preview += f', … (+{len(tags)-5} more)'
                    print(f'    {cat} ({len(tags)} tags): {tag_preview}')

                # Show would-be config (but don't write it)
                has_new = merge_new_tags(tag_categories, list(all_tags))
                if has_new:
                    print(f'\n  Would update {DEFAULT_CONFIG_PATH.name} with new tags')
            else:
                print(f'\n🏷️  MyTag conversion: no [bracket] tags found in comments')

        sys.exit(0)

    # ── 4. Backup master.db ───────────────────────────────────────────────────
    backup_master_db(MASTER_DB)

    # ── 5. Open DB ────────────────────────────────────────────────────────────
    con = open_db(MASTER_DB)
    try:
        # ── 6. Get USN once — increment locally for each write ────────────────
        usn = next_usn(con)

        print(f'Syncing {len(selected_playlists)} playlists '
              f'({len(selected_tracks)} tracks) …')

        # ── 7. Insert/skip tracks in djmdContent + djmdCue ───────────────────
        path_to_content_id, new_count, skipped_count = sync_tracks(
            con, selected_tracks, usn
        )

        # ── 8. Insert/update playlists in djmdPlaylist + djmdSongPlaylist ─────
        pl_count = sync_playlists(
            con, selected_playlists, tracks, path_to_content_id, usn
        )

        # ── 8b. Sync MyTags from comment [bracket] tags ──────────────────────
        mytag_cats = mytag_tags = mytag_links = 0
        if do_tags:
            tag_categories = load_tag_categories()
            # Merge any new tags into the categories dict
            all_discovered = set()
            for t in selected_tracks.values():
                all_discovered.update(t.get('tags', []))
            has_new = merge_new_tags(tag_categories, list(all_discovered))

            mytag_cats, mytag_tags, mytag_links = sync_mytags(
                con, selected_tracks, path_to_content_id, tag_categories, usn
            )

            # Save updated config (new tags may have been added to Uncategorized)
            if has_new or not DEFAULT_CONFIG_PATH.exists():
                save_tag_categories(DEFAULT_CONFIG_PATH, tag_categories)
                print(f'  📝 Saved {DEFAULT_CONFIG_PATH.name}')

        # ── 9. Rebuild masterPlaylists6.xml from full DB state ────────────────
        manifest_nodes = build_manifest_from_db(con)
        write_playlists_xml(PLAYLISTS_XML, manifest_nodes, dry_run=False)

    except Exception as e:
        try:
            con.rollback()
        except Exception:
            pass
        print(f'❌ Error: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        con.close()

    # ── 10. Summary ───────────────────────────────────────────────────────────
    print(f'\n✅ Done: {new_count} new tracks added, {skipped_count} already in DB, '
          f'{pl_count} playlists synced')
    if do_tags and (mytag_cats or mytag_tags or mytag_links):
        print(f'   🏷️  MyTags: {mytag_cats} categories, {mytag_tags} tags, {mytag_links} track-tag links')


if __name__ == '__main__':
    main()
