#!/usr/bin/env python3.11
"""
write_pdb.py — Convert exportLibrary.db (SQLCipher) to export.pdb (Pioneer DeviceSQL binary)

Rekordbox desktop reads export.pdb (binary Pioneer format), not exportLibrary.db.
This script generates export.pdb from the SQLCipher database after USB export.

Usage:
    python3.11 write_pdb.py /Volumes/MYUSB
    python3.11 write_pdb.py /Volumes/MYUSB --dry-run
    python3.11 write_pdb.py "/Volumes/PATRIOT 2" --dry-run
"""

import argparse
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path

import sqlcipher3

# ── Constants ──────────────────────────────────────────────────────────────────

SQLCIPHER_KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

PAGE_SIZE = 4096
HEADER_SIZE = 40  # bytes at start of every page
NUM_TABLES = 20
ROW_GROUP_SIZE = 36  # bytes per row group at end of page
ROWS_PER_GROUP = 16

# Table type constants
TRACKS          = 0
GENRES          = 1
ARTISTS         = 2
ALBUMS          = 3
LABELS          = 4
KEYS            = 5
COLORS          = 6
PLAYLIST_TREE   = 7
PLAYLIST_ENTRIES = 8
UNK9            = 9
UNK10           = 10
HIST_PLAYLISTS  = 11
HIST_ENTRIES    = 12
ARTWORK         = 13
UNK14           = 14
UNK15           = 15
COLUMNS         = 16
UNK17           = 17
UNK18           = 18
HISTORY         = 19

TABLE_NAMES = [
    "Tracks", "Genres", "Artists", "Albums", "Labels", "Keys", "Colors",
    "PlaylistTree", "PlaylistEntries", "Unk9", "Unk10",
    "HistPlaylists", "HistEntries", "Artwork", "Unk14",
    "Unk15", "Columns", "Unk17", "Unk18", "History",
]

COLOR_NAMES = {
    1: "Pink", 2: "Red", 3: "Orange", 4: "Yellow",
    5: "Green", 6: "Aqua", 7: "Blue", 8: "Purple",
}


# ── DeviceSQL String Encoding ─────────────────────────────────────────────────

def encode_devicesql_string(text: str) -> bytes:
    """Encode a string in Pioneer DeviceSQL format.

    Short ASCII:  1-byte header + ASCII bytes   (strings ≤ 126 chars, ASCII-safe)
    Long ASCII:   0x40 + u2le(len+4) + u1(0) + ASCII bytes
    Long UTF-16:  0x90 + u2le(len+4) + u1(0) + UTF-16LE bytes
    """
    if not text:
        # Empty string: length_and_kind = (0 + 1) << 1 | 1 = 3
        return b"\x03"

    try:
        text_bytes = text.encode("ascii")
    except UnicodeEncodeError:
        # Non-ASCII → Long UTF-16LE (0x90)
        # Format: 0x90 + u2le(len_bytes + 4) + u1(0) + utf16le_bytes
        utf16 = text.encode("utf-16-le")
        return b"\x90" + struct.pack("<H", len(utf16) + 4) + b"\x00" + utf16

    if len(text_bytes) <= 126:
        # Short ASCII: length_and_kind = (len + 1) << 1 | 1
        lak = ((len(text_bytes) + 1) << 1) | 1
        return bytes([lak]) + text_bytes
    else:
        # Long ASCII (0x40)
        # Format: 0x40 + u2le(len_bytes + 4) + u1(0) + ascii_bytes
        return b"\x40" + struct.pack("<H", len(text_bytes) + 4) + b"\x00" + text_bytes


# ── Row Serializers ────────────────────────────────────────────────────────────

def serialize_color_row(color_id: int, color_code: int, name: str) -> bytes:
    """Type 6: ColorRow — 4 zero bytes + color_code(u1) + id(u2le) + pad(u1) + name."""
    data = bytearray(4)                                # 4 bytes padding
    data.append(color_code & 0xFF)                     # color code (u1)
    data.extend(struct.pack("<H", color_id))           # id (u2le)
    data.append(0)                                     # padding byte
    data.extend(encode_devicesql_string(name))
    return bytes(data)


def serialize_genre_row(genre_id: int, name: str) -> bytes:
    """Type 1: GenreRow — id(u4le) + name."""
    return struct.pack("<I", genre_id) + encode_devicesql_string(name)


def serialize_label_row(label_id: int, name: str) -> bytes:
    """Type 4: LabelRow — id(u4le) + name."""
    return struct.pack("<I", label_id) + encode_devicesql_string(name)


def serialize_artwork_row(art_id: int, path: str) -> bytes:
    """Type 13: ArtworkRow — id(u4le) + path."""
    return struct.pack("<I", art_id) + encode_devicesql_string(path)


