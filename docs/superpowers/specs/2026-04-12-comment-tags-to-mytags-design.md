# Comment Tags → Rekordbox MyTags

**Date**: 2026-04-12
**Status**: Draft

## Problem

Traktor's comment field is used to store tags in `[bracket]` format (e.g. `[techno] [deep] [peak-hour]`). When exporting to Rekordbox, these tags are copied as raw text into the Comments field — losing their semantic value. Rekordbox has a dedicated MyTag system that supports categorized tags with parent/child grouping. This feature converts bracketed comment tags into proper Rekordbox MyTags during export.

## Scope

- Parse `[tag]` tokens from Traktor comment fields
- Auto-classify tags into categories (Genre, Energy, Mood, Style) using a built-in dictionary
- Write tag definitions and track-tag associations to both master.db and USB export databases
- Generate a `tag_categories.json` config file for user override
- Keep original comment text intact (no stripping)

## Design

### 1. Tag Parsing

A shared utility function extracts bracketed tags from comments.

**Module**: New file `tag_config.py` (co-located with `config.py`).

```python
import re

TAG_PATTERN = re.compile(r'\[([^\]]+)\]')

def parse_comment_tags(comment: str) -> list[str]:
    """Extract [bracketed] tags from a comment string.
    Returns tag names with original case preserved."""
    return [m.strip() for m in TAG_PATTERN.findall(comment) if m.strip()]
```

**Integration**: Both `traktor_to_master.py::parse_tracks()` and `traktor_to_rekordbox.py::parse_tracks()` will call `parse_comment_tags()` and store the result in `t['tags']` (a list of strings).

### 2. Auto-Classification

A built-in dictionary maps common DJ tag names (case-insensitive) to categories:

```python
BUILTIN_TAG_CATEGORIES = {
    "Genre": [
        "techno", "house", "trance", "dnb", "drum and bass",
        "electro", "ambient", "downtempo", "breaks", "garage",
        "dubstep", "hardstyle", "hardcore", "industrial",
        "disco", "funk", "soul", "hip-hop", "r&b",
        "afro house", "afro tech", "latin", "reggaeton",
    ],
    "Energy": [
        "peak-hour", "peak hour", "warm-up", "warm up",
        "chill", "high-energy", "low-energy", "mid-energy",
        "build-up", "cool-down", "opener", "closer",
    ],
    "Mood": [
        "dark", "uplifting", "melancholic", "euphoric",
        "hypnotic", "groovy", "aggressive", "dreamy",
        "emotional", "intense", "playful", "moody",
    ],
    "Style": [
        "progressive", "melodic", "acid", "minimal",
        "deep", "raw", "organic", "driving", "percussive",
        "vocal", "instrumental", "dub", "lo-fi",
    ],
}
```

**Classification logic**:
1. For each tag found in comments, match (case-insensitive) against the built-in dictionary
2. First match wins (a tag belongs to exactly one category)
3. Unmatched tags → "Uncategorized"

### 3. Config File (`tag_categories.json`)

Located in the project root alongside `sync_config.json`.

**Format**:
```json
{
  "Genre": ["techno", "house", "trance"],
  "Energy": ["peak-hour", "warm-up"],
  "Mood": ["dark", "uplifting"],
  "Style": ["progressive", "melodic", "deep"],
  "Uncategorized": ["some-unknown-tag"]
}
```

**Behavior**:
- If `tag_categories.json` exists → load it as the authoritative mapping. Built-in dict is ignored.
- If it does not exist → use built-in dict. After processing, write the discovered tag→category mapping to `tag_categories.json` so the user can edit it for future runs.
- Tags not in the config file (new tags found in comments) → added to "Uncategorized" and the config file is updated.

**Functions**:
```python
def load_tag_categories(config_path: Path) -> dict[str, list[str]]:
    """Load tag→category mapping from JSON or fall back to built-in."""

def save_tag_categories(config_path: Path, categories: dict[str, list[str]]):
    """Write the current tag→category mapping to JSON."""

def classify_tag(tag: str, categories: dict[str, list[str]]) -> str:
    """Return the category name for a tag. 'Uncategorized' if no match."""
```

### 4. Database Writes

#### 4a. master.db (via `traktor_to_master.py`)

New function `sync_mytags()` called after `sync_tracks()`:

