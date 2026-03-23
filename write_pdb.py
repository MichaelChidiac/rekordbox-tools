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
# Device Library Plus key (exportLibrary.db on USB) — different from master.db key
EXPORT_KEY = "r8gddnr4k847830ar6cqzbkk0el6qytmb3trbbx805jm74vez64i5o8fnrqryqls"

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

# Standard column definitions for Pioneer CDJ browser (type 16)
# (column_id, unknown0, name) — same for every Pioneer USB
STANDARD_COLUMNS = [
    (1, 128, "GENRE"), (2, 129, "ARTIST"), (3, 130, "ALBUM"), (4, 131, "TRACK"),
    (5, 133, "BPM"), (6, 134, "RATING"), (7, 135, "YEAR"), (8, 136, "REMIXER"),
    (9, 137, "LABEL"), (10, 138, "ORIGINAL ARTIST"), (11, 139, "KEY"),
    (12, 141, "CUE"), (13, 142, "COLOR"), (14, 146, "TIME"), (15, 147, "BITRATE"),
    (16, 148, "FILE NAME"), (17, 132, "PLAYLIST"), (18, 152, "HOT CUE BANK"),
    (19, 149, "HISTORY"), (20, 145, "SEARCH"), (21, 150, "COMMENTS"),
    (22, 140, "DATE ADDED"), (23, 151, "DJ PLAY COUNT"), (24, 144, "FOLDER"),
    (25, 161, "DEFAULT"), (26, 162, "ALPHABET"), (27, 170, "MATCHING"),
]

# Standard menu entries for Pioneer CDJ browser (type 17)
# (category_id, content_pointer/menuItem_id, unknown, visibility, sort_order)
STANDARD_MENU = [
    (1, 1, 99, 0, 0), (5, 6, 5, 0, 0), (6, 7, 99, 0, 0), (7, 8, 99, 0, 0),
    (8, 9, 99, 0, 0), (9, 10, 99, 0, 0), (10, 11, 99, 0, 0),
    (14, 19, 4, 0, 0), (15, 20, 6, 0, 0), (16, 21, 99, 0, 0), (18, 23, 99, 0, 0),
    (2, 2, 2, 1, 1), (3, 3, 3, 1, 2), (4, 4, 1, 1, 3),
    (11, 12, 99, 1, 4), (13, 15, 99, 1, 5), (17, 5, 99, 1, 6),
    (19, 22, 99, 1, 7), (20, 18, 99, 1, 8), (27, 26, 99, 2, 9),
    (24, 17, 99, 1, 10), (22, 27, 99, 1, 11),
]

