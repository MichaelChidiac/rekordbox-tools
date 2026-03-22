#!/usr/bin/env python3.11
"""
nas_lookup.py
=============
NAS track lookup and download module for rekordbox-tools.

Queries traktor-ml's traktor.db to find tracks archived on the NAS,
and downloads them via the local traktor-ml API which auto-proxies
to the NAS for archived tracks.

Requirements
------------
  - traktor-ml project at ~/projects/traktor-ml/ (or TRAKTOR_ML_DB env var)
  - Local traktor-ml server running on port 5003 (or TRAKTOR_ML_API env var)
  - SSH tunnel to NAS active: ssh -L 5004:localhost:5003 <nas-host>
"""

import hashlib
import os
import sqlite3
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────
TRAKTOR_ML_DB = Path(os.environ.get(
    "TRAKTOR_ML_DB",
    os.path.expanduser("~/projects/traktor-ml/traktor.db"),
))
TRAKTOR_ML_API = os.environ.get("TRAKTOR_ML_API", "http://127.0.0.1:5003")

CHUNK_SIZE = 262144  # 256KB chunks for streaming


@dataclass
class NasTrackInfo:
    """Info about a track's NAS availability."""
    path: str
    storage_location: str  # 'remote', 'both', or 'local'
    size_bytes: int
    file_hash: str


def _open_traktor_db() -> Optional[sqlite3.Connection]:
    """Open traktor-ml's traktor.db read-only. Returns None if not found."""
    if not TRAKTOR_ML_DB.exists():
        return None
    con = sqlite3.connect(f"file:{TRAKTOR_ML_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def lookup_nas_tracks(paths: list[str]) -> dict[str, NasTrackInfo]:
    """
    Look up which tracks are available on the NAS.

    Returns a dict mapping path → NasTrackInfo for tracks with
    storage_location 'remote' or 'both'.
    """
    con = _open_traktor_db()
    if not con:
        return {}

    result = {}
    try:
        # Query in batches to avoid SQLite variable limit
        batch_size = 500
        for i in range(0, len(paths), batch_size):
            batch = paths[i:i + batch_size]
            placeholders = ",".join("?" * len(batch))
            rows = con.execute(
                f"SELECT path, storage_location, storage_size_bytes, file_hash "
                f"FROM tracks WHERE path IN ({placeholders}) "
                f"AND storage_location IN ('remote', 'both')",
                batch,
            ).fetchall()
            for row in rows:
                result[row["path"]] = NasTrackInfo(
                    path=row["path"],
                    storage_location=row["storage_location"],
                    size_bytes=row["storage_size_bytes"] or 0,
                    file_hash=row["file_hash"] or "",
                )
    finally:
        con.close()

    return result


def check_traktor_ml_reachable(api_base: str = TRAKTOR_ML_API) -> bool:
    """Check if the local traktor-ml API is running and reachable."""
    try:
        req = urllib.request.Request(f"{api_base}/docs", method="HEAD")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        # Try GET as fallback (some servers don't support HEAD)
        try:
            urllib.request.urlopen(f"{api_base}/docs", timeout=3)
            return True
        except Exception:
            return False


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_from_nas(
    track_path: str,
    dest: Path,
    api_base: str = TRAKTOR_ML_API,
    expected_hash: str = "",
) -> bool:
    """
    Download a track from the NAS via traktor-ml's local API.

    The local API auto-proxies to the NAS for archived tracks.
    Downloads to a temp file first, then moves to dest to avoid partial files.

    Returns True on success, False on failure.
    """
    url = f"{api_base}/api/audio?path={urllib.parse.quote(track_path)}"
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=Path(track_path).suffix,
        dir=str(dest.parent),
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            with os.fdopen(tmp_fd, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                tmp_fd = -1  # fd is now closed by os.fdopen context manager

        # Verify hash if available
        if expected_hash:
            actual_hash = _sha256_file(Path(tmp_path))
            if actual_hash != expected_hash:
                os.unlink(tmp_path)
                return False

        # Move temp file to final destination
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.rename(tmp_path, str(dest))
        return True

    except Exception:
        # Clean up temp file on failure
        if tmp_fd >= 0:
            os.close(tmp_fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return False