```python
def sync_mytags(con, tracks: dict, path_to_content_id: dict,
                tag_categories: dict, usn: int) -> tuple:
    """
    Insert MyTag categories, tags, and track-tag links into master.db.

    Tables:
      djmdMyTag     — tag definitions (categories as parents, tags as children)
      djmdSongMyTag — track-tag associations

    Args:
        con:                 Open SQLCipher connection (read-write)
        tracks:              {traktor_key: track_dict} with 'tags' field
        path_to_content_id:  {fs_path: content_id} from sync_tracks()
        tag_categories:      {"Genre": ["techno", ...], ...}
        usn:                 Session USN counter

    Returns:
        (categories_created, tags_created, links_created)
    """
```

**djmdMyTag schema** (existing in master.db):
| Column | Type | Purpose |
|--------|------|---------|
| ID | VARCHAR(255) PK | Stable ID (CRC32 of `mytag:<name>`) |
| Seq | INTEGER | Display order |
| Name | VARCHAR(255) | Category or tag name |
| Attribute | INTEGER | 0 = folder/category, 1 = tag |
| ParentID | VARCHAR(255) | NULL for categories, category ID for tags |
| UUID | VARCHAR(255) | Random UUID |
| rb_local_usn | INTEGER | Must not be NULL |

**djmdSongMyTag schema** (existing in master.db):
| Column | Type | Purpose |
|--------|------|---------|
| ID | VARCHAR(255) PK | Stable ID |
| MyTagID | VARCHAR(255) | FK → djmdMyTag.ID |
| ContentID | VARCHAR(255) | FK → djmdContent.ID |
| TrackNo | INTEGER | Sequence within the tag |
| UUID | VARCHAR(255) | Random UUID |
| rb_local_usn | INTEGER | Must not be NULL |

**ID generation**: Uses existing `make_id()` pattern (CRC32-based) with collision guard:
- Category ID: `make_id(f'mytag-cat:{category_name}')`
- Tag ID: `make_id(f'mytag:{tag_name}')`
- Link ID: `make_id(f'mytag-link:{tag_id}:{content_id}')`

**Idempotency**: Uses `INSERT OR IGNORE` for all rows. Re-running the script will not create duplicates.

#### 4b. USB export (via `traktor_to_usb.py`)

Same logic adapted for the simpler USB schema:

**myTag table**:
| Column | Type |
|--------|------|
| myTag_id | INTEGER PK |
| sequenceNo | INTEGER |
| name | VARCHAR |
| attribute | INTEGER |
| myTag_id_parent | INTEGER |

**myTag_content table**:
| Column | Type |
|--------|------|
| myTag_id | INTEGER |
| content_id | INTEGER |

USB uses integer IDs (auto-incrementing or CRC32 as int). The conversion reuses the same tag parsing and classification.

### 5. CLI Flags

#### `traktor_to_master.py`
```
--tags          Enable comment-to-MyTag conversion (default: on)
--no-tags       Skip MyTag conversion
```

#### `traktor_to_usb.py`
```
--tags          Enable comment-to-MyTag conversion (default: on)
--no-tags       Skip MyTag conversion
```

#### `traktor_to_rekordbox.py` (XML export)
No new flags. Tags are parsed into the track dict (for downstream consumers) but not written to XML (Rekordbox XML has no MyTag support).

### 6. Dry-Run Output

When `--dry-run` is active:
```
🏷️  MyTag conversion:
  Would create 4 categories: Genre, Energy, Mood, Style
  Would create 23 tags across categories
  Would create 847 track-tag links
  Category breakdown:
    Genre (12 tags): techno, house, trance, ...
    Energy (4 tags): peak-hour, warm-up, chill, ...
    Mood (3 tags): dark, uplifting, hypnotic
    Style (4 tags): progressive, melodic, deep, acid
```

### 7. Files Changed

| File | Change |
|------|--------|
| `tag_config.py` | **New** — tag parsing, built-in dict, classification, config I/O |
| `traktor_to_master.py` | Add `tags` to parse_tracks, add `sync_mytags()`, CLI flags |
| `traktor_to_usb.py` | Add MyTag export using USB schema |
| `traktor_to_rekordbox.py` | Add `tags` to parse_tracks (data only, no XML output) |
| `tag_categories.json` | **Auto-generated** on first run |

### 8. Error Handling

- If comment is empty → `tags` = `[]`, no MyTag rows created
- If `tag_categories.json` is malformed → log warning, fall back to built-in dict
- If DB write fails → rollback (existing pattern), no partial tag state
- If a tag name exceeds 255 chars → truncate with warning

### 9. Testing Notes

- `parse_comment_tags()` is pure — easy to unit test with various comment formats
- `classify_tag()` is pure — test against built-in dict and custom config
- DB writes can be tested against an in-memory SQLite DB (no SQLCipher needed for schema validation)
