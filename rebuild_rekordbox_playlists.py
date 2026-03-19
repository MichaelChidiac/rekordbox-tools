#!/usr/bin/env python3.11
"""
rebuild_rekordbox_playlists.py
==============================
Wipes the Rekordbox playlist library and rebuilds it from scratch
from traktor_to_rekordbox.xml.

Writes to:
  • ~/Library/Pioneer/rekordbox/master.db      — djmdPlaylist + djmdSongPlaylist
  • ~/Library/Pioneer/rekordbox/masterPlaylists6.xml  — Rekordbox's display manifest

THIS is the root cause fix: Rekordbox reads masterPlaylists6.xml to determine
which playlists to display. Any playlist only in master.db but NOT in this XML
is invisible in Rekordbox's UI.

Steps:
  1. Back up master.db + masterPlaylists6.xml
  2. Wipe djmdPlaylist + djmdSongPlaylist (track data preserved)
  3. Rebuild playlist tree from XML into master.db
  4. Write fresh masterPlaylists6.xml

Usage:
  python3.11 rebuild_rekordbox_playlists.py [--xml PATH] [--dry-run]
"""

import argparse, datetime, shutil, uuid, zlib, time
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import sqlcipher3 as sqlite3

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH       = Path.home() / "Library/Pioneer/rekordbox/master.db"
MANIFEST_PATH = Path.home() / "Library/Pioneer/rekordbox/masterPlaylists6.xml"
XML_PATH      = Path.home() / "projects/rekordbox-tools/traktor_to_rekordbox.xml"
KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

# ── Helpers ───────────────────────────────────────────────────────────────────
def now_ts():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime('%Y-%m-%d %H:%M:%S.') + f'{now.microsecond//1000:03d} +00:00'

def now_ms():
    return int(time.time() * 1000)

def make_id(s):
    """Stable CRC32-based integer ID from a string."""
    return zlib.crc32(s.encode('utf-8')) & 0xFFFFFFFF

def to_hex(decimal_id):
    """Convert decimal integer ID to uppercase hex string (no 0x prefix)."""
    return format(int(decimal_id), 'X').upper()

def new_uuid():
    return str(uuid.uuid4())

def open_db():
    con = sqlite3.connect(str(DB_PATH))
    con.execute(f"PRAGMA key='{KEY}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")
    con.execute("PRAGMA foreign_keys=OFF")
    return con

def next_usn(con):
    m = 0
    for tbl in ("djmdPlaylist", "djmdContent", "djmdSongPlaylist", "djmdCue"):
        v = con.execute(f"SELECT MAX(rb_local_usn) FROM {tbl}").fetchone()[0]
        if v and v > m:
            m = v
    return m + 1

# ── Step 1: Backup ────────────────────────────────────────────────────────────
def backup():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for src in [DB_PATH, MANIFEST_PATH]:
        if src.exists():
            dst = src.parent / f"{src.name}.backup_{stamp}"
            shutil.copy2(src, dst)
            print(f"  Backed up {src.name} → {dst.name}")

# ── Step 2: Wipe playlists ────────────────────────────────────────────────────
def wipe_playlists(con, dry_run):
    n_pl = con.execute("SELECT COUNT(*) FROM djmdPlaylist").fetchone()[0]
    n_sp = con.execute("SELECT COUNT(*) FROM djmdSongPlaylist").fetchone()[0]
    print(f"  Wiping {n_pl} playlists, {n_sp} song-playlist links …")
    if not dry_run:
        con.execute("DELETE FROM djmdPlaylist")
        con.execute("DELETE FROM djmdSongPlaylist")
        con.commit()
    print("  Done.")

# ── Step 3: Build path → DB track ID map ─────────────────────────────────────
def build_path_map(con):
    return {r[0]: r[1] for r in con.execute("SELECT FolderPath, ID FROM djmdContent").fetchall()}