def serialize_key_row(key_id: int, name: str) -> bytes:
    """Type 5: KeyRow — id(u4le) + id2(u4le) + name."""
    return struct.pack("<II", key_id, key_id) + encode_devicesql_string(name)


def serialize_artist_row(artist_id: int, name: str, index_shift: int = 0) -> bytes:
    """Type 2: ArtistRow — subtype(u2) + shift(u2) + id(u4) + unk(u1) + ofsName(u1) + name."""
    ofs_name = 10  # string starts right after the 10-byte fixed part
    data = struct.pack("<HH", 0x0060, index_shift)
    data += struct.pack("<I", artist_id)
    data += bytes([3, ofs_name])  # unk=3 (matches reference), offset to name
    data += encode_devicesql_string(name)
    return data


def serialize_album_row(album_id: int, name: str, artist_id: int = 0,
                        index_shift: int = 0) -> bytes:
    """Type 3: AlbumRow — subtype + shift + unk + artistId + id + unk + pad + ofsName + name."""
    ofs_name = 22  # 22 bytes of fixed fields
    data = struct.pack("<HH", 0x0080, index_shift)
    data += struct.pack("<I", 0)          # unknown
    data += struct.pack("<I", artist_id)
    data += struct.pack("<I", album_id)
    data += struct.pack("<I", 0)          # unknown
    data += bytes([3, ofs_name])
    data += encode_devicesql_string(name)
    return data


def serialize_playlist_tree_row(pl_id: int, parent_id: int, sort_order: int,
                                raw_is_folder: int, name: str) -> bytes:
    """Type 7: PlaylistTreeRow — parentId + pad + sortOrder + id + rawIsFolder + name."""
    data = struct.pack("<I", parent_id)
    data += b"\x00\x00\x00\x00"         # 4 bytes padding
    data += struct.pack("<I", sort_order)
    data += struct.pack("<I", pl_id)
    data += struct.pack("<I", raw_is_folder)
    data += encode_devicesql_string(name)
    return data


def serialize_playlist_entry_row(entry_index: int, track_id: int,
                                 playlist_id: int) -> bytes:
    """Type 8: PlaylistEntryRow — entryIndex(u4) + trackId(u4) + playlistId(u4)."""
    return struct.pack("<III", entry_index, track_id, playlist_id)


def serialize_track_row(t: dict) -> bytes:
    """Type 0: TrackRow — 94 bytes fixed + 42 bytes string offsets + string data.

    `t` is a dict with all required track fields.
    """
    # ── Fixed fields (94 bytes before string offsets) ──────────────────────
    fixed = bytearray()
    fixed.extend(struct.pack("<H", 0x0024))   # _unnamed0 (subtype)
    fixed.extend(struct.pack("<H", t.get("indexShift", 0)))
    fixed.extend(struct.pack("<I", t.get("bitmask", 0)))
    fixed.extend(struct.pack("<I", t.get("sampleRate", 44100)))
    fixed.extend(struct.pack("<I", t.get("composerId", 0)))
    fixed.extend(struct.pack("<I", t.get("fileSize", 0)))
    fixed.extend(struct.pack("<I", 0))        # _unnamed6
    fixed.extend(struct.pack("<H", 0))        # _unnamed7
    fixed.extend(struct.pack("<H", 0))        # _unnamed8
    fixed.extend(struct.pack("<I", t.get("artworkId", 0)))
    fixed.extend(struct.pack("<I", t.get("keyId", 0)))
    fixed.extend(struct.pack("<I", t.get("originalArtistId", 0)))
    fixed.extend(struct.pack("<I", t.get("labelId", 0)))
    fixed.extend(struct.pack("<I", t.get("remixerId", 0)))
    fixed.extend(struct.pack("<I", t.get("bitrate", 0)))
    fixed.extend(struct.pack("<I", t.get("trackNumber", 0)))
    fixed.extend(struct.pack("<I", t.get("tempo", 0)))
    fixed.extend(struct.pack("<I", t.get("genreId", 0)))
    fixed.extend(struct.pack("<I", t.get("albumId", 0)))
    fixed.extend(struct.pack("<I", t.get("artistId", 0)))
    fixed.extend(struct.pack("<I", t.get("id", 0)))
    fixed.extend(struct.pack("<H", t.get("discNumber", 0)))
    fixed.extend(struct.pack("<H", t.get("playCount", 0)))
    fixed.extend(struct.pack("<H", t.get("year", 0)))
    fixed.extend(struct.pack("<H", t.get("sampleDepth", 16)))
    fixed.extend(struct.pack("<H", t.get("duration", 0)))
    fixed.extend(struct.pack("<H", 0))        # _unnamed26
    fixed.append(t.get("colorId", 0) & 0xFF)  # colorId (u1)
    fixed.append(t.get("rating", 0) & 0xFF)   # rating (u1)
    fixed.extend(struct.pack("<H", 0))        # _unnamed29
    fixed.extend(struct.pack("<H", 0))        # _unnamed30
    assert len(fixed) == 94

    # ── String fields (21 fields) ──────────────────────────────────────────
    STRING_FIELDS = [
        "isrc", "texter", "unknownString2", "unknownString3", "unknownString4",
        "message", "kuvoPublic", "autoloadHotcues", "unknownString5", "unknownString6",
        "dateAdded", "releaseDate", "mixName", "unknownString7", "analyzePath",
        "analyzeDate", "comment", "title", "unknownString8", "filename", "filePath",
    ]

    # Pre-encode all strings
    encoded_strings = []
    for field_name in STRING_FIELDS:
        encoded_strings.append(encode_devicesql_string(t.get(field_name, "")))

    # Calculate offsets: string data starts at byte 136 (94 fixed + 42 offsets)
    STRINGS_START = 94 + 21 * 2  # = 136
    assert STRINGS_START == 136

    string_offsets = []
    running_offset = STRINGS_START
    for enc in encoded_strings:
        string_offsets.append(running_offset)
        running_offset += len(enc)

    # ── Build offset array (42 bytes) ──────────────────────────────────────
    ofs_bytes = bytearray()
    for ofs in string_offsets:
        ofs_bytes.extend(struct.pack("<H", ofs))
    assert len(ofs_bytes) == 42

    # ── Combine ────────────────────────────────────────────────────────────
    result = bytes(fixed) + bytes(ofs_bytes)
    for enc in encoded_strings:
        result += enc
    return result


