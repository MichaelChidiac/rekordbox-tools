#!/usr/bin/env python3.11
"""
pdb_to_traktor.py

Imports a Rekordbox HISTORY playlist from a USB drive's export.pdb
directly into a Traktor collection.nml — no Rekordbox app needed.

Always creates a timestamped backup of the NML before modifying it.

Usage:
    python3.11 pdb_to_traktor.py \\
        --playlist "HISTORY 008" \\
        --name "My Live Set" \\
        --pdb "/Volumes/Extreme SSD/.PIONEER/rekordbox/export.pdb" \\
        --nml ~/Documents/Native\\ Instruments/Traktor\\ 3.11.1/collection.nml

    # --name supports folder paths with / separator:
    python3.11 pdb_to_traktor.py \\
        --playlist "HISTORY 008" \\
        --name "04 - History / Live Events / My Set"

    # --name defaults to the playlist name from the PDB if omitted
    # --pdb defaults to the Extreme SSD path if omitted
    # --nml defaults to Traktor 3.11.1 collection path if omitted
"""

import argparse
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

# ── Dependency check ─────────────────────────────────────────────────────────

try:
    from pyrekordbox import open_rekordbox_database  # noqa: F401 (not used, just check)
except ImportError:
    pass  # pyrekordbox not needed — we use the Node.js parser via subprocess

import subprocess, json, os

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_PDB = '/Volumes/Extreme SSD/.PIONEER/rekordbox/export.pdb'
DEFAULT_NML = str(Path.home() / 'Documents/Native Instruments/Traktor 3.11.1/collection.nml')
TOOLS_DIR   = Path(__file__).parent

# ── PDB reading (delegates to Node.js rekordbox-parser) ──────────────────────

_READER_SCRIPT = """
const { parsePdb, RekordboxPdb, tableRows } = require('rekordbox-parser');
const fs = require('fs');
const { PageType } = RekordboxPdb;

const pdbPath = process.argv[2];
const targetName = process.argv[3].toLowerCase();

const db = parsePdb(fs.readFileSync(pdbPath));

// History playlists
const histPlaylists = [];
for (const row of tableRows(db.tables.find(t => t.type === PageType.HISTORY_PLAYLISTS))) {
  histPlaylists.push({ id: row.id, name: row.name.body.text });
}

const target = histPlaylists.find(p => p.name.toLowerCase() === targetName);
if (!target) {
  process.stderr.write('PLAYLISTS:' + JSON.stringify(histPlaylists) + '\\n');
  process.exit(1);
}

// Track map
const trackMap = new Map();
for (const row of tableRows(db.tables.find(t => t.type === PageType.TRACKS))) {
  trackMap.set(row.id, {
    title:    row.title.body.text,
    filename: (row.filename && row.filename.body && row.filename.body.text) || '',
    bpm:      (row.tempo / 100).toFixed(1),
    artistId: row.artistId,
  });
}

// Artist map
const artistMap = new Map();
for (const row of tableRows(db.tables.find(t => t.type === PageType.ARTISTS))) {
  artistMap.set(row.id, row.name.body.text);
}

// History entries
const entries = [];
for (const row of tableRows(db.tables.find(t => t.type === PageType.HISTORY_ENTRIES))) {
  if (row.playlistId === target.id) {
    const track = trackMap.get(row.trackId);
    entries.push({
      index:    row.entryIndex,
      trackId:  row.trackId,
      filename: track ? track.filename : '',
      title:    track ? track.title    : '',
      artist:   track ? (artistMap.get(track.artistId) || '') : '',
      bpm:      track ? track.bpm : '0',
    });
  }
}
entries.sort((a, b) => a.index - b.index);

process.stdout.write(JSON.stringify({ playlist: target, entries }));
"""


def read_pdb(pdb_path: str, playlist_name: str) -> dict:
    """Use Node.js to parse the PDB and return playlist + entries as a dict."""
    node = '/usr/local/bin/node'  # Use absolute path for consistent subprocess execution
    if not Path(node).exists():
        node = 'node'  # Fallback to PATH lookup
    script_path = TOOLS_DIR / '_reader_tmp.js'
    script_path.write_text(_READER_SCRIPT)
    try:
        result = subprocess.run(
            [node, str(script_path), pdb_path, playlist_name],
            capture_output=True, text=True, cwd=str(TOOLS_DIR)
        )
        script_path.unlink()
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr.startswith('PLAYLISTS:'):
                playlists = json.loads(stderr[len('PLAYLISTS:'):])
                names = [p['name'] for p in playlists]
                print(f"Playlist '{playlist_name}' not found.")
                print(f"Available: {', '.join(names)}")
            else:
                print("Error reading PDB:", stderr)
            sys.exit(1)
        return json.loads(result.stdout)
    except Exception as e:
        if script_path.exists():
            script_path.unlink()
        raise e