# ── Step 4: Walk XML and insert playlists ─────────────────────────────────────
def insert_playlists(con, xml_root, path_map, dry_run):
    """
    Walk the XML PLAYLISTS tree, insert every folder and playlist into
    djmdPlaylist + djmdSongPlaylist, and return a list of
    (decimal_id, parent_decimal_id, attribute) for building masterPlaylists6.xml.
    """
    usn      = next_usn(con)
    ts       = now_ts()
    manifest_nodes = []  # (decimal_id, parent_decimal_id, attribute)

    def walk(xml_node, parent_db_id, parent_hex_id, seq_counter):
        """Recursively walk XML NODE elements."""
        children = xml_node.findall('NODE')
        for seq, child in enumerate(children):
            name      = child.get('Name', '')
            node_type = child.get('Type', '1')  # '0'=folder, '1'=playlist
            attribute = 1 if node_type == '0' else 0

            # Stable ID based on full ancestry to avoid collisions
            id_int = make_id(f"{'folder' if attribute==1 else 'playlist'}:{parent_db_id}:{name}")
            hex_id = to_hex(id_int)

            manifest_nodes.append((id_int, parent_db_id, attribute))

            if not dry_run:
                con.execute("""
                    INSERT OR REPLACE INTO djmdPlaylist
                      (ID, Seq, Name, Attribute, ParentID, UUID,
                       rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                       rb_local_usn, created_at, updated_at)
                    VALUES (?,?,?,?,?,?, 0,0,0,0, ?,?,?)
                """, (str(id_int), seq, name, attribute,
                      str(parent_db_id) if parent_db_id != 0 else 'root',
                      new_uuid(), usn, ts, ts))

            if attribute == 0:  # playlist — add tracks
                tracks = child.findall('TRACK')
                for track_seq, t in enumerate(tracks, 1):
                    key_str = t.get('Key', '')
                    db_cid  = path_map.get(key_str)  # Key is file path in our XML
                    if db_cid:
                        sp_id = make_id(f"sp:{id_int}:{track_seq}:{db_cid}")
                        if not dry_run:
                            con.execute("""
                                INSERT OR IGNORE INTO djmdSongPlaylist
                                  (ID, PlaylistID, ContentID, TrackNo, UUID,
                                   rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                                   rb_local_usn, created_at, updated_at)
                                VALUES (?,?,?,?,?, 0,0,0,0, ?,?,?)
                            """, (str(sp_id), str(id_int), str(db_cid), track_seq,
                                  new_uuid(), usn, ts, ts))

            # Recurse into children
            walk(child, id_int, hex_id, 0)

    # The XML root NODE is a wrapper; its children are the actual top-level items
    walk(xml_root, 0, '0', 0)

    if not dry_run:
        con.commit()

    return manifest_nodes, usn

# ── Step 5: Write masterPlaylists6.xml ───────────────────────────────────────
def write_manifest(manifest_nodes, dry_run):
    """Write masterPlaylists6.xml with all playlist nodes."""
    ts_ms = now_ms()

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '',
        '<MASTER_PLAYLIST Version="3.0.0" AutomaticSync="0">',
        '  <PRODUCT Name="rekordbox" Version="6.8.5" Company="Pioneer DJ"/>',
        '  <PLAYLISTS>',
    ]

    for (dec_id, parent_dec_id, attribute) in manifest_nodes:
        hex_id     = to_hex(dec_id)
        parent_hex = to_hex(parent_dec_id) if parent_dec_id != 0 else '0'
        lines.append(
            f'    <NODE Id="{hex_id}" ParentId="{parent_hex}" '
            f'Attribute="{attribute}" Timestamp="{ts_ms}" '
            f'Lib_Type="0" CheckType="0"/>'
        )

    lines += ['  </PLAYLISTS>', '</MASTER_PLAYLIST>', '']

    content = '\n'.join(lines)
    print(f"  Writing {len(manifest_nodes)} nodes to masterPlaylists6.xml …")
    if not dry_run:
        MANIFEST_PATH.write_text(content, encoding='utf-8')
    print("  Done.")

# ── Step 6: Build XML path→track map ─────────────────────────────────────────
def build_xml_path_map(xml_collection, db_path_map):
    """
    Our XML uses TrackID as Key in TRACK elements but the TRACK Location is the path.
    Build a map: TrackID (str) → db content ID.
    """
    tid_to_path = {}
    for t in xml_collection:
        path = unquote(t.get('Location', '').replace('file://localhost', ''))
        tid_to_path[t.get('TrackID')] = path
    return {tid: db_path_map[path] for tid, path in tid_to_path.items() if path in db_path_map}