# Standard sort/column-association entries (type 18) — raw 8-byte rows
STANDARD_SORT_ROWS = [
    bytes.fromhex("1500070001000000"),
    bytes.fromhex("0e00080001000000"),
    bytes.fromhex("0800090001000000"),
    bytes.fromhex("09000a0001000000"),
    bytes.fromhex("0a000b0001000000"),
    bytes.fromhex("0f000d0001000000"),
    bytes.fromhex("1700100001000000"),
    bytes.fromhex("1600110001000000"),
    bytes.fromhex("1900000000010000"),
    bytes.fromhex("1a00010000020000"),
    bytes.fromhex("0200020000030000"),
    bytes.fromhex("0300030000040000"),
    bytes.fromhex("0b000c0000050000"),
    bytes.fromhex("0d000f0002060000"),
    bytes.fromhex("0500040000070000"),
    bytes.fromhex("0600050000080000"),
    bytes.fromhex("0000000000000000"),
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


def serialize_column_entry(col_id: int, unknown0: int, name: str) -> bytes:
    """Type 16: ColumnEntry — id(u2le) + unknown0(u2le) + DeviceSQLString name."""
    data = struct.pack("<HH", col_id, unknown0)
    data += encode_devicesql_string(name)
    return data


def serialize_menu_row(category_id: int, content_pointer: int, unknown: int,
                       visibility: int, sort_order: int) -> bytes:
    """Type 17: Menu — categoryId(u4le) + contentPointer(u4le) + unknown(u4le) + visibility(u4le) + sortOrder(u4le)."""
    return struct.pack("<5I", category_id, content_pointer, unknown, visibility, sort_order)


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
    # Compute bitmask: base 0x000C0700 (bits 8,9,10,18,19 always set),
    # add bit 16 if comment is non-empty (matches Rekordbox reference pattern)
    bitmask = 0x000C0700
    if t.get("comment", ""):
        bitmask |= 0x10000  # bit 16 = comment present

    fixed = bytearray()
    fixed.extend(struct.pack("<H", 0x0024))   # _unnamed0 (subtype)
    fixed.extend(struct.pack("<H", t.get("indexShift", 0)))
    fixed.extend(struct.pack("<I", bitmask))
    fixed.extend(struct.pack("<I", t.get("sampleRate", 44100)))
    fixed.extend(struct.pack("<I", t.get("composerId", 0)))
    fixed.extend(struct.pack("<I", t.get("fileSize", 0)))
    fixed.extend(struct.pack("<I", t.get("_unnamed6", 0)))
    fixed.extend(struct.pack("<H", t.get("_unnamed7", 47387)))  # constant from reference
    fixed.extend(struct.pack("<H", t.get("_unnamed8", 55941)))  # constant from reference
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
    fixed.extend(struct.pack("<H", 0x0029))   # u5 (always 0x29 per Deep Symmetry)
    fixed.append(t.get("colorId", 0) & 0xFF)  # colorId (u1)
    fixed.append(t.get("rating", 0) & 0xFF)   # rating (u1)
    fixed.extend(struct.pack("<H", t.get("fileType", 1)))  # file_type (1=MP3,4=M4A,5=FLAC,11=WAV,12=AIFF)
    fixed.extend(struct.pack("<H", 0x0003))   # u7 (always 3, precedes string offsets)
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
                           next_page: int, *, unk10: int = 0,
                           num_rows: int = 0, num_rows_valid: int = 0,
                           flags: int = 0, free_size: int = 0,
                           used_size: int = 0,
                           is_index: bool = False, index_unk1: int = 0,
                           index_unk2: int = 0,
                           dph_unk5: int = 0, dph_unk_nrl: int = 0,
                           dph_unk6: int = 0, dph_unk7: int = 0):
        """Write the 40-byte page header (32-byte PageHeader + 8-byte content header).

        Bytes 0x18-0x1A: packed_row_counts = num_rows(13 bits) | (num_rows_valid(11 bits) << 13)
        Byte 0x1B: page_flags
        Bytes 0x20-0x27: IndexPageHeader (2×u4) or DataPageHeader (4×u2)
        """
        struct.pack_into("<I", page, 0x00, 0)            # gap (always 0)
        struct.pack_into("<I", page, 0x04, page_idx)
        struct.pack_into("<I", page, 0x08, table_type)
        struct.pack_into("<I", page, 0x0C, next_page)
        struct.pack_into("<I", page, 0x10, unk10)
        struct.pack_into("<I", page, 0x14, 0)

        # packed_row_counts: 24-bit packed field (3 bytes LE)
        packed = (num_rows & 0x1FFF) | ((num_rows_valid & 0x7FF) << 13)
        page[0x18] = packed & 0xFF
        page[0x19] = (packed >> 8) & 0xFF
        page[0x1A] = (packed >> 16) & 0xFF
        page[0x1B] = flags & 0xFF

        struct.pack_into("<H", page, 0x1C, free_size & 0xFFFF)
        struct.pack_into("<H", page, 0x1E, used_size & 0xFFFF)

        if is_index:
            # First 4 bytes of index content area (unknown_a + unknown_b)
            # Full IndexPageContent is written by _write_index_content()
            struct.pack_into("<I", page, 0x20, index_unk1)
            struct.pack_into("<I", page, 0x24, index_unk2)
        else:
            # DataPageHeader: 4 × u2
            struct.pack_into("<H", page, 0x20, dph_unk5 & 0xFFFF)
            struct.pack_into("<H", page, 0x22, dph_unk_nrl & 0xFFFF)
            struct.pack_into("<H", page, 0x24, dph_unk6 & 0xFFFF)
            struct.pack_into("<H", page, 0x26, dph_unk7 & 0xFFFF)

    @staticmethod
    def _write_index_content(page: bytearray, header_page_idx: int,
                             first_data_page_idx: int,
                             data_page_indices: list[int]):
        """Write the IndexPageContent after the 32-byte PageHeader.

        Layout (at offset 0x20):
          u16  unknown_a       (0x1FFF)
          u16  unknown_b       (0x1FFF)
          u16  magic           (0x03EC)
          u16  next_offset     (= num_entries)
          u32  page_index      (self-reference to header page)
          u32  next_page       (first data page, or 0x03FFFFFF if empty)
          u64  magic           (0x0000_0000_03FF_FFFF)
          u16  num_entries
          u16  first_empty     (0x1FFF = no empty slots)
        Total header: 28 bytes

        Followed by IndexEntry values (u32 each):
          Non-empty: (data_page_index << 3) | 0
          Empty:     0x1FFF_FFF8
        Max entries per 4096-byte page: (4096 - 32 - 28 - 20) / 4 = 1004
        Last 20 bytes of page: zeros (already zero from bytearray init).
        """
        EMPTY_ENTRY = 0x1FFF_FFF8
        INDEX_PAGE_SENTINEL = 0x03FF_FFFF  # "no next page" marker
        MAX_ENTRIES = (PAGE_SIZE - 32 - 28 - 20) // 4  # 1004

        num_entries = min(len(data_page_indices), MAX_ENTRIES)
        # Empty tables use sentinel value for next_page (matches Rekordbox reference)
        next_page = data_page_indices[0] if data_page_indices else INDEX_PAGE_SENTINEL
        off = 0x20

        # IndexPageHeader (28 bytes)
        struct.pack_into("<H", page, off, 0x1FFF)       # unknown_a
        struct.pack_into("<H", page, off + 2, 0x1FFF)   # unknown_b
        struct.pack_into("<H", page, off + 4, 0x03EC)   # magic
        struct.pack_into("<H", page, off + 6, num_entries)  # next_offset
        struct.pack_into("<I", page, off + 8, header_page_idx)  # page_index
        struct.pack_into("<I", page, off + 12, next_page)  # next_page
        struct.pack_into("<Q", page, off + 16, 0x0000_0000_03FF_FFFF)  # magic
        struct.pack_into("<H", page, off + 24, num_entries)  # num_entries
        struct.pack_into("<H", page, off + 26, 0x1FFF)  # first_empty

        # Index entries start at offset 0x3C (0x20 + 28)
        entries_off = 0x3C
        for i in range(MAX_ENTRIES):
            if i < num_entries:
                entry = (data_page_indices[i] << 3) | 0  # flags = 0
            else:
                entry = EMPTY_ENTRY
            struct.pack_into("<I", page, entries_off + i * 4, entry)

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

            # Flags and unknown field at end of group
            struct.pack_into("<H", page, grp_offset + 32, present_flags)
            struct.pack_into("<H", page, grp_offset + 34, 0)  # unknown (always 0 for fresh data)

        # ── Page header ───────────────────────────────────────────────────
        # numRowsLarge at 0x22: set to actual count when > 255 (overflow for u1 numRowsSmall)
        self._write_page_header(
            page, 0, table_type, 0,  # page_idx and next_page set later
            unk10=page_counter,
            num_rows=nrows,
            num_rows_valid=nrows,
            flags=0x24,  # normal data page (no deleted rows)
            free_size=free_size,
            used_size=used_size,
            dph_unk5=nrows,
            dph_unk_nrl=nrows if nrows > 255 else 0,
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
                unk10=1, flags=0x64,
                is_index=True, index_unk1=0x1FFF1FFF, index_unk2=1004,
            )
            # Write empty index content (num_entries=0, all empty entries)
            self._write_index_content(
                header_page, header_idx, empty_idx, [])
            # Leave empty_page as all zeros (matches reference format)

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

        # Write header page (32-byte PageHeader)
        first_data = page_indices[0]
        self._write_page_header(
            header_page, header_idx, table_type, first_data,
            unk10=1, flags=0x64,
            is_index=True, index_unk1=0x1FFF1FFF, index_unk2=1004,
        )

        # Write index page content (IndexPageHeader + index entries)
        self._write_index_content(
            header_page, header_idx, first_data, page_indices)

        last_data = page_indices[-1]
        self.table_info.append({
            "type": table_type,
            "empty_candidate": -1,  # placeholder, set in finalize
            "first_page": header_idx,
            "last_page": last_data,
            "_data_page_indices": page_indices,
        })

    def finalize(self, num_tables: int = NUM_TABLES) -> bytes:
        """Build file header (page 0) and finalize all page links.

        Returns the complete PDB file as bytes.
        """
        # Allocate sentinel (empty) pages for each populated table's empty_candidate
        # Reference PDBs have ALL-ZERO empty candidate pages
        for info in self.table_info:
            if info["empty_candidate"] == -1:
                sentinel_idx, sentinel_page = self._alloc_page()
                info["empty_candidate"] = sentinel_idx
                # Leave sentinel_page as all zeros (matches reference format)

                # Set last data page's next_page to sentinel
                dp_indices = info.get("_data_page_indices", [])
                if dp_indices:
                    last_pg = self.pages[dp_indices[-1]]
                    struct.pack_into("<I", last_pg, 0x0C, sentinel_idx)

        next_unused = len(self.pages)

        # Build page 0 (file header)
        page0 = bytearray(PAGE_SIZE)
        struct.pack_into("<I", page0, 0x00, 0)             # padding
        struct.pack_into("<I", page0, 0x04, PAGE_SIZE)      # page size
        struct.pack_into("<I", page0, 0x08, num_tables)     # num tables
        struct.pack_into("<I", page0, 0x0C, next_unused)    # next unused page
        struct.pack_into("<I", page0, 0x10, 5)              # unknown (always 5)
        struct.pack_into("<I", page0, 0x14, 1)              # sequence (non-zero)
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
    """Open the SQLCipher-encrypted exportLibrary.db (read-only).
    Tries Device Library Plus key first, falls back to master.db key."""
    # Try Device Library Plus format (export key, SQLCipher 4 defaults)
    try:
        con = sqlcipher3.connect(str(db_path), flags=sqlcipher3.SQLITE_OPEN_READONLY)
        con.execute(f"PRAGMA key='{EXPORT_KEY}'")
        con.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return con
    except Exception:
        pass

    # Fall back to djmd format (master key, legacy=4)
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
    """Read all tables from exportLibrary.db, return structured data.
    Handles both Device Library Plus (DLP) and djmd formats automatically."""
    con = open_export_db(db_path)

    # Detect schema format
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    is_dlp = 'content' in tables and 'djmdContent' not in tables

    if is_dlp:
        return _read_dlp_db(con)
    else:
        return _read_djmd_db(con)