# ── NML helpers ──────────────────────────────────────────────────────────────

def backup_nml(nml_path: str) -> str:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Use fixed timestamp format safe for all shells
    backup = nml_path + f'.backup_{ts[:8]}'
    shutil.copy2(nml_path, backup)
    return backup


def build_filename_key_map(nml_content: str) -> dict:
    pattern = r'LOCATION DIR="([^"]*)" FILE="([^"]*)" VOLUME="([^"]*)"'
    mapping = {}
    for m in re.finditer(pattern, nml_content):
        dir_, file_, vol = m.group(1), m.group(2), m.group(3)
        mapping[file_] = f'{vol}{dir_}{file_}'
    return mapping


def find_key(filename: str, mapping: dict) -> str | None:
    if filename in mapping:
        return mapping[filename]
    # Prefix match for truncated filenames (Pioneer truncates long filenames)
    if '.' not in filename:
        return None
    stem, ext = filename.rsplit('.', 1)
    ext = '.' + ext
    prefix = stem[:20]
    for fname, key in mapping.items():
        if fname.endswith(ext) and fname.startswith(prefix):
            return key
    return None


def _find_last_folder(nml_content: str, folder_name: str) -> re.Match | None:
    """Find the LAST occurrence of a folder node (the original, not duplicates at top)."""
    matches = list(re.finditer(
        rf'<NODE TYPE="FOLDER" NAME="{re.escape(folder_name)}"><SUBNODES COUNT="(\d+)">',
        nml_content
    ))
    return matches[-1] if matches else None


def _bump_subnodes(nml_content: str, match: re.Match) -> tuple[str, int]:
    """Increment the SUBNODES COUNT at the given match position. Returns (updated_content, insert_pos)."""
    old_count = int(match.group(1))
    new_count = old_count + 1
    old_tag = match.group(0)
    new_tag = old_tag.replace(f'COUNT="{old_count}"', f'COUNT="{new_count}"')
    # Replace only this specific occurrence by position
    start, end = match.start(), match.end()
    nml_content = nml_content[:start] + new_tag + nml_content[end:]
    insert_pos = start + len(new_tag)
    return nml_content, insert_pos