# ── PDB Page Builder ──────────────────────────────────────────────────────────

class PdbWriter:
    """Builds a complete export.pdb file from serialized row data."""

    def __init__(self):
        self.pages: list[bytearray] = []
        self.table_info: list[dict] = []  # one per table type (0-19)

    def _alloc_page(self) -> tuple[int, bytearray]:
        """Allocate a new blank page, return (index, page_buffer)."""
        idx = len(self.pages)
        page = bytearray(PAGE_SIZE)
        self.pages.append(page)
        return idx, page

    @staticmethod
    def _write_page_header(page: bytearray, page_idx: int, table_type: int,
                           next_page: int, *, unk10: int = 0, nrows: int = 0,
                           unk1a: int = 0, flags: int = 0, free_size: int = 0,
                           used_size: int = 0, unk20: int = 0,
                           nrows_large: int = 0, unk24: int = 0, unk26: int = 0):
        """Write the 40-byte page header."""
        struct.pack_into("<I", page, 0x00, 0)            # gap
        struct.pack_into("<I", page, 0x04, page_idx)
        struct.pack_into("<I", page, 0x08, table_type)
        struct.pack_into("<I", page, 0x0C, next_page)
        struct.pack_into("<I", page, 0x10, unk10)
        struct.pack_into("<I", page, 0x14, 0)
        page[0x18] = nrows & 0xFF
        page[0x19] = 0
        page[0x1A] = unk1a & 0xFF
        page[0x1B] = flags & 0xFF
        struct.pack_into("<H", page, 0x1C, free_size & 0xFFFF)
        struct.pack_into("<H", page, 0x1E, used_size & 0xFFFF)
        struct.pack_into("<H", page, 0x20, unk20 & 0xFFFF)
        struct.pack_into("<H", page, 0x22, nrows_large & 0xFFFF)
        struct.pack_into("<H", page, 0x24, unk24 & 0xFFFF)
        struct.pack_into("<H", page, 0x26, unk26 & 0xFFFF)

    def _build_data_page(self, rows_data: list[bytes], table_type: int,
                         page_counter: int) -> bytearray:
        """Build a single data page from serialized rows, return page buffer."""
        page = bytearray(PAGE_SIZE)
        nrows = len(rows_data)
        num_groups = (nrows + ROWS_PER_GROUP - 1) // ROWS_PER_GROUP

        # ── Write row data into heap (starts at offset 40) ────────────────
        heap_pos = HEADER_SIZE
        row_offsets: list[int] = []

        for row in rows_data:
            offset_from_heap = heap_pos - HEADER_SIZE
            row_offsets.append(offset_from_heap)
            page[heap_pos:heap_pos + len(row)] = row
            # 4-byte alignment
            heap_pos += (len(row) + 3) & ~3

        used_size = heap_pos - HEADER_SIZE
        data_capacity = PAGE_SIZE - HEADER_SIZE - num_groups * ROW_GROUP_SIZE
        free_size = max(0, data_capacity - used_size)

        # ── Write row groups at end of page (growing backward) ────────────
        for g in range(num_groups):
            grp_offset = PAGE_SIZE - (g + 1) * ROW_GROUP_SIZE
            present_flags = 0

            for r in range(ROWS_PER_GROUP):
                row_global = g * ROWS_PER_GROUP + r
                if row_global < nrows:
                    # Slot (15 - r) stores row r's offset (reverse order)
                    slot_pos = grp_offset + (15 - r) * 2
                    struct.pack_into("<H", page, slot_pos, row_offsets[row_global])
                    present_flags |= (1 << r)

            # Flags and padding at end of group
            struct.pack_into("<H", page, grp_offset + 32, present_flags)
            struct.pack_into("<H", page, grp_offset + 34, present_flags)

        # ── Page header ───────────────────────────────────────────────────
        page_flags = 0x34 if nrows > ROWS_PER_GROUP else 0x24
        # numRowsSmall is u1 (max 255); for larger counts, the parser uses
        # numRowsLarge when numRowsLarge > numRowsSmall && numRowsLarge != 8191
        nrows_large = nrows if nrows > 255 else 0
        self._write_page_header(
            page, 0, table_type, 0,  # page_idx and next_page set later
            unk10=page_counter,
            nrows=nrows,
            unk1a=1 if nrows > 0 else 0,
            flags=page_flags,
            free_size=free_size,
            used_size=used_size,
            unk20=nrows if nrows <= 255 else 0,
            nrows_large=nrows_large,
        )
        return page

    def _pack_rows_into_pages(self, rows_data: list[bytes],
                              table_type: int) -> list[bytearray]:
        """Pack serialized rows into one or more data pages."""
        if not rows_data:
            return []

        pages: list[bytearray] = []
        current_rows: list[bytes] = []
        current_used = 0

        for row in rows_data:
            padded = (len(row) + 3) & ~3
            new_count = len(current_rows) + 1
            new_groups = (new_count + ROWS_PER_GROUP - 1) // ROWS_PER_GROUP
            capacity = PAGE_SIZE - HEADER_SIZE - new_groups * ROW_GROUP_SIZE

            if current_used + padded > capacity:
                # Current page is full — emit it
                if current_rows:
                    pages.append(self._build_data_page(
                        current_rows, table_type, len(pages) + 2))
                current_rows = [row]
                current_used = padded
            else:
                current_rows.append(row)
                current_used += padded

        if current_rows:
            pages.append(self._build_data_page(
                current_rows, table_type, len(pages) + 2))

        return pages

    def write_table(self, table_type: int, rows_data: list[bytes]):
        """Write a complete table (header + data pages).

        Appends to self.pages and records table info for the file header.
        """
        header_idx, header_page = self._alloc_page()

        if not rows_data:
            # ── Empty table: header + empty sentinel page ─────────────────
            empty_idx, empty_page = self._alloc_page()
            self._write_page_header(
                header_page, header_idx, table_type, empty_idx,
                unk10=1, flags=0x64, unk24=1004,
                unk20=0x1FFF, nrows_large=0x1FFF,
            )
            # Minimal sentinel page (type & index only)
            struct.pack_into("<I", empty_page, 0x04, empty_idx)
            struct.pack_into("<I", empty_page, 0x08, table_type)

            self.table_info.append({
                "type": table_type,
                "empty_candidate": empty_idx,
                "first_page": header_idx,
                "last_page": header_idx,
            })
            return

        # ── Populated table ───────────────────────────────────────────────
        data_pages = self._pack_rows_into_pages(rows_data, table_type)

        # Allocate data pages
        page_indices: list[int] = []
        for dp in data_pages:
            idx, page_buf = self._alloc_page()
            page_buf[:] = dp
            page_indices.append(idx)

        # Set page indices and link chain
        for i, pidx in enumerate(page_indices):
            page_buf = self.pages[pidx]
            struct.pack_into("<I", page_buf, 0x04, pidx)  # page index
            if i + 1 < len(page_indices):
                struct.pack_into("<I", page_buf, 0x0C, page_indices[i + 1])
            # Last page's next_page is set after all tables are allocated

        # Write header page
        first_data = page_indices[0]
        self._write_page_header(
            header_page, header_idx, table_type, first_data,
            unk10=1, flags=0x64, unk24=1004,
            unk20=0x1FFF, nrows_large=0x1FFF,
        )

        last_data = page_indices[-1]
        self.table_info.append({
            "type": table_type,
            "empty_candidate": -1,  # placeholder, set in finalize
            "first_page": header_idx,
            "last_page": last_data,
            "_data_page_indices": page_indices,
        })

    def finalize(self) -> bytes:
        """Build file header (page 0) and finalize all page links.

        Returns the complete PDB file as bytes.
        """
        # Determine next_unused page (for empty_candidate pointers)
        next_unused = len(self.pages)

        # Fix up empty_candidate and last-page next_page links
        for info in self.table_info:
            if info["empty_candidate"] == -1:
                # Populated table — empty_candidate = next_unused
                info["empty_candidate"] = next_unused
                next_unused += 1

                # Set last data page's next_page to its empty_candidate
                dp_indices = info.get("_data_page_indices", [])
                if dp_indices:
                    last_pg = self.pages[dp_indices[-1]]
                    struct.pack_into("<I", last_pg, 0x0C, info["empty_candidate"])

        # Build page 0 (file header)
        page0 = bytearray(PAGE_SIZE)
        struct.pack_into("<I", page0, 0x00, 0)             # padding
        struct.pack_into("<I", page0, 0x04, PAGE_SIZE)      # page size
        struct.pack_into("<I", page0, 0x08, NUM_TABLES)     # num tables
        struct.pack_into("<I", page0, 0x0C, next_unused)    # next unused page
        struct.pack_into("<I", page0, 0x10, 5)              # unknown (always 5)
        struct.pack_into("<I", page0, 0x14, 0)              # sequence
        struct.pack_into("<I", page0, 0x18, 0)              # gap

        # Table pointers: 20 × 16 bytes
        for i, info in enumerate(self.table_info):
            off = 0x1C + i * 16
            struct.pack_into("<I", page0, off + 0, info["type"])
            struct.pack_into("<I", page0, off + 4, info["empty_candidate"])
            struct.pack_into("<I", page0, off + 8, info["first_page"])
            struct.pack_into("<I", page0, off + 12, info["last_page"])

        # Page 0 is always index 0 — update it
        self.pages[0][:] = page0

        return b"".join(bytes(p) for p in self.pages)