def _read_dlp_db(con) -> dict:
    """Read Device Library Plus format database."""
    data = {}

    # Colors
    colors = []
    for row in con.execute("SELECT color_id, name FROM color ORDER BY color_id"):
        cid = safe_int(row[0])
        name = row[1] or COLOR_NAMES.get(cid, "")
        colors.append({"id": cid, "code": cid, "name": name})
    data["colors"] = colors

    # Genres
    genres = []
    for row in con.execute("SELECT genre_id, name FROM genre ORDER BY genre_id"):
        genres.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["genres"] = genres

    # Artists
    artists = []
    for row in con.execute("SELECT artist_id, name FROM artist ORDER BY artist_id"):
        artists.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["artists"] = artists

    # Albums
    albums = []
    for row in con.execute("SELECT album_id, name, artist_id FROM album ORDER BY album_id"):
        albums.append({
            "id": safe_int(row[0]),
            "name": row[1] or "",
            "artistId": safe_int(row[2]),
        })
    data["albums"] = albums

    # Labels
    labels = []
    for row in con.execute("SELECT label_id, name FROM label ORDER BY label_id"):
        labels.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["labels"] = labels

    # Keys
    keys = []
    for row in con.execute("SELECT key_id, name FROM key ORDER BY key_id"):
        keys.append({"id": safe_int(row[0]), "name": row[1] or ""})
    data["keys"] = keys

    # Artwork (images)
    artwork = []
    try:
        for row in con.execute("SELECT image_id, path FROM image WHERE path IS NOT NULL AND path != '' ORDER BY image_id"):
            artwork.append({"id": safe_int(row[0]), "path": row[1] or ""})
    except Exception:
        pass
    data["artwork"] = artwork

    # Playlists
    playlists = []
    for row in con.execute("SELECT playlist_id, name, playlist_id_parent, sequenceNo, attribute "
                           "FROM playlist ORDER BY playlist_id_parent, sequenceNo"):
        parent_id = safe_int(row[2])
        playlists.append({
            "id": safe_int(row[0]),
            "name": row[1] or "",
            "parentId": parent_id,
            "sortOrder": safe_int(row[3]),
            "rawIsFolder": 1 if safe_int(row[4]) == 1 else 0,
        })
    data["playlists"] = playlists

    # Build valid content ID set
    content_ids = set()
    for row in con.execute("SELECT content_id FROM content"):
        content_ids.add(str(row[0]))

    # Playlist entries
    playlist_entries = []
    for row in con.execute("SELECT playlist_id, content_id, sequenceNo FROM playlist_content ORDER BY playlist_id, sequenceNo"):
        content_str = str(row[1])
        if content_str not in content_ids:
            continue
        playlist_entries.append({
            "playlistId": safe_int(row[0]),
            "trackId": safe_int(row[1]),
            "entryIndex": safe_int(row[2]),
        })
    data["playlist_entries"] = playlist_entries

    # Tracks
    tracks = []
    for row in con.execute(
        "SELECT content_id, title, artist_id_artist, album_id, genre_id, color_id, key_id, "
        "label_id, path, fileName, bpmx100, length, bitrate, samplingRate, "
        "releaseYear, rating, trackNo, discNo, fileSize, dateAdded, "
        "analysisDataFilePath, djComment, dateCreated, releaseDate, "
        "isHotCueAutoLoadOn, isrc, artist_id_lyricist, artist_id_remixer, "
        "artist_id_originalArtist, artist_id_composer, bitDepth, masterContentId "
        "FROM content ORDER BY content_id"
    ):
        track_id = safe_int(row[0])
        folder_path = row[8] or ""
        filename = row[9] or ""
        bpm_raw = safe_int(row[10])
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
        hotcue_autoload = "ON" if row[24] else "OFF"
        isrc = row[25] or ""
        lyricist_id = safe_int(row[26])
        remixer_id = safe_int(row[27])
        org_artist_id = safe_int(row[28])
        composer_id = safe_int(row[29])
        bit_depth = safe_int(row[30], 16)
        master_content_id = safe_int(row[31])

        date_added = ""
        if date_created:
            date_added = date_created[:10]
        if not date_added and stock_date:
            date_added = stock_date[:10]

        analyze_path = fix_analyze_path(analysis_path)
        analyze_date = date_added

        color_id = safe_int(row[5])
        file_type = 1
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        FILE_TYPE_MAP = {"mp3": 1, "m4a": 4, "aac": 4, "flac": 5,
                         "wav": 11, "aiff": 12, "aif": 12}
        file_type = FILE_TYPE_MAP.get(ext, 1)

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
            "_unnamed6": master_content_id,
            "artworkId": 0,
            "bitrate": bitrate,
            "trackNumber": track_no,
            "tempo": bpm_raw,
            "discNumber": disc_no,
            "playCount": 0,
            "year": year,
            "sampleDepth": bit_depth if bit_depth else 16,
            "duration": length_sec & 0xFFFF,
            "rating": rating & 0xFF,
            "fileType": file_type,
            "isrc": isrc,
            "texter": "",
            "unknownString2": "10",
            "unknownString3": "10",
            "unknownString4": "8",
            "message": "",
            "kuvoPublic": "",
            "autoloadHotcues": hotcue_autoload,
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
            "filePath": folder_path,
        })
    data["tracks"] = tracks

    con.close()
    return data


