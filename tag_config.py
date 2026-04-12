"""
tag_config.py — Tag parsing, classification, and config I/O for MyTag conversion.

Extracts [bracketed] tags from Traktor comment fields and classifies them
into Rekordbox MyTag categories using a built-in dictionary or a user-editable
JSON config file.
"""

import json
import re
from pathlib import Path

# ── Tag extraction ────────────────────────────────────────────────────────────

TAG_PATTERN = re.compile(r'\[([^\]]+)\]')


def parse_comment_tags(comment: str) -> list[str]:
    """Extract [bracketed] tags from a comment string.
    Returns tag names with original case preserved, empty tags stripped."""
    if not comment:
        return []
    return [m.strip() for m in TAG_PATTERN.findall(comment) if m.strip()]


# ── Built-in dictionary ──────────────────────────────────────────────────────

BUILTIN_TAG_CATEGORIES: dict[str, list[str]] = {
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


# ── Classification ────────────────────────────────────────────────────────────

def classify_tag(tag: str, categories: dict[str, list[str]]) -> str:
    """Return the category name for a tag (case-insensitive). 'Uncategorized' if no match."""
    tag_lower = tag.lower()
    for cat_name, tag_list in categories.items():
        if tag_lower in (t.lower() for t in tag_list):
            return cat_name
    return "Uncategorized"


def classify_all_tags(tags: list[str], categories: dict[str, list[str]]) -> dict[str, list[str]]:
    """Classify a list of tags into categories.
    Returns {category: [tag, ...]} with original case preserved."""
    result: dict[str, list[str]] = {}
    for tag in tags:
        cat = classify_tag(tag, categories)
        result.setdefault(cat, []).append(tag)
    return result


# ── Config file I/O ───────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = Path(__file__).parent / "tag_categories.json"


def load_tag_categories(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, list[str]]:
    """Load tag→category mapping from JSON or fall back to built-in dict.

    If the JSON file exists, it is the authoritative source (built-in dict ignored).
    If it doesn't exist, returns a deep copy of the built-in dict.
    If the JSON is malformed, prints a warning and falls back to built-in.
    """
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
            print(f"  ⚠️  {config_path.name} has unexpected format — using built-in dict")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠️  Failed to read {config_path.name}: {e} — using built-in dict")
    # Deep copy so callers don't mutate the built-in
    return {k: list(v) for k, v in BUILTIN_TAG_CATEGORIES.items()}


def save_tag_categories(config_path: Path, categories: dict[str, list[str]]):
    """Write the current tag→category mapping to JSON."""
    config_path.write_text(
        json.dumps(categories, indent=2, ensure_ascii=False) + "\n",
        encoding='utf-8',
    )


def merge_new_tags(categories: dict[str, list[str]], discovered_tags: list[str]) -> bool:
    """Add any tags not already in any category to 'Uncategorized'.
    Returns True if new tags were added (config needs saving)."""
    # Build a set of all known tags (case-insensitive)
    known = set()
    for tag_list in categories.values():
        for t in tag_list:
            known.add(t.lower())

    new_tags = []
    for tag in discovered_tags:
        if tag.lower() not in known:
            new_tags.append(tag)
            known.add(tag.lower())

    if new_tags:
        categories.setdefault("Uncategorized", []).extend(new_tags)
        return True
    return False