# ── Database Reading ──────────────────────────────────────────────────────────

def open_export_db(db_path: Path):
    """Open the SQLCipher-encrypted exportLibrary.db (read-only)."""
    con = sqlcipher3.connect(str(db_path), flags=sqlcipher3.SQLITE_OPEN_READONLY)
    con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")
    return con


def safe_int(val, default: int = 0) -> int:
    """Convert a string or None to int, clamped to u4le range."""
    if val is None or val == "":
        return default
    try:
        v = int(val)
        return v & 0xFFFFFFFF  # clamp to u4le
    except (ValueError, TypeError):
        return default


def safe_int16(val, default: int = 0) -> int:
    """Convert to int, clamped to u2le range."""
    return safe_int(val, default) & 0xFFFF


def fix_analyze_path(path: str) -> str:
    """Convert artwork paths to ANLZ paths if needed.

    Some tracks have '/PIONEER/Artwork/xxx/uuid/artwork.jpg' instead of
    '/PIONEER/USBANLZ/xxx/uuid/ANLZ0000.DAT'. Fix those.
    """
    if not path:
        return ""
    if "ANLZ" in path:
        return path
    if "/Artwork/" in path:
        # /PIONEER/Artwork/xxx/uuid/artwork.jpg → /PIONEER/USBANLZ/xxx/uuid/ANLZ0000.DAT
        parts = path.split("/")
        # Find "Artwork" and replace with "USBANLZ"
        try:
            idx = parts.index("Artwork")
            parts[idx] = "USBANLZ"
            # Replace filename with ANLZ0000.DAT
            parts[-1] = "ANLZ0000.DAT"
            return "/".join(parts)
        except ValueError:
            return ""
    return ""