# ── Summary ───────────────────────────────────────────────────────────────────
def print_summary(con):
    n_pl   = con.execute("SELECT COUNT(*) FROM djmdPlaylist WHERE Attribute=0").fetchone()[0]
    n_fold = con.execute("SELECT COUNT(*) FROM djmdPlaylist WHERE Attribute=1").fetchone()[0]
    n_sp   = con.execute("SELECT COUNT(*) FROM djmdSongPlaylist").fetchone()[0]
    n_tr   = con.execute("SELECT COUNT(*) FROM djmdContent").fetchone()[0]
    print(f"\n  ✅ DB state:")
    print(f"     Playlists:   {n_pl}")
    print(f"     Folders:     {n_fold}")
    print(f"     Track links: {n_sp}")
    print(f"     Tracks:      {n_tr} (unchanged)")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml",     default=str(XML_PATH), help="Path to Rekordbox XML")
    ap.add_argument("--dry-run", action="store_true",   help="Preview without writing")
    args = ap.parse_args()

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Rekordbox playlist rebuild")
    print(f"  XML: {args.xml}")
    print(f"  DB:  {DB_PATH}\n")

    # Parse XML
    xml_path = Path(args.xml)
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    xml_collection = root.find('COLLECTION').findall('TRACK')
    xml_pl_root    = root.find('PLAYLISTS').find('NODE')  # top-level wrapper node

    print("1. Backing up …")
    if not args.dry_run:
        backup()

    con = open_db()
    path_map = build_path_map(con)
    tid_map  = build_xml_path_map(xml_collection, path_map)
    print(f"\n   Track coverage: {len(tid_map)}/{len(xml_collection)} XML tracks matched in DB")

    print("\n2. Wiping existing playlists …")
    wipe_playlists(con, args.dry_run)

    # Patch walk() to use tid_map for TRACK Key lookups (Key = TrackID in XML)
    # We need to override path_map with tid_map
    print("\n3. Inserting playlist tree …")

    usn = next_usn(con)
    ts  = now_ts()
    manifest_nodes = []
    pl_count = fold_count = link_count = 0

    def walk(xml_node, parent_db_id, seq_start=0):
        nonlocal pl_count, fold_count, link_count
        for seq, child in enumerate(xml_node.findall('NODE'), seq_start):
            name      = child.get('Name', '')
            node_type = child.get('Type', '1')
            attribute = 1 if node_type == '0' else 0

            id_int    = make_id(f"{'folder' if attribute==1 else 'playlist'}:{parent_db_id}:{name}")
            parent_str = str(parent_db_id) if parent_db_id != 0 else 'root'

            manifest_nodes.append((id_int, parent_db_id, attribute))

            if not args.dry_run:
                con.execute("""
                    INSERT OR REPLACE INTO djmdPlaylist
                      (ID, Seq, Name, Attribute, ParentID, UUID,
                       rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                       rb_local_usn, created_at, updated_at)
                    VALUES (?,?,?,?,?,?, 0,0,0,0, ?,?,?)
                """, (str(id_int), seq, name, attribute, parent_str,
                      new_uuid(), usn, ts, ts))

            if attribute == 0:
                pl_count += 1
                tracks = child.findall('TRACK')
                for t_seq, t in enumerate(tracks, 1):
                    db_cid = tid_map.get(t.get('Key', ''))
                    if db_cid:
                        link_count += 1
                        sp_id = str(make_id(f"sp:{id_int}:{t_seq}:{db_cid}"))
                        if not args.dry_run:
                            con.execute("""
                                INSERT OR IGNORE INTO djmdSongPlaylist
                                  (ID, PlaylistID, ContentID, TrackNo, UUID,
                                   rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
                                   rb_local_usn, created_at, updated_at)
                                VALUES (?,?,?,?,?, 0,0,0,0, ?,?,?)
                            """, (sp_id, str(id_int), str(db_cid), t_seq,
                                  new_uuid(), usn, ts, ts))
            else:
                fold_count += 1

            walk(child, id_int)

    walk(xml_pl_root, 0)

    if not args.dry_run:
        con.commit()
    print(f"  Inserted {fold_count} folders, {pl_count} playlists, {link_count} track links")

    print("\n4. Writing masterPlaylists6.xml …")
    write_manifest(manifest_nodes, args.dry_run)

    if not args.dry_run:
        print_summary(con)

    con.close()
    print("\nDone. Open Rekordbox — all playlists should now appear.")

if __name__ == '__main__':
    main()