def inject_playlist(nml_content: str, playlist_path: str, keys: list[str], playlist_uuid: str) -> str:
    """Inject a playlist at the specified path (supports nested folders with /).
    
    Finds existing folders by name and inserts into them. Only creates
    folders that don't already exist.
    """
    entries_xml = ''.join(
        f'<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="{k.replace("&", "&amp;")}"></PRIMARYKEY></ENTRY>'
        for k in keys
    )
    count = len(keys)
    
    parts = [p.strip() for p in playlist_path.split('/')]
    playlist_name = parts[-1]
    folder_parts = parts[:-1]
    
    playlist_node = (
        f'<NODE TYPE="PLAYLIST" NAME="{playlist_name}">'
        f'<PLAYLIST ENTRIES="{count}" TYPE="LIST" UUID="{playlist_uuid}">'
        f'{entries_xml}'
        f'</PLAYLIST></NODE>'
    )
    
    if not folder_parts:
        # No folders — insert at $ROOT
        m = re.search(r'NAME="\$ROOT"><SUBNODES COUNT="(\d+)">', nml_content)
        if not m:
            raise ValueError('Could not find $ROOT SUBNODES COUNT in NML')
        nml_content, insert_pos = _bump_subnodes(nml_content, m)
        return nml_content[:insert_pos] + playlist_node + nml_content[insert_pos:]
    
    # Walk folder path: find existing folders, create missing ones
    # Find the deepest existing folder
    deepest_match = None
    deepest_idx = -1  # index into folder_parts of deepest found folder
    
    for i, folder_name in enumerate(folder_parts):
        m = _find_last_folder(nml_content, folder_name)
        if m:
            deepest_match = m
            deepest_idx = i
        else:
            break
    
    if deepest_idx == len(folder_parts) - 1:
        # All folders exist — just insert the playlist into the deepest one
        nml_content, insert_pos = _bump_subnodes(nml_content, deepest_match)
        return nml_content[:insert_pos] + playlist_node + nml_content[insert_pos:]
    
    # Some folders need to be created. Build the missing folder chain
    # wrapping the playlist from innermost to outermost missing folder.
    node_to_insert = playlist_node
    for i in range(len(folder_parts) - 1, deepest_idx, -1):
        node_to_insert = (
            f'<NODE TYPE="FOLDER" NAME="{folder_parts[i]}">'
            f'<SUBNODES COUNT="1">'
            f'{node_to_insert}'
            f'</SUBNODES></NODE>'
        )
    
    if deepest_idx >= 0:
        # Insert the new folder chain into the deepest existing folder
        nml_content, insert_pos = _bump_subnodes(nml_content, deepest_match)
        return nml_content[:insert_pos] + node_to_insert + nml_content[insert_pos:]
    else:
        # No folders exist at all — insert everything at $ROOT
        m = re.search(r'NAME="\$ROOT"><SUBNODES COUNT="(\d+)">', nml_content)
        if not m:
            raise ValueError('Could not find $ROOT SUBNODES COUNT in NML')
        nml_content, insert_pos = _bump_subnodes(nml_content, m)
        return nml_content[:insert_pos] + node_to_insert + nml_content[insert_pos:]


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Import Rekordbox history playlist into Traktor NML')
    parser.add_argument('--playlist', required=True, help='Name of the HISTORY playlist in the PDB (e.g. "HISTORY 008")')
    parser.add_argument('--name',     default=None,  help='Name to give the playlist in Traktor (defaults to --playlist value)')
    parser.add_argument('--pdb',      default=DEFAULT_PDB, help=f'Path to export.pdb (default: {DEFAULT_PDB})')
    parser.add_argument('--nml',      default=DEFAULT_NML, help=f'Path to collection.nml (default: {DEFAULT_NML})')
    args = parser.parse_args()

    playlist_name = args.name or args.playlist
    pdb_path = str(Path(args.pdb).expanduser())
    nml_path = str(Path(args.nml).expanduser())

    if not Path(pdb_path).exists():
        print(f'Error: PDB not found: {pdb_path}')
        print('Is the USB drive mounted?')
        sys.exit(1)
    if not Path(nml_path).exists():
        print(f'Error: NML not found: {nml_path}')
        sys.exit(1)

    print(f'Reading PDB: {pdb_path}')
    data = read_pdb(pdb_path, args.playlist)
    entries = data['entries']
    print(f'Found {len(entries)} tracks in "{data["playlist"]["name"]}"')

    print(f'Reading NML: {nml_path}')
    with open(nml_path, 'r', encoding='utf-8') as f:
        nml_content = f.read()

    # Check if playlist already exists
    if f'NAME="{playlist_name}"' in nml_content:
        print(f'Warning: playlist "{playlist_name}" already exists in NML — skipping.')
        print('If you want to re-import, remove the existing playlist first.')
        sys.exit(0)

    key_map = build_filename_key_map(nml_content)
    print(f'Collection has {len(key_map)} tracks')

    keys = []
    missing = []
    for entry in entries:
        key = find_key(entry['filename'], key_map)
        if key:
            keys.append(key)
        else:
            missing.append(entry)
            print(f"  WARNING: no match for track {entry['index']}: {entry['artist']} - {entry['title']} ({entry['filename']})")

    print(f'Matched {len(keys)}/{len(entries)} tracks')

    backup = backup_nml(nml_path)
    print(f'Backup saved: {backup}')

    pl_uuid = uuid.uuid4().hex
    new_content = inject_playlist(nml_content, playlist_name, keys, pl_uuid)

    with open(nml_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    # Verify — extract just the playlist name from the path for checking
    check_name = playlist_name.split('/')[-1].strip() if '/' in playlist_name else playlist_name
    if f'NAME="{check_name}"' in new_content:
        print(f'\n✓ Playlist "{playlist_name}" added with {len(keys)} tracks')
        print(f'  UUID: {pl_uuid}')
        if missing:
            print(f'\n  {len(missing)} tracks could not be matched (not in Traktor collection):')
            for e in missing:
                print(f"    - {e['artist']} - {e['title']}")
    else:
        print('ERROR: Verification failed — playlist not found after write')
        sys.exit(1)

    print('\n⚠️  Make sure Traktor is CLOSED when you run this.')
    print('   Open Traktor now to load the playlist.')


if __name__ == '__main__':
    main()
