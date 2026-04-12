#!/usr/bin/env python3.11
"""
traktor_to_rekordbox.py

Converts a Traktor collection.nml to a Rekordbox-importable XML file.

Features:
  - All 10k+ tracks with full metadata (title, artist, album, genre, BPM,
    comment, key, rating, color, dates, file path)
  - All cue points + memory cues (green by default, configurable)
  - Beat grid markers → Rekordbox TEMPO elements
  - Loop cues preserved
  - Full playlist/folder hierarchy preserved
  - Smart playlists evaluated and expanded to regular playlists
  - Traktor track colors mapped to Rekordbox colors

Usage:
    python3.11 traktor_to_rekordbox.py
    python3.11 traktor_to_rekordbox.py --nml ~/path/to/collection.nml --out rekordbox.xml
    python3.11 traktor_to_rekordbox.py --cue-color red   # change default cue color

Import into Rekordbox:
    File → Import Playlist → rekordbox xml → select the output file
"""

import argparse
import html
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from html import unescape
from pathlib import Path

from tag_config import parse_comment_tags

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_NML = str(Path.home() / 'Documents/Native Instruments/Traktor 3.11.1/collection.nml')
DEFAULT_OUT  = str(Path(__file__).parent / 'traktor_to_rekordbox.xml')

# ── Color mappings ────────────────────────────────────────────────────────────

# Traktor color index → Rekordbox decimal color integer (RGB packed)
# Traktor: 0=none, 1=red, 2=orange, 3=yellow, 4=green, 5=blue, 6=violet, 7=magenta
# Extended Traktor values 8-15 are custom; map best-effort
TRAKTOR_TO_RB_COLOR = {
    0:  None,          # none
    1:  16711680,      # red      #FF0000
    2:  16737792,      # orange   #FF6600
    3:  16776960,      # yellow   #FFFF00
    4:  5570304,       # green    #550F00 — actually Rekordbox green is specific
    5:  255,           # blue     #0000FF
    6:  8388736,       # violet   #800080
    7:  16711935,      # magenta  #FF00FF
    # Extended (Traktor non-standard)
    8:  65280,         # bright green #00FF00
    9:  65535,         # cyan     #00FFFF
    10: 16744448,      # amber    #FF8000
    11: 8388608,       # dark red #800000
    12: 32768,         # dark green #008000
    13: 8421376,       # olive    #808000
    14: 128,           # dark blue #000080
    15: 8388736,       # purple   #800080
}

# Better Rekordbox-accurate green (Rekordbox uses this for green label)
TRAKTOR_TO_RB_COLOR[4] = 5635925   # Rekordbox green: #55FF55 approx → actually 0x00CC00 = 52224

# Use proper Rekordbox palette colors (from actual Rekordbox exports)
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

CUE_COLOR_PRESETS = {
    'green':   (0,   204, 0),
    'blue':    (0,   0,   255),
    'red':     (255, 0,   0),
    'orange':  (255, 102, 0),
    'yellow':  (255, 255, 0),
    'cyan':    (0,   204, 255),
    'magenta': (255, 0,   255),
    'white':   (255, 255, 255),
}

# Traktor cue TYPE → Rekordbox POSITION_MARK Type
# 0=cue, 1=fade-in, 2=fade-out, 3=load, 4=grid(skip/tempo), 5=loop
TRAKTOR_CUE_TYPE_TO_RB = {
    0: 0,   # cue → cue
    1: 1,   # fade-in → fade-in
    2: 2,   # fade-out → fade-out
    3: 3,   # load → load
    4: None,# grid → handled as TEMPO, not POSITION_MARK
    5: 4,   # loop → loop
}

# ── NML Parsing ───────────────────────────────────────────────────────────────

def nml_attr(element, *attrs):
    """Get first matching attribute from element, return '' if missing."""
    for a in attrs:
        v = element.get(a, '')
        if v:
            return v
    return ''


def parse_location(loc_el):
    """Build a file:// URI from a LOCATION element."""
    if loc_el is None:
        return ''
    volume = loc_el.get('VOLUME', '')
    dir_   = loc_el.get('DIR', '')
    file_  = loc_el.get('FILE', '')
    # Traktor uses /: as separator; convert to /
    path = (dir_ + file_).replace('/:', '/')
    # Build posix path
    if volume and volume != 'Macintosh HD':
        full = f'/Volumes/{volume}{path}'
    else:
        full = path
    # URL-encode spaces and special chars for file URI
    encoded = full.replace(' ', '%20').replace('&', '%26')
    return f'file://localhost{encoded}'


