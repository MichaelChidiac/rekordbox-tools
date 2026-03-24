# Pioneer USB `export.pdb` Generation: Complete Research & Status Report

## Project Context

**Goal:** Generate a valid Pioneer USB `export.pdb` file that Rekordbox desktop recognizes as a "Device Library" (the legacy/standard format used by CDJ-2000NXS2 and older players).

**Current state:** The `traktor_to_usb.py` script successfully generates `exportLibrary.db` (Device Library Plus format) which works with newer CDJs (CDJ-3000, XDJ-RX3) — Rekordbox shows playlists under "Device Library Plus." However, `export.pdb` (DeviceSQL binary format) has never been successfully generated — Rekordbox either shows "corrupt" or becomes unresponsive when reading our generated files.

**USB drives:** PATRIOT (reference, known-good Rekordbox export), PATRIOT 2 (test target).

---

## What Works: Device Library Plus (`exportLibrary.db`)

The DLP approach works perfectly. Here's how it works:

1. **`traktor_to_usb.py`** reads Rekordbox's `master.db` (SQLCipher-encrypted, key `402fd482...`, `PRAGMA legacy=4`)
2. It creates `exportLibrary.db` on USB using the **export key** (`a]59Cv-N*[%Z;e7`) with SQLCipher 4 defaults (NO `legacy=4`)
3. The DLP database uses rekordbox's internal schema with tables like `agentRegistry`, `djmdContent`, `djmdArtist`, `djmdPlaylist`, `djmdSongPlaylist`, etc.
4. Tracks, playlists, artists, albums, genres, labels, keys, colors are all inserted with proper foreign key relationships
5. Audio files are copied to `/Contents/` on the USB
6. ANLZ files (waveforms, beat grids) are copied to `/PIONEER/USBANLZ/`

**Key code path:** `export_to_usb()` → `convert_djmd_to_dlp()` → writes a new SQLCipher DB with DLP schema.

**Result:** Rekordbox shows all playlists and tracks under "Device Library Plus" ✅

---

## What Fails: Device Library (`export.pdb`)

### What is `export.pdb`?

`export.pdb` is a proprietary binary database format called "DeviceSQL" used by Pioneer CDJ hardware. It contains 20 tables:

| Table | Content |
|-------|---------|
| Tracks | All track metadata (title, artist IDs, BPM, file paths, etc.) |
| Artists | Artist names with IDs |
| Albums | Album names with artist IDs |
| Genres | Genre names |
| Labels | Label names |
| Keys | Musical key names |
| Colors | Color names |
| Artwork | Artwork file paths |
| Playlists | Playlist tree (folders + playlists) |
| PlaylistEntries | Track-to-playlist mappings |
| Columns | UI column definitions |
| Menu | Menu structure |
| History | Play history |
| + 8 more | Mostly empty system tables |

### File Structure

```
export.pdb layout:
- Page 0: Header (4096 bytes)
  - Magic/page_size: 4096
  - num_tables: 20
  - next_unused_page: N
  - Table directory: 20 entries, each with:
    - page_type (table type)
    - first_page (PageIndex)
    - last_page (PageIndex)
    - empty_candidate (PageIndex)
- Pages 1..N: Data/Index pages (4096 bytes each)
  - Page types: Data (contains rows) or Index (B-tree index)
  - Each table has: Index page → chain of Data pages → Sentinel page
```

### Page Structure

```
Data Page (4096 bytes):
  PageHeader (28 bytes):
    - page_index, page_type, next_page
    - packed_row_counts (num_rows, num_rows_valid)
    - page_flags
    - free_size, used_size
  DataPageHeader (16 bytes):
    - unknown5 (always 1 in reference)
    - unknown_not_num_rows_large
  RowGroups (grow from bottom of page, upward):
    - Each RowGroup has 16 row_offsets (u16), presence flags, unknown
    - Written at page_end - 36 * group_index
  Rows (grow from top of data area, downward):
    - Variable-size row data
    - 4-byte aligned
```

### Row Format (Artist example)

```
Artist row (variable size):
  Offset 0: subtype (u16) = 0x0060
  Offset 2: index_shift (u16) = 0x20 * row_position
  Offset 4: id (u32) = ArtistId
  Offset 8: OffsetArrayContainer
    - Offset header: [magic=0x03, offset=10] (U8 format)
    - String data at offset 10: DeviceSQLString
      - ShortASCII: header_byte + ASCII chars
      - Long UCS-2: flags(0x90) + length(u16) + padding(0x00) + UCS-2 data
```