def read_export_db(db_path: Path) -> dict:
    """Read all tables from exportLibrary.db, return structured data."""
    con = open_export_db(db_path)

    data = {}

    # ── Colors ────────────────────────────────────────────────────────────
    colors = []
    for row in con.execute("SELECT ID, ColorCode, SortKey, Commnt FROM djmdColor "
                           "WHERE rb_local_deleted=0 ORDER BY CAST(ID AS INTEGER)"):
        cid = safe_int(row[0])
        code = row[2] if row[2] else cid  # SortKey is the 1-8 color code
        name = row[3] if row[3] else COLOR_NAMES.get(code, "")
        colors.append({"id": cid, "code": code, "name": name})
    data["colors"] = colors

    # ── Genres ────────────────────────────────────────────────────────────
    genres = []
    for row in con.execute("SELECT ID, Name FROM djmdGenre "
                           "WHERE rb_local_deleted=0 ORDER BY CAST(ID AS INTEGER)"):
        genres.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["genres"] = genres

    # ── Artists ───────────────────────────────────────────────────────────
    artists = []
    for row in con.execute("SELECT ID, Name FROM djmdArtist "
                           "WHERE rb_local_deleted=0 ORDER BY CAST(ID AS INTEGER)"):
        artists.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["artists"] = artists

    # ── Albums ────────────────────────────────────────────────────────────
    albums = []
    for row in con.execute("SELECT ID, Name, AlbumArtistID FROM djmdAlbum "
                           "WHERE rb_local_deleted=0 ORDER BY CAST(ID AS INTEGER)"):
        albums.append({
            "id": safe_int(row[0]),
            "name": row[1] or "",
            "artistId": safe_int(row[2]),
        })
    data["albums"] = albums

    # ── Labels ────────────────────────────────────────────────────────────
    labels = []
    for row in con.execute("SELECT ID, Name FROM djmdLabel "
                           "WHERE rb_local_deleted=0 ORDER BY CAST(ID AS INTEGER)"):
        labels.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["labels"] = labels

    # ── Keys ──────────────────────────────────────────────────────────────
    keys = []
    for row in con.execute("SELECT ID, ScaleName FROM djmdKey "
                           "WHERE rb_local_deleted=0 ORDER BY CAST(ID AS INTEGER)"):
        keys.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["keys"] = keys

    # ── Artwork (from imageFile if available) ─────────────────────────────
    artwork = []
    try:
        for row in con.execute("SELECT ID, Path FROM imageFile "
                               "WHERE rb_local_deleted=0 AND Path IS NOT NULL "
                               "AND Path != '' ORDER BY CAST(ID AS INTEGER)"):
            artwork.append({"id": safe_int(row[0]), "path": row[1] or ""})
    except Exception:
        pass  # table might not exist or be empty
    data["artwork"] = artwork

    # ── Playlists ─────────────────────────────────────────────────────────
    playlists = []
    for row in con.execute("SELECT ID, Name, ParentID, Seq, Attribute "
                           "FROM djmdPlaylist WHERE rb_local_deleted=0 "
                           "ORDER BY ParentID, Seq"):
        parent = row[2] or ""
        parent_id = 0 if parent == "root" else safe_int(parent)
        playlists.append({
            "id": safe_int(row[0]),
            "name": row[1] or "",
            "parentId": parent_id,
            "sortOrder": safe_int(row[3]),
            "rawIsFolder": 1 if safe_int(row[4]) == 1 else 0,
        })
    data["playlists"] = playlists

    # Build set of valid content IDs for filtering playlist entries
    content_ids = set()
    for row in con.execute("SELECT ID FROM djmdContent WHERE rb_local_deleted=0"):
        content_ids.add(str(row[0]))

    # ── Playlist Entries ──────────────────────────────────────────────────
    playlist_entries = []
    for row in con.execute(
        "SELECT PlaylistID, ContentID, TrackNo FROM djmdSongPlaylist "
        "WHERE rb_local_deleted=0 ORDER BY PlaylistID, TrackNo"
    ):
        content_str = str(row[1])
        if content_str not in content_ids:
            continue  # skip entries for deleted tracks
        playlist_entries.append({
            "playlistId": safe_int(row[0]),
            "trackId": safe_int(row[1]),
            "entryIndex": safe_int(row[2]),
        })
    data["playlist_entries"] = playlist_entries

    # ── Tracks ────────────────────────────────────────────────────────────
    tracks = []
    for row in con.execute(
        "SELECT ID, Title, ArtistID, AlbumID, GenreID, ColorID, KeyID, "
        "LabelID, FolderPath, FileNameL, BPM, Length, BitRate, SampleRate, "
        "ReleaseYear, Rating, TrackNo, DiscNo, FileSize, StockDate, "
        "AnalysisDataPath, Commnt, DateCreated, ReleaseDate, "
        "HotCueAutoLoad, ISRC, Lyricist, RemixerID, OrgArtistID, "
        "ComposerID, BitDepth "
        "FROM djmdContent WHERE rb_local_deleted=0 "
        "ORDER BY CAST(ID AS INTEGER)"
    ):
        track_id = safe_int(row[0])
        folder_path = row[8] or ""
        filename = row[9] or ""
        bpm_raw = safe_int(row[10])  # BPM * 100 in the DB
        length_sec = safe_int(row[11])
        bitrate = safe_int(row[12])
        sample_rate = safe_int(row[13], 44100)
        year = safe_int16(row[14])
        rating = safe_int(row[15])
        track_no = safe_int(row[16])
        disc_no = safe_int16(row[17])
        file_size = safe_int(row[18])
        stock_date = row[19] or ""
        analysis_path = row[20] or ""
        comment = row[21] or ""
        date_created = row[22] or ""
        release_date = row[23] or ""
        hotcue_autoload = row[24] or ""
        isrc = row[25] or ""
        lyricist = row[26] or ""
        remixer_id = safe_int(row[27])
        org_artist_id = safe_int(row[28])
        composer_id = safe_int(row[29])
        bit_depth = safe_int(row[30], 16)

        # Parse dateAdded from DateCreated (format: "2026-03-22 21:39:25.168 +00:00")
        date_added = ""
        if date_created:
            date_added = date_created[:10]  # "2026-03-22"

        # Fix analyze path
        analyze_path = fix_analyze_path(analysis_path)
        analyze_date = date_added  # use same date for analysis

        # File path: the FolderPath from the DB (already USB-relative)
        file_path = folder_path

        # Color ID: stored as string in DB, convert to int
        color_id = safe_int(row[5])

        tracks.append({
            "id": track_id,
            "title": row[1] or "",
            "artistId": safe_int(row[2]),
            "albumId": safe_int(row[3]),
            "genreId": safe_int(row[4]),
            "colorId": color_id,
            "keyId": safe_int(row[6]),
            "labelId": safe_int(row[7]),
            "remixerId": remixer_id,
            "originalArtistId": org_artist_id,
            "composerId": composer_id,
            "sampleRate": sample_rate,
            "fileSize": file_size,
            "artworkId": 0,  # no artwork table data
            "bitrate": bitrate,
            "trackNumber": track_no,
            "tempo": bpm_raw,
            "discNumber": disc_no,
            "playCount": 0,
            "year": year,
            "sampleDepth": bit_depth if bit_depth else 16,
            "duration": length_sec & 0xFFFF,
            "rating": rating & 0xFF,
            # String fields
            "isrc": isrc,
            "texter": lyricist,
            "unknownString2": "",
            "unknownString3": "",
            "unknownString4": "",
            "message": "",
            "kuvoPublic": "",
            "autoloadHotcues": hotcue_autoload if hotcue_autoload else "ON",
            "unknownString5": "",
            "unknownString6": "",
            "dateAdded": date_added,
            "releaseDate": release_date[:10] if release_date else "",
            "mixName": "",
            "unknownString7": "",
            "analyzePath": analyze_path,
            "analyzeDate": analyze_date,
            "comment": comment,
            "title": row[1] or "",
            "unknownString8": "",
            "filename": filename,
            "filePath": file_path,
        })
    data["tracks"] = tracks

    con.close()
    return data