def _read_djmd_db(con) -> dict:
    """Read djmd-format database (legacy format)."""
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
        "ComposerID, BitDepth, rb_local_usn "
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
        rb_local_usn = safe_int(row[31])

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

        # File type from extension (1=MP3, 4=M4A, 5=FLAC, 11=WAV, 12=AIFF)
        file_type = 1  # default MP3
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        FILE_TYPE_MAP = {"mp3": 1, "m4a": 4, "aac": 4, "flac": 5,
                         "wav": 11, "aiff": 12, "aif": 12}
        file_type = FILE_TYPE_MAP.get(ext, 1)

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
            "_unnamed6": rb_local_usn,
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
            "fileType": file_type,
            # String fields
            "isrc": isrc,
            "texter": lyricist,
            "unknownString2": "10",
            "unknownString3": "10",
            "unknownString4": "8",
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


def remap_ids(data: dict) -> dict:
    """Remap all entity IDs to small sequential integers (1-based).

    Rekordbox USB exports use small sequential IDs. Our master.db IDs can be
    very large (>2^31), which Rekordbox treats as negative when read as signed
    int32, causing it to discard all track/playlist data. Colors (IDs 1-8) are
    kept as-is since they already use small IDs.
    """
    # Build old→new mappings for each entity type
    def make_map(items, start=1):
        m = {}
        for i, item in enumerate(items, start):
            old_id = item["id"]
            m[old_id] = i
            item["id"] = i
        return m

    genre_map = make_map(data["genres"])
    artist_map = make_map(data["artists"])
    album_map = make_map(data["albums"])
    label_map = make_map(data["labels"])
    key_map = make_map(data["keys"])
    # Colors keep their original IDs (already 1-8)
    color_map = {c["id"]: c["id"] for c in data["colors"]}
    artwork_map = make_map(data["artwork"])

    # Remap album artist references
    for a in data["albums"]:
        a["artistId"] = artist_map.get(a.get("artistId", 0), 0)

    # Remap track references
    track_map = {}
    for i, t in enumerate(data["tracks"], 1):
        old_id = t["id"]
        track_map[old_id] = i
        t["id"] = i
        t["artistId"] = artist_map.get(t.get("artistId", 0), 0)
        t["albumId"] = album_map.get(t.get("albumId", 0), 0)
        t["genreId"] = genre_map.get(t.get("genreId", 0), 0)
        t["colorId"] = color_map.get(t.get("colorId", 0), 0)
        t["keyId"] = key_map.get(t.get("keyId", 0), 0)
        t["labelId"] = label_map.get(t.get("labelId", 0), 0)
        t["remixerId"] = artist_map.get(t.get("remixerId", 0), 0)
        t["originalArtistId"] = artist_map.get(t.get("originalArtistId", 0), 0)
        t["composerId"] = artist_map.get(t.get("composerId", 0), 0)
        t["artworkId"] = artwork_map.get(t.get("artworkId", 0), 0)

    # Remap playlist IDs and parent references
    playlist_map = {}
    for i, p in enumerate(data["playlists"], 1):
        old_id = p["id"]
        playlist_map[old_id] = i
        p["id"] = i
    for p in data["playlists"]:
        p["parentId"] = playlist_map.get(p.get("parentId", 0), 0)

    # Remap playlist entry references
    for e in data["playlist_entries"]:
        e["trackId"] = track_map.get(e.get("trackId", 0), 0)
        e["playlistId"] = playlist_map.get(e.get("playlistId", 0), 0)

    # Remove entries with unmapped references
    data["playlist_entries"] = [
        e for e in data["playlist_entries"]
        if e["trackId"] > 0 and e["playlistId"] > 0
    ]

    return data