---

## Attempt History

### Attempt 1: Python `write_pdb.py` (1396 lines)

**Approach:** Pure Python binary writer that manually constructs every byte of the PDB format.

**Result:** ❌ Rekordbox detects as corrupt. Pages don't parse correctly in any tool.

**Problems identified:**
- Page structure alignment issues
- RowGroup format incorrect
- String encoding wrong
- No proper page chain linking

### Attempt 2: Rust PDB writer with `rekordcrate` library (current)

**Approach:** Use the open-source `rekordcrate` Rust library (https://github.com/Holzhaus/rekordcrate) which can both read AND write PDB files. The library has BinRead/BinWrite implementations for all PDB structures.

**Pipeline:**
1. `export_pdb_json.py` reads `exportLibrary.db` (DLP on USB) → outputs JSON with all tracks, artists, albums, etc.
2. `/tmp/pdb_writer/src/main.rs` (Rust, 851 lines) reads JSON → constructs PDB structs → serializes with BinWrite

**Key files:**
- `/tmp/pdb_writer/src/main.rs` — Rust PDB writer
- `/tmp/pdb_writer/Cargo.toml` — depends on local `/tmp/rekordcrate`
- `/tmp/export_pdb_json.py` — DLP → JSON exporter
- `/tmp/rekordcrate/` — modified fork of rekordcrate with some fields made public

**Results across iterations:**

#### v1 (`rust_export.pdb`, 1.2MB, 292 pages)
- Track, Genre, Color, Playlist, Column, Menu pages: ✅ Parse correctly
- Artist, Album pages: ❌ Show as "content: Unknown" in rekordcrate dump
- **Root cause found:** `MaybeCalculated::Calculated` mode in `OffsetArrayContainer` + `#[bw(align_after = 4)]` on `PlainRow::Artist/Album` causes the first 2 bytes of string data to be overwritten with zero padding

#### v2/v3 (`rust_export_v3.pdb`, 741KB, 181 pages)  
- All pages: ✅ Parse correctly (zero "Unknown" pages)
- Roundtrip: ✅ Read → Write → binary identical
- **Fixes applied:**
  1. Strip `\uFFFA`/`\uFFFB` Unicode markers from strings → proper ShortASCII encoding
  2. Use `MaybeCalculated::Provided` with pre-calculated offsets for Artist/Album
  3. Set `DataPageHeader.unknown5 = 1`
  4. Set `index_shift = 0x20 * row_position` per row
- **Rekordbox result:** ❌ Rekordbox becomes unresponsive when reading the USB

---

## Root Cause Analysis: The `align_after` Bug

### The Bug

In rekordcrate's `PlainRow` enum (`/tmp/rekordcrate/src/pdb/mod.rs`, line ~1631):
```rust
Artist(#[bw(align_after = 4)] Artist),
Album(#[bw(align_after = 4)] Album),
Track(#[bw(align_after = 4)] Track),
```

When `OffsetArrayContainer` uses `MaybeCalculated::Calculated` mode (`offset_array.rs` line ~172):
1. Skip past offset header bytes → cursor at `base + fixed_fields + header_size`
2. Write string data at that position ✅
3. Seek BACK to `base + fixed_fields` 
4. Write offset header → cursor at `base + fixed_fields + header_size`
5. **Cursor is now at offset_header_end, NOT at data_end**

Then `align_after = 4` pads FROM the cursor position:
- Artist: cursor at 10 (8 fixed + 2 header), 10 % 4 = 2 → writes 2 ZERO bytes at positions 10-11
- Those zeros OVERWRITE the first 2 bytes of the string data (ShortASCII header + first char)

### The Fix

Use `MaybeCalculated::Provided(OffsetArray::U8([offset]))` instead of `Calculated`:
- With Provided mode, the cursor ends at `base` (row start), which is already 4-byte aligned
- `align_after = 4` writes 0 padding bytes → string data preserved

Offset values:
- Artist ASCII: 10 (8 fixed + 2 U8 header)
- Artist non-ASCII: 12 (4-byte aligned for UCS-2)
- Album ASCII: 22 (20 fixed + 2 U8 header)  
- Album non-ASCII: 24 (4-byte aligned for UCS-2)
- Track: Calculated works fine (U16 offsets → 92 + 44 = 136, already 4-byte aligned)

### Why Track Works But Artist/Album Don't

Track uses U16 offsets (subtype 0x24, bit 2 set):
- Header size = (21 + 1) * 2 = 44 bytes
- Position after header = 92 + 44 = 136
- 136 % 4 = 0 → already aligned → no padding → no corruption

Artist/Album use U8 offsets (subtype 0x60/0x80, bit 2 not set):
- Header size = 1 + 1 = 2 bytes
- Position after header = 8 + 2 = 10 (Artist) or 20 + 2 = 22 (Album)
- 10 % 4 = 2, 22 % 4 = 2 → needs 2 bytes padding → CORRUPTION

---

## Remaining Unsolved Problems

Despite fixing the string corruption, Rekordbox still won't accept our PDB. Possible reasons:

### 1. File Size / Page Count
- Reference `export.pdb`: 13,197,312 bytes (3222 pages)
- Our `export.pdb`: 741,376 bytes (181 pages)
- Rekordbox may expect a minimum page count or pre-allocated empty pages
- The reference has many empty pages from Rekordbox's internal page allocator

### 2. Missing/Wrong System Tables
Our PDB has 20 tables but some may have incorrect content:
- History, HistoryEntries, HistoryClone — we create empty sentinels
- Some tables may need specific sentinel/system rows

### 3. `exportExt.pdb` Mismatch
- We copied `exportExt.pdb` from PATRIOT (reference) but our `export.pdb` is different
- There may be cross-references between the two files (sequence numbers, IDs)
- `exportExt.pdb` has 9 tables with extended track metadata

### 4. Page Chain / Index Page Issues
- Our index pages may not correctly mirror what Rekordbox expects
- Index page entries contain (PageIndex, unknown_byte) — the unknown_byte might matter
- The `empty_candidate` field in each Table header entry may need correct values

### 5. Sequence Number
- Reference header has `sequence: 6021` (incremented on each export)
- Our header has `sequence: 1`
- May need a realistic sequence number

### 6. `unknown1` / `unknown2` Fields in PageHeader
- Reference pages have non-zero `unknown1` values (105, 590, 610, etc.)
- Our pages have `unknown1: 0`
- These might be page sequence numbers or checksums

### 7. String Encoding Details
- Reference uses specific patterns for empty strings vs missing strings
- Track strings have `unknown_string2`, `unknown_string3`, `unknown_string4` with values like "8", "19", "20"
- We may not be matching these exactly

### 8. Row Counts / RowGroup Format
- `packed_row_counts` has `num_rows` and `num_rows_valid` — must be exact
- RowGroup `unknown` field varies in reference (1, 2, 3...) — may need correct values
- RowGroup `row_presence_flags` bitmask must match which slots have rows

---

## Key Files on Disk

### Working code (Rust PDB writer)
| File | Description |
|------|-------------|
| `/tmp/pdb_writer/src/main.rs` | 851-line Rust PDB writer |
| `/tmp/pdb_writer/Cargo.toml` | Cargo config, depends on local rekordcrate |
| `/tmp/pdb_writer/src/roundtrip.rs` | Read-write-compare tool |
| `/tmp/pdb_writer/src/test_page3.rs` | Key diagnostic: proves Provided vs Calculated bug |
| `/tmp/export_pdb_json.py` | DLP → JSON exporter (237 lines) |
| `/tmp/rekordcrate/` | Modified fork of rekordcrate library |

### Generated PDB files
| File | Size | Status |
|------|------|--------|
| `/tmp/rust_export.pdb` | 1.2MB | v1, Artist/Album corrupt |
| `/tmp/rust_export_v2.pdb` | 741KB | v2, fixed strings |
| `/tmp/rust_export_v3.pdb` | 741KB | v3, + index_shift fix |

### Reference files
| File | Description |
|------|-------------|
| `/Volumes/PATRIOT/PIONEER/rekordbox/export.pdb` | 13MB, known-good Rekordbox export |
| `/Volumes/PATRIOT/PIONEER/rekordbox/exportExt.pdb` | 86KB, extended metadata |
| `/Volumes/PATRIOT/PIONEER/rekordbox/exportLibrary.db` | 614KB, DLP database |

### Project scripts
| File | Description |
|------|-------------|
| `traktor_to_usb.py` | Main USB export (1617 lines), DLP works, PDB fails |
| `write_pdb.py` | Original Python PDB writer (1396 lines), abandoned |

---

## How to Build & Test

```bash
# Build Rust PDB writer
export PATH="$HOME/.cargo/bin:$PATH"
cd /tmp/pdb_writer && cargo build --release --bin pdb_writer

# Export DLP data to JSON
python3.11 /tmp/export_pdb_json.py "/Volumes/PATRIOT/PIONEER/rekordbox/exportLibrary.db" > /tmp/pdb_data.json

# Generate PDB
/tmp/pdb_writer/target/release/pdb_writer /tmp/pdb_data.json /tmp/test_export.pdb

# Verify with rekordcrate dump (should show zero "Unknown" pages)
cd /tmp/rekordcrate && cargo build --release
/tmp/rekordcrate/target/release/rekordcrate dump-pdb --db-type plain /tmp/test_export.pdb 2>&1 | grep -c "content: Unknown"

# Roundtrip test (should say IDENTICAL)
cd /tmp/pdb_writer && cargo build --release --bin roundtrip
/tmp/pdb_writer/target/release/roundtrip /tmp/test_export.pdb /tmp/test_rt.pdb

# Deploy to USB
cp /tmp/test_export.pdb "/Volumes/PATRIOT 2/PIONEER/rekordbox/export.pdb"

# Compare with reference
/tmp/rekordcrate/target/release/rekordcrate dump-pdb "/Volumes/PATRIOT/PIONEER/rekordbox/export.pdb" > /tmp/ref_dump.txt 2>&1
/tmp/rekordcrate/target/release/rekordcrate dump-pdb --db-type plain /tmp/test_export.pdb > /tmp/our_dump.txt 2>&1
diff /tmp/ref_dump.txt /tmp/our_dump.txt | head -100
```

---

## Reference PDB Patterns (from PATRIOT)

### Artist Row Examples
```
ASCII: Artist { subtype: Subtype(96), index_shift: 0, id: ArtistId(1),
  offsets: Provided(U8([10])), name: DeviceSQLString(Quelza) }

Non-ASCII: Artist { subtype: Subtype(96), index_shift: 0, id: ArtistId(6),
  offsets: Provided(U8([12])), name: DeviceSQLString(Rødhåd, Uvall) }
```

### Track Row Example
```
Track { subtype: Subtype(36), index_shift: 32, bitmask: 853760,
  sample_rate: 44100, composer_id: ArtistId(0), file_size: 36012032,
  ... artwork_id: ArtworkId(216), key_id: KeyId(19), ...
  offsets: Provided(U16([136, 137, 138, 140, 142, 144, 145, 146, 149,
    150, 151, 162, 173, 174, 175, 219, 230, 253, 278, 279, 325])),
  inner: TrackStrings { isrc: DeviceSQLString(), lyricist: DeviceSQLString(),
    unknown_string2: DeviceSQLString(8), unknown_string3: DeviceSQLString(8),
    unknown_string4: DeviceSQLString(6), ... } }
```

### PageHeader `unknown1` Pattern
- Varies per page: 105, 590, 610, etc.
- Appears to be a page sequence or modification counter
- Our pages have 0 — this might be why Rekordbox rejects the file

### DataPageHeader Pattern
- `unknown5`: always 1 for data pages with rows
- `unknown_not_num_rows_large`: varies (0, 1, 3, 5, 7 etc.) — appears to be `num_groups - 1`

---

## Suggested Next Approaches

### Approach A: Byte-level Copying with Targeted Fixes
Instead of building PDB from scratch, READ the reference `export.pdb`, modify specific rows (change track paths, add/remove playlists), and write it back. This preserves all the unknown fields and formatting that Rekordbox expects.

### Approach B: Study Other Tools
- **PDBLIB** (https://github.com/Deep-Symmetry/crate-digger) — Java library that reads/writes PDB files
- **prolink-tools** — Another implementation
- **Denon Engine Library** converters may have PDB writing code
- Compare our output byte-by-byte against these tools' output

### Approach C: Minimal Reproduction
Create the smallest possible valid PDB (1 track, 1 artist, 1 playlist) by hand-crafting each byte to match the reference format exactly. Then scale up.

### Approach D: Fix `unknown1` and Other Missing Fields
The `unknown1` field in PageHeader may be critical. Study the reference to determine the pattern and set it correctly. Also investigate the `sequence` field in the main header.

### Approach E: Use rekordcrate's Built-in Write Path
Instead of building pages manually, investigate if rekordcrate has a higher-level API for creating a complete PDB from scratch. The library's roundtrip works (read → write = identical), suggesting its write path is correct when given properly-structured input.