# ── PDB Generation ────────────────────────────────────────────────────────────

def build_pdb(data: dict) -> bytes:
    """Build a complete export.pdb from the data dict."""
    writer = PdbWriter()

    # Page 0: file header (placeholder, finalized at end)
    writer._alloc_page()

    # ── Type 0: TRACKS ────────────────────────────────────────────────────
    track_rows = [serialize_track_row(t) for t in data["tracks"]]
    writer.write_table(TRACKS, track_rows)

    # ── Type 1: GENRES ────────────────────────────────────────────────────
    genre_rows = [serialize_genre_row(g["id"], g["name"]) for g in data["genres"]]
    writer.write_table(GENRES, genre_rows)

    # ── Type 2: ARTISTS ───────────────────────────────────────────────────
    artist_rows = [serialize_artist_row(a["id"], a["name"]) for a in data["artists"]]
    writer.write_table(ARTISTS, artist_rows)

    # ── Type 3: ALBUMS ────────────────────────────────────────────────────
    album_rows = [serialize_album_row(a["id"], a["name"], a.get("artistId", 0))
                  for a in data["albums"]]
    writer.write_table(ALBUMS, album_rows)

    # ── Type 4: LABELS ────────────────────────────────────────────────────
    label_rows = [serialize_label_row(l["id"], l["name"]) for l in data["labels"]]
    writer.write_table(LABELS, label_rows)

    # ── Type 5: KEYS ─────────────────────────────────────────────────────
    key_rows = [serialize_key_row(k["id"], k["name"]) for k in data["keys"]]
    writer.write_table(KEYS, key_rows)

    # ── Type 6: COLORS ───────────────────────────────────────────────────
    color_rows = [serialize_color_row(c["id"], c["code"], c["name"])
                  for c in data["colors"]]
    writer.write_table(COLORS, color_rows)

    # ── Type 7: PLAYLIST_TREE ────────────────────────────────────────────
    pl_rows = [serialize_playlist_tree_row(
        p["id"], p["parentId"], p["sortOrder"], p["rawIsFolder"], p["name"]
    ) for p in data["playlists"]]
    writer.write_table(PLAYLIST_TREE, pl_rows)

    # ── Type 8: PLAYLIST_ENTRIES ─────────────────────────────────────────
    entry_rows = [serialize_playlist_entry_row(
        e["entryIndex"], e["trackId"], e["playlistId"]
    ) for e in data["playlist_entries"]]
    writer.write_table(PLAYLIST_ENTRIES, entry_rows)

    # ── Types 9-12: Empty tables ─────────────────────────────────────────
    writer.write_table(UNK9, [])
    writer.write_table(UNK10, [])
    writer.write_table(HIST_PLAYLISTS, [])
    writer.write_table(HIST_ENTRIES, [])

    # ── Type 13: ARTWORK ─────────────────────────────────────────────────
    art_rows = [serialize_artwork_row(a["id"], a["path"]) for a in data["artwork"]]
    writer.write_table(ARTWORK, art_rows)

    # ── Types 14-19: Empty tables ────────────────────────────────────────
    writer.write_table(UNK14, [])
    writer.write_table(UNK15, [])
    writer.write_table(COLUMNS, [])
    writer.write_table(UNK17, [])
    writer.write_table(UNK18, [])
    writer.write_table(HISTORY, [])

    return writer.finalize()