def parse_tracks(root):
    """
    Parse all ENTRY elements from the NML.
    Returns: dict mapping (volume+dir+file) key → track dict
    """
    tracks = {}  # key → track_dict
    track_id = 1

    collection = root.find('COLLECTION')
    if collection is None:
        return tracks

    for entry in collection.findall('ENTRY'):
        loc = entry.find('LOCATION')
        if loc is None:
            continue

        # Build the Traktor primary key (same format as playlists use)
        vol  = loc.get('VOLUME', '')
        dir_ = loc.get('DIR', '')
        file_ = loc.get('FILE', '')
        traktor_key = f"{vol}{dir_}{file_}"

        info    = entry.find('INFO')
        tempo   = entry.find('TEMPO')
        album   = entry.find('ALBUM')
        loudness = entry.find('LOUDNESS')

        bpm_raw = tempo.get('BPM', '0') if tempo is not None else '0'
        try:
            bpm = f"{float(bpm_raw):.2f}"
        except ValueError:
            bpm = '0.00'

        color_idx = int(entry.get('COLOR', '0') or '0')

        t = {
            'id':           track_id,
            'traktor_key':  traktor_key,
            'title':        entry.get('TITLE', ''),
            'artist':       entry.get('ARTIST', ''),
            'album':        album.get('TITLE', '') if album is not None else '',
            'genre':        info.get('GENRE', '')        if info is not None else '',
            'comment':      info.get('COMMENT', '')      if info is not None else '',
            'key':          info.get('KEY', '')          if info is not None else '',
            'rating':       str(int(info.get('RANKING', '0') or '0') // 51)  # 0-255 → 0-5
                            if info is not None else '0',
            'playtime':     info.get('PLAYTIME', '0')   if info is not None else '0',
            'bitrate':      str(int(info.get('BITRATE', '0') or '0') // 1000)
                            if info is not None else '0',
            'filesize':     info.get('FILESIZE', '0')   if info is not None else '0',
            'import_date':  (info.get('IMPORT_DATE', '') or '').replace('/', '-')
                            if info is not None else '',
            'label':        info.get('LABEL', '')        if info is not None else '',
            'bpm':          bpm,
            'color_idx':    color_idx,
            'rb_color':     TRAKTOR_TO_RB_COLOR.get(color_idx),
            'location':     parse_location(loc),
            'filename':     file_,
            'cues':         [],   # filled in below
            'grid':         [],   # beat grid entries
            'tags':         [],   # [bracket] tags from comment — filled below
        }

        # Extract [bracket] tags from comment field
        t['tags'] = parse_comment_tags(t['comment'])

        # Parse cue points
        for cue in entry.findall('CUE_V2'):
            cue_type_traktor = int(cue.get('TYPE', '0'))
            rb_type = TRAKTOR_CUE_TYPE_TO_RB.get(cue_type_traktor)

            start_raw = float(cue.get('START', '0'))
            start_sec = start_raw / 1000.0  # Traktor stores ms

            if cue_type_traktor == 4:
                # Grid marker → TEMPO
                t['grid'].append({
                    'start': f"{start_sec:.3f}",
                    'bpm':   bpm,
                })
                continue

            if rb_type is None:
                continue

            hotcue = int(cue.get('HOTCUE', '-1'))
            name   = cue.get('NAME', '')
            len_raw = float(cue.get('LEN', '0'))

            c = {
                'name':    name,
                'type':    rb_type,
                'start':   f"{start_sec:.3f}",
                'num':     str(hotcue),  # -1 = memory cue
            }
            if cue_type_traktor == 5:  # loop
                c['end'] = f"{(start_sec + len_raw / 1000.0):.3f}"

            t['cues'].append(c)

        tracks[traktor_key] = t
        track_id += 1

    print(f"  Parsed {len(tracks)} tracks, "
          f"{sum(len(t['cues']) for t in tracks.values())} cue points, "
          f"{sum(len(t['grid']) for t in tracks.values())} grid markers")
    return tracks


# ── Smart Playlist Evaluator ──────────────────────────────────────────────────

def make_track_lookup(tracks):
    """Build a lookup dict for smartlist evaluation."""
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
    Supports: $FIELD % "value" (contains), $FIELD == "value", != > < >= <=
              & (AND), | (OR), ! (NOT expr)
    """
    # Unescape HTML entities from XML
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
                if s[i] == '=' and (tokens and tokens[-1] in ('>', '<', '!')):
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
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume():
        t = tokens[pos[0]]; pos[0] += 1; return t

    def parse_expr():
        return parse_or()

    def parse_or():
        left = parse_and()
        while peek() == '|':
            consume()
            right = parse_and()
            left = left or right
        return left

    def parse_and():
        left = parse_not()
        while peek() == '&':
            consume()
            right = parse_not()
            left = left and right
        return left

    def parse_not():
        if peek() == '!':
            consume()
            return not parse_atom()
        return parse_atom()

    def parse_atom():
        if peek() == '(':
            consume()
            val = parse_expr()
            if peek() == ')':
                consume()
            return val

        # $FIELD OP "value"
        tok = peek()
        if tok and tok.startswith('$'):
            field = consume()[1:]  # strip $
            op    = consume()
            val   = consume().lower()
            fv    = track_fields.get(field, '').lower()

            if op == '%':    return val in fv
            if op == '==':   return fv == val
            if op == '!=':   return fv != val
            if op == '>':    return fv > val
            if op == '<':    return fv < val
            if op == '>=':   return fv >= val
            if op == '<=':   return fv <= val
        return False

    try:
        return parse_expr()
    except Exception:
        return False


def expand_smartlist(query_raw: str, track_lookup: dict) -> list:
    """Return list of traktor_keys matching the smartlist query."""
    return [key for key, fields in track_lookup.items()
            if eval_smartlist_query(query_raw, fields)]


# ── Playlist Tree Parsing ─────────────────────────────────────────────────────

def parse_playlist_tree(root, tracks, track_lookup):
    """
    Parse the PLAYLISTS NODE tree from the NML.
    Returns a nested structure: list of node dicts.
    Each node: {type, name, children} or {type, name, keys}
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
                return {'type': 'playlist', 'name': name + ' [smart]', 'keys': [], 'smart': True}
            se = sl_el.find('SEARCH_EXPRESSION')
            query = se.get('QUERY', '') if se is not None else ''
            if query:
                keys = expand_smartlist(query, track_lookup)
                stats['smart_expanded'] += 1
            else:
                keys = []
            return {'type': 'playlist', 'name': name, 'keys': keys, 'smart': True}

        return None

    # Walk children of $ROOT
    result = []
    subnodes = root_node.find('SUBNODES')
    if subnodes is not None:
        for child in subnodes.findall('NODE'):
            node = walk(child)
            if node:
                result.append(node)

    print(f"  Parsed {stats['folders']} folders, {stats['playlists']} playlists, "
          f"{stats['smartlists']} smartlists ({stats['smart_expanded']} expanded)")
    return result


# ── Rekordbox XML Builder ─────────────────────────────────────────────────────

def xml_escape(s):
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;'))


def build_rekordbox_xml(tracks: dict, playlist_tree: list, cue_rgb: tuple) -> str:
    r, g, b = cue_rgb
    lines = []

    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<DJ_PLAYLISTS Version="1.0.0">')
    lines.append('  <PRODUCT Name="rekordbox" Version="6.8.5" Company="AlphaTheta"/>')

    # ── COLLECTION ───────────────────────────────────────────────────────────
    track_list = list(tracks.values())
    lines.append(f'  <COLLECTION Entries="{len(track_list)}">')

    for t in track_list:
        color_attr = f' Colour="{t["rb_color"]}"' if t['rb_color'] is not None else ''
        # Determine file kind
        loc = t['location']
        if loc.endswith('.mp3'):    kind = 'MP3 File'
        elif loc.endswith('.flac'): kind = 'FLAC File'
        elif loc.endswith('.aiff') or loc.endswith('.aif'): kind = 'AIFF File'
        elif loc.endswith('.wav'):  kind = 'WAV File'
        elif loc.endswith('.m4a'):  kind = 'M4A File'
        else:                       kind = 'Unknown'

        lines.append(
            f'    <TRACK TrackID="{t["id"]}"'
            f' Name="{xml_escape(t["title"])}"'
            f' Artist="{xml_escape(t["artist"])}"'
            f' Album="{xml_escape(t["album"])}"'
            f' Genre="{xml_escape(t["genre"])}"'
            f' Kind="{kind}"'
            f' Size="{t["filesize"]}"'
            f' TotalTime="{t["playtime"]}"'
            f' DiscNumber="0"'
            f' TrackNumber="0"'
            f' AverageBpm="{t["bpm"]}"'
            f' DateAdded="{t["import_date"]}"'
            f' BitRate="{t["bitrate"]}"'
            f' Comments="{xml_escape(t["comment"])}"'
            f' PlayCount="0"'
            f' Rating="{t["rating"]}"'
            f' Location="{xml_escape(t["location"])}"'
            f' Remixer=""'
            f' Tonality="{xml_escape(t["key"])}"'
            f' Label="{xml_escape(t["label"])}"'
            f'{color_attr}>'
        )

        # Beat grid (first grid marker = tempo)
        if t['grid']:
            g_entry = t['grid'][0]
            lines.append(
                f'      <TEMPO Inizio="{g_entry["start"]}"'
                f' Bpm="{t["bpm"]}"'
                f' Metro="4/4" Battito="1"/>'
            )
        else:
            # Always write a TEMPO entry if we have BPM
            if t['bpm'] != '0.00':
                lines.append(f'      <TEMPO Inizio="0.000" Bpm="{t["bpm"]}" Metro="4/4" Battito="1"/>')

        # Cue points
        for cue in t['cues']:
            num = cue['num']
            # Memory cues get Num="-1", hot cues get their slot number
            if cue['type'] == 4:  # loop
                end_attr = f' End="{cue["end"]}"' if 'end' in cue else ''
                lines.append(
                    f'      <POSITION_MARK'
                    f' Name="{xml_escape(cue["name"])}"'
                    f' Type="4"'
                    f' Start="{cue["start"]}"'
                    f'{end_attr}'
                    f' Num="{num}"'
                    f' Red="{r}" Green="{g}" Blue="{b}"/>'
                )
            else:
                lines.append(
                    f'      <POSITION_MARK'
                    f' Name="{xml_escape(cue["name"])}"'
                    f' Type="{cue["type"]}"'
                    f' Start="{cue["start"]}"'
                    f' Num="{num}"'
                    f' Red="{r}" Green="{g}" Blue="{b}"/>'
                )

        lines.append('    </TRACK>')

    lines.append('  </COLLECTION>')

    # ── PLAYLISTS ─────────────────────────────────────────────────────────────
    # Build track key → TrackID map
    key_to_id = {t['traktor_key']: t['id'] for t in track_list}

    lines.append('  <PLAYLISTS>')
    lines.append('    <NODE Type="0" Name="ROOT" Count="{}">'
                 .format(len(playlist_tree)))

    def write_node(node, indent):
        pad = '  ' * indent
        if node['type'] == 'folder':
            lines.append(f'{pad}<NODE Type="0" Name="{xml_escape(node["name"])}" Count="{len(node["children"])}">')
            for child in node['children']:
                write_node(child, indent + 1)
            lines.append(f'{pad}</NODE>')
        elif node['type'] == 'playlist':
            valid_keys = [k for k in node['keys'] if k in key_to_id]
            lines.append(
                f'{pad}<NODE Type="1" Name="{xml_escape(node["name"])}"'
                f' Entries="{len(valid_keys)}" KeyType="0" Rows="{len(valid_keys)}">'
            )
            for k in valid_keys:
                lines.append(f'{pad}  <TRACK Key="{key_to_id[k]}"/>')
            lines.append(f'{pad}</NODE>')

    for node in playlist_tree:
        write_node(node, 3)

    lines.append('    </NODE>')
    lines.append('  </PLAYLISTS>')
    lines.append('</DJ_PLAYLISTS>')

    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Convert Traktor NML to Rekordbox XML')
    parser.add_argument('--nml', default=DEFAULT_NML,
                        help=f'Path to collection.nml (default: {DEFAULT_NML})')
    parser.add_argument('--out', default=DEFAULT_OUT,
                        help=f'Output XML path (default: {DEFAULT_OUT})')
    parser.add_argument('--cue-color', default='green',
                        choices=list(CUE_COLOR_PRESETS.keys()),
                        help='Default color for all cue points (default: green)')
    args = parser.parse_args()

    nml_path = Path(args.nml).expanduser()
    out_path  = Path(args.out).expanduser()
    cue_rgb   = CUE_COLOR_PRESETS[args.cue_color]

    if not nml_path.exists():
        print(f"Error: NML not found: {nml_path}")
        sys.exit(1)

    print(f"Reading {nml_path} ...")
    content = nml_path.read_text(encoding='utf-8')

    print("Parsing NML XML...")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"XML parse error: {e}")
        sys.exit(1)

    print("Parsing tracks & cues...")
    tracks = parse_tracks(root)

    print("Building track lookup for smartlists...")
    track_lookup = make_track_lookup(tracks)

    print("Parsing playlist tree (+ evaluating smartlists)...")
    playlist_tree = parse_playlist_tree(root, tracks, track_lookup)

    print(f"Building Rekordbox XML (cue color: {args.cue_color} {cue_rgb})...")
    xml_output = build_rekordbox_xml(tracks, playlist_tree, cue_rgb)

    out_path.write_text(xml_output, encoding='utf-8')
    size_mb = out_path.stat().st_size / 1_000_000

    print(f"\n✓ Written to: {out_path} ({size_mb:.1f} MB)")
    print(f"\nImport into Rekordbox:")
    print(f"  File → Import Playlist → rekordbox xml → {out_path}")


if __name__ == '__main__':
    main()