# ── PDB Generation ────────────────────────────────────────────────────────────

def build_pdb(data: dict) -> bytes:
    """Build a complete export.pdb from the data dict."""
    # Remap IDs to small sequential integers (required for Rekordbox)
    data = remap_ids(data)

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

    # ── Types 14-15: Empty tables ───────────────────────────────────────
    writer.write_table(UNK14, [])
    writer.write_table(UNK15, [])

    # ── Type 16: COLUMNS (system table) ──────────────────────────────────
    col_rows = [serialize_column_entry(cid, unk, name) for cid, unk, name in STANDARD_COLUMNS]
    writer.write_table(COLUMNS, col_rows)

    # ── Type 17: MENU (system table) ─────────────────────────────────────
    menu_rows = [serialize_menu_row(*m) for m in STANDARD_MENU]
    writer.write_table(UNK17, menu_rows)

    # ── Type 18: SORT (system table) ─────────────────────────────────────
    writer.write_table(UNK18, STANDARD_SORT_ROWS)

    # ── Type 19: HISTORY ─────────────────────────────────────────────────
    writer.write_table(HISTORY, [])

    return writer.finalize()


def build_ext_pdb() -> bytes:
    """Build a minimal exportExt.pdb with 9 empty tables (types 0-8)."""
    writer = PdbWriter()
    writer._alloc_page()  # page 0: file header
    for t in range(9):
        writer.write_table(t, [])
    return writer.finalize(num_tables=9)


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
    ext_pdb_path = pioneer_dir / "exportExt.pdb"

    if not db_path.exists():
        print(f"❌ exportLibrary.db not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    # ── Read data ─────────────────────────────────────────────────────────
    print(f"📖 Reading: {db_path}")
    data = read_export_db(db_path)

    # ── Fill in missing file sizes from actual USB files ──────────────────
    fixed_sizes = 0
    for t in data["tracks"]:
        if not t.get("fileSize"):
            fp = t.get("filePath", "")
            if fp:
                full = usb_path / fp.lstrip("/")
                if full.exists():
                    t["fileSize"] = full.stat().st_size
                    fixed_sizes += 1
        # Set _unnamed6 to track ID as export reference value if not populated
        if not t.get("_unnamed6") or t["_unnamed6"] <= 1:
            t["_unnamed6"] = t.get("id", 1)
    if fixed_sizes:
        print(f"  📏 Filled {fixed_sizes} file sizes from USB filesystem")

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
        print(f"    and exportExt.pdb ({len(build_ext_pdb()):,} bytes)")
        return

    # ── Backup existing PDB ───────────────────────────────────────────────
    if pdb_path.exists():
        backup_pdb(pdb_path)

    # ── Write ─────────────────────────────────────────────────────────────
    print(f"\n💾 Writing: {pdb_path}")
    pdb_path.write_bytes(pdb_bytes)
    print(f"  ✅ Written {len(pdb_bytes):,} bytes ({num_pages} pages)")

    # ── Write exportExt.pdb ──────────────────────────────────────────────
    ext_bytes = build_ext_pdb()
    if ext_pdb_path.exists():
        backup_pdb(ext_pdb_path)
    ext_pdb_path.write_bytes(ext_bytes)
    print(f"  ✅ Written exportExt.pdb ({len(ext_bytes):,} bytes)")

    print(f"\n✅ Done! Verify with: node read_usb_pdb.js \"{usb_path}\" --summary")


if __name__ == "__main__":
    main()