# ── Backup ────────────────────────────────────────────────────────────────────

def backup_pdb(pdb_path: Path) -> Path:
    """Create a timestamped backup of an existing export.pdb."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pdb_path.parent / f"export_backup_{ts}.pdb"
    shutil.copy2(pdb_path, backup)
    print(f"  ✅ Backup: {backup}")
    return backup


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert exportLibrary.db to export.pdb (Pioneer DeviceSQL binary)")
    parser.add_argument("usb_path", help="USB mount point, e.g. /Volumes/MYUSB")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written without touching any files")
    args = parser.parse_args()

    usb_path = Path(args.usb_path)
    if not usb_path.exists():
        print(f"❌ USB path not found: {usb_path}", file=sys.stderr)
        sys.exit(1)

    # Find the Pioneer directory (PIONEER or .PIONEER)
    pioneer_dir = None
    for name in ["PIONEER", ".PIONEER"]:
        candidate = usb_path / name / "rekordbox"
        if candidate.exists():
            pioneer_dir = candidate
            break

    if not pioneer_dir:
        print(f"❌ No PIONEER/rekordbox directory found on {usb_path}", file=sys.stderr)
        sys.exit(1)

    db_path = pioneer_dir / "exportLibrary.db"
    pdb_path = pioneer_dir / "export.pdb"

    if not db_path.exists():
        print(f"❌ exportLibrary.db not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    # ── Read data ─────────────────────────────────────────────────────────
    print(f"📖 Reading: {db_path}")
    data = read_export_db(db_path)

    # Print summary
    print(f"  Tracks:           {len(data['tracks']):,}")
    print(f"  Artists:          {len(data['artists']):,}")
    print(f"  Genres:           {len(data['genres']):,}")
    print(f"  Albums:           {len(data['albums']):,}")
    print(f"  Labels:           {len(data['labels']):,}")
    print(f"  Keys:             {len(data['keys']):,}")
    print(f"  Colors:           {len(data['colors']):,}")
    print(f"  Playlists:        {len(data['playlists']):,}")
    print(f"  Playlist entries: {len(data['playlist_entries']):,}")
    print(f"  Artwork:          {len(data['artwork']):,}")

    if not data["tracks"]:
        print("⚠️  No tracks found — nothing to write.")
        sys.exit(0)

    # ── Build PDB ─────────────────────────────────────────────────────────
    print("\n🔨 Building export.pdb ...")
    pdb_bytes = build_pdb(data)
    num_pages = len(pdb_bytes) // PAGE_SIZE
    print(f"  File size: {len(pdb_bytes):,} bytes ({num_pages} pages)")

    if args.dry_run:
        print(f"\n🏁 Dry run — would write {len(pdb_bytes):,} bytes to {pdb_path}")
        return

    # ── Backup existing PDB ───────────────────────────────────────────────
    if pdb_path.exists():
        backup_pdb(pdb_path)

    # ── Write ─────────────────────────────────────────────────────────────
    print(f"\n💾 Writing: {pdb_path}")
    pdb_path.write_bytes(pdb_bytes)
    print(f"  ✅ Written {len(pdb_bytes):,} bytes ({num_pages} pages)")

    print(f"\n✅ Done! Verify with: node read_usb_pdb.js \"{usb_path}\" --summary")


if __name__ == "__main__":
    main()
