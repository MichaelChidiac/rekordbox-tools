#!/usr/bin/env python3.11
"""
traktor_to_usb.py
=================
Exports Traktor playlists directly to a Pioneer USB drive (no Rekordbox needed).

Selection
---------
  --select          Interactive checkbox UI — pick folders/playlists to export
  --all             Export the entire library
  --playlists NAME  Export specific folder/playlist names

Sync modes (--mode)
-------------------
  update  (default)  Skip existing tracks, update changed metadata, delete only
                     tracks removed from master.db entirely. Always rebuilds
                     the playlist tree from the current selection.
  push               Additive only — copies selected playlists/tracks to USB,
                     never deletes anything, merges into existing playlist tree.
  mirror             USB exactly matches the selected playlists. Wipes + rebuilds
                     playlist tree, deletes tracks not in scope, cleans orphans.

Flags
-----
  --mode MODE       Sync mode: update, push, or mirror (default: update)
  --sync            [Deprecated] Alias for --mode update
  --usb PATH        USB mount point, e.g. /Volumes/MYUSB (auto-detected if omitted)
  --dry-run         Preview what would be written without touching anything

Examples
--------
  python3.11 traktor_to_usb.py --select --usb /Volumes/MYUSB
  python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB --mode update
  python3.11 traktor_to_usb.py --playlists "03 - Events" --usb /Volumes/MYUSB --mode push
  python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB --mode mirror --dry-run
  python3.11 traktor_to_usb.py --select --dry-run

What it writes
--------------
  /PIONEER/rekordbox/exportLibrary.db       CDJ-3000 / XDJ-RX3 / XDJ-XZ
  /PIONEER/rekordbox/masterPlaylists6.xml   playlist display manifest
  /PIONEER/USBANLZ/…/ANLZ0000.DAT/.EXT     waveforms, beat grids, cue points
  /Contents/<Artist>/<track>               audio files

Sync state
----------
  A row is stored in exportLibrary.db djmdProperty (DBID='_sync_state') with
  the highest rb_local_usn seen from master.db at the time of last sync.
  On --sync, only records with rb_local_usn > that value are processed.

Requirements
------------
  python3.11, sqlcipher3, questionary
"""

import argparse, datetime, os, shutil, sys, time, uuid, zlib, atexit
from pathlib import Path

import sqlcipher3 as sqlite3

# ── Auto-save checkpoint handler ────────────────────────────────────────────
_checkpoint_callback = None
_last_save_time = 0
_dirty = False

def set_checkpoint_callback(cb):
    """Register a callback to be called at checkpoint (e.g., to save to disk)."""
    global _checkpoint_callback
    _checkpoint_callback = cb
    atexit.register(force_checkpoint)  # Ensure save on exit

def mark_dirty():
    """Mark that changes have been made."""
    global _dirty
    _dirty = True

def checkpoint(reason=""):
    """Save changes if dirty, with optional reason."""
    global _dirty, _last_save_time
    if _dirty and _checkpoint_callback:
        _checkpoint_callback(reason)
        _dirty = False
        _last_save_time = time.time()

def force_checkpoint():
    """Force a save regardless of dirty state (e.g., on exit)."""
    if _checkpoint_callback:
        _checkpoint_callback("Force save (exit)")

# ── Config ─────────────────────────────────────────────────────────────────────
MASTER_DB  = Path.home() / "Library/Pioneer/rekordbox/master.db"
KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
# Device Library Plus key (exportLibrary.db on USB) — different from master.db key
EXPORT_KEY = "r8gddnr4k847830ar6cqzbkk0el6qytmb3trbbx805jm74vez64i5o8fnrqryqls"
PIONEER_DIR = "PIONEER"
AUDIO_DIR   = "Contents"

# ── Helpers ────────────────────────────────────────────────────────────────────
def ts():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime('%Y-%m-%d %H:%M:%S.') + f'{now.microsecond//1000:03d} +00:00'

def safe_copy(src, dst):
    """Copy file to USB, falling back to shutil.copy if copy2 fails (FAT32 chflags)."""
    try:
        shutil.copy2(src, dst)
    except OSError:
        shutil.copy(src, dst)

def now_ms():
    return int(time.time() * 1000)

def make_id(s):
    return zlib.crc32(s.encode('utf-8')) & 0xFFFFFFFF

def new_uuid():
    return str(uuid.uuid4())

def to_hex(n):
    return format(int(n), 'X').upper()

def open_db(path, key=KEY):
    con = sqlite3.connect(str(path), timeout=30)
    con.execute(f"PRAGMA key='{key}'")
    con.execute("PRAGMA cipher='sqlcipher'")
    con.execute("PRAGMA legacy=4")
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("PRAGMA busy_timeout=30000")
    return con

def open_export_db(path, key=EXPORT_KEY):
    """Open a Device Library Plus database (exportLibrary.db on USB).
    Uses SQLCipher 4 defaults (no legacy mode) and the export key."""
    con = sqlite3.connect(str(path), timeout=30)
    con.execute(f"PRAGMA key='{key}'")
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("PRAGMA busy_timeout=30000")
    return con

# ── Auto-detect USB ────────────────────────────────────────────────────────────
def detect_pioneer_usbs():
    """Return list of mounted Pioneer USB paths."""
    candidates = []
    volumes = Path("/Volumes")
    if not volumes.exists():
        return candidates
    for vol in volumes.iterdir():
        pioneer = vol / PIONEER_DIR
        if pioneer.is_dir():
            candidates.append(vol)
    return sorted(candidates)

# ── Wipe USB ───────────────────────────────────────────────────────────────────
def wipe_usb(usb_path: Path, dry_run: bool = False):
    """Remove all Rekordbox data from a Pioneer USB (DB, playlists XML, ANLZ, audio)."""
    usb_rb_dir  = usb_path / PIONEER_DIR / "rekordbox"
    usb_anlz    = usb_path / PIONEER_DIR / "USBANLZ"
    audio_dir   = usb_path / AUDIO_DIR

    existing = [(d, d.relative_to(usb_path)) for d in [usb_rb_dir, usb_anlz, audio_dir] if d.exists()]

    if not existing:
        print("Nothing to wipe — USB appears clean.")
        return True

    print(f"\n🗑️  Wipe USB: {usb_path.name}")
    for d, rel in existing:
        print(f"  Will delete: {rel}/")

    if dry_run:
        print("\n📋 DRY RUN — nothing deleted.")
        return True

    import shutil
    for d, rel in existing:
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Wiped {rel}/")

    # Recreate empty DB structure so next export starts clean
    usb_db_path = usb_rb_dir / "exportLibrary.db"
    if not usb_db_path.exists():
        con = open_db(usb_db_path)
        init_usb_db(con, usb_path)
        con.close()

    print(f"\n✅ USB wiped. Ready for fresh export.")
    return True

# ── Schema — full Rekordbox 6 schema from master.db ────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS `agentNotification` (`ID` BIGINT PRIMARY KEY, `graphic_area` TINYINT(1) DEFAULT 0, `text_area` TINYINT(1) DEFAULT 0, `os_notification` TINYINT(1) DEFAULT 0, `start_datetime` DATETIME DEFAULT NULL, `end_datetime` DATETIME DEFAULT NULL, `display_datetime` DATETIME DEFAULT NULL, `interval` INTEGER DEFAULT 0, `category` VARCHAR(255) DEFAULT NULL, `category_color` VARCHAR(255) DEFAULT NULL, `title` TEXT DEFAULT NULL, `description` TEXT DEFAULT NULL, `url` VARCHAR(255) DEFAULT NULL, `image` VARCHAR(255) DEFAULT NULL, `image_path` VARCHAR(255) DEFAULT NULL, `read_status` INTEGER DEFAULT 0, `last_displayed_datetime` DATETIME DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `agentNotificationLog` (`ID` INTEGER PRIMARY KEY AUTOINCREMENT, `gigya_uid` VARCHAR(255) DEFAULT NULL, `event_date` INTEGER DEFAULT NULL, `reported_datetime` DATETIME DEFAULT NULL, `kind` INTEGER DEFAULT NULL, `value` INTEGER DEFAULT NULL, `notification_id` BIGINT DEFAULT NULL, `link` VARCHAR(255) DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `agentRegistry` (`registry_id` VARCHAR(255) PRIMARY KEY, `id_1` VARCHAR(255) DEFAULT NULL, `id_2` VARCHAR(255) DEFAULT NULL, `int_1` BIGINT DEFAULT NULL, `int_2` BIGINT DEFAULT NULL, `str_1` VARCHAR(255) DEFAULT NULL, `str_2` VARCHAR(255) DEFAULT NULL, `date_1` DATETIME DEFAULT NULL, `date_2` DATETIME DEFAULT NULL, `text_1` TEXT DEFAULT NULL, `text_2` TEXT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `cloudAgentRegistry` (`ID` VARCHAR(255) PRIMARY KEY, `int_1` BIGINT DEFAULT NULL, `int_2` BIGINT DEFAULT NULL, `str_1` VARCHAR(255) DEFAULT NULL, `str_2` VARCHAR(255) DEFAULT NULL, `date_1` DATETIME DEFAULT NULL, `date_2` DATETIME DEFAULT NULL, `text_1` TEXT DEFAULT NULL, `text_2` TEXT DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `contentActiveCensor` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `ActiveCensors` TEXT DEFAULT NULL, `rb_activecensor_count` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `contentCue` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `Cues` TEXT DEFAULT NULL, `rb_cue_count` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `contentFile` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `Path` VARCHAR(255) DEFAULT NULL, `Hash` VARCHAR(255) DEFAULT NULL, `Size` INTEGER DEFAULT NULL, `rb_local_path` VARCHAR(255) DEFAULT NULL, `rb_insync_hash` VARCHAR(255) DEFAULT NULL, `rb_insync_local_usn` BIGINT DEFAULT NULL, `rb_file_hash_dirty` INTEGER DEFAULT 0, `rb_local_file_status` INTEGER DEFAULT 0, `rb_in_progress` TINYINT(1) DEFAULT 0, `rb_process_type` INTEGER DEFAULT 0, `rb_temp_path` VARCHAR(255) DEFAULT NULL, `rb_priority` INTEGER DEFAULT 50, `rb_file_size_dirty` INTEGER DEFAULT 0, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdActiveCensor` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `InMsec` INTEGER DEFAULT NULL, `OutMsec` INTEGER DEFAULT NULL, `Info` INTEGER DEFAULT NULL, `ParameterList` TEXT DEFAULT NULL, `ContentUUID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdAlbum` (`ID` VARCHAR(255) PRIMARY KEY, `Name` VARCHAR(255) DEFAULT NULL, `AlbumArtistID` VARCHAR(255) DEFAULT NULL, `ImagePath` VARCHAR(255) DEFAULT NULL, `Compilation` INTEGER DEFAULT NULL, `SearchStr` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdArtist` (`ID` VARCHAR(255) PRIMARY KEY, `Name` VARCHAR(255) DEFAULT NULL, `SearchStr` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdCategory` (`ID` VARCHAR(255) PRIMARY KEY, `MenuItemID` VARCHAR(255) DEFAULT NULL, `Seq` INTEGER DEFAULT NULL, `Disable` INTEGER DEFAULT NULL, `InfoOrder` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdCloudProperty` (`ID` VARCHAR(255) PRIMARY KEY, `Reserved1` TEXT DEFAULT NULL, `Reserved2` TEXT DEFAULT NULL, `Reserved3` TEXT DEFAULT NULL, `Reserved4` TEXT DEFAULT NULL, `Reserved5` TEXT DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdColor` (`ID` VARCHAR(255) PRIMARY KEY, `ColorCode` INTEGER DEFAULT NULL, `SortKey` INTEGER DEFAULT NULL, `Commnt` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdContent` (`ID` VARCHAR(255) PRIMARY KEY, `FolderPath` VARCHAR(255) DEFAULT NULL, `FileNameL` VARCHAR(255) DEFAULT NULL, `FileNameS` VARCHAR(255) DEFAULT NULL, `Title` VARCHAR(255) DEFAULT NULL, `ArtistID` VARCHAR(255) DEFAULT NULL, `AlbumID` VARCHAR(255) DEFAULT NULL, `GenreID` VARCHAR(255) DEFAULT NULL, `BPM` INTEGER DEFAULT NULL, `Length` INTEGER DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `BitRate` INTEGER DEFAULT NULL, `BitDepth` INTEGER DEFAULT NULL, `Commnt` TEXT DEFAULT NULL, `FileType` INTEGER DEFAULT NULL, `Rating` INTEGER DEFAULT NULL, `ReleaseYear` INTEGER DEFAULT NULL, `RemixerID` VARCHAR(255) DEFAULT NULL, `LabelID` VARCHAR(255) DEFAULT NULL, `OrgArtistID` VARCHAR(255) DEFAULT NULL, `KeyID` VARCHAR(255) DEFAULT NULL, `StockDate` VARCHAR(255) DEFAULT NULL, `ColorID` VARCHAR(255) DEFAULT NULL, `DJPlayCount` INTEGER DEFAULT NULL, `ImagePath` VARCHAR(255) DEFAULT NULL, `MasterDBID` VARCHAR(255) DEFAULT NULL, `MasterSongID` VARCHAR(255) DEFAULT NULL, `AnalysisDataPath` VARCHAR(255) DEFAULT NULL, `SearchStr` VARCHAR(255) DEFAULT NULL, `FileSize` INTEGER DEFAULT NULL, `DiscNo` INTEGER DEFAULT NULL, `ComposerID` VARCHAR(255) DEFAULT NULL, `Subtitle` VARCHAR(255) DEFAULT NULL, `SampleRate` INTEGER DEFAULT NULL, `DisableQuantize` INTEGER DEFAULT NULL, `Analysed` INTEGER DEFAULT NULL, `ReleaseDate` VARCHAR(255) DEFAULT NULL, `DateCreated` VARCHAR(255) DEFAULT NULL, `ContentLink` INTEGER DEFAULT NULL, `Tag` VARCHAR(255) DEFAULT NULL, `ModifiedByRBM` VARCHAR(255) DEFAULT NULL, `HotCueAutoLoad` VARCHAR(255) DEFAULT NULL, `DeliveryControl` VARCHAR(255) DEFAULT NULL, `DeliveryComment` VARCHAR(255) DEFAULT NULL, `CueUpdated` VARCHAR(255) DEFAULT NULL, `AnalysisUpdated` VARCHAR(255) DEFAULT NULL, `TrackInfoUpdated` VARCHAR(255) DEFAULT NULL, `Lyricist` VARCHAR(255) DEFAULT NULL, `ISRC` VARCHAR(255) DEFAULT NULL, `SamplerTrackInfo` INTEGER DEFAULT NULL, `SamplerPlayOffset` INTEGER DEFAULT NULL, `SamplerGain` FLOAT DEFAULT NULL, `VideoAssociate` VARCHAR(255) DEFAULT NULL, `LyricStatus` INTEGER DEFAULT NULL, `ServiceID` INTEGER DEFAULT NULL, `OrgFolderPath` VARCHAR(255) DEFAULT NULL, `Reserved1` TEXT DEFAULT NULL, `Reserved2` TEXT DEFAULT NULL, `Reserved3` TEXT DEFAULT NULL, `Reserved4` TEXT DEFAULT NULL, `ExtInfo` TEXT DEFAULT NULL, `rb_file_id` VARCHAR(255) DEFAULT NULL, `DeviceID` VARCHAR(255) DEFAULT NULL, `rb_LocalFolderPath` VARCHAR(255) DEFAULT NULL, `SrcID` VARCHAR(255) DEFAULT NULL, `SrcTitle` VARCHAR(255) DEFAULT NULL, `SrcArtistName` VARCHAR(255) DEFAULT NULL, `SrcAlbumName` VARCHAR(255) DEFAULT NULL, `SrcLength` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdCue` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `InMsec` INTEGER DEFAULT NULL, `InFrame` INTEGER DEFAULT NULL, `InMpegFrame` INTEGER DEFAULT NULL, `InMpegAbs` INTEGER DEFAULT NULL, `OutMsec` INTEGER DEFAULT NULL, `OutFrame` INTEGER DEFAULT NULL, `OutMpegFrame` INTEGER DEFAULT NULL, `OutMpegAbs` INTEGER DEFAULT NULL, `Kind` INTEGER DEFAULT NULL, `Color` INTEGER DEFAULT NULL, `ColorTableIndex` INTEGER DEFAULT NULL, `ActiveLoop` INTEGER DEFAULT NULL, `Comment` VARCHAR(255) DEFAULT NULL, `BeatLoopSize` INTEGER DEFAULT NULL, `CueMicrosec` INTEGER DEFAULT NULL, `InPointSeekInfo` VARCHAR(255) DEFAULT NULL, `OutPointSeekInfo` VARCHAR(255) DEFAULT NULL, `ContentUUID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdDevice` (`ID` VARCHAR(255) PRIMARY KEY, `MasterDBID` VARCHAR(255) DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdGenre` (`ID` VARCHAR(255) PRIMARY KEY, `Name` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdHistory` (`ID` VARCHAR(255) PRIMARY KEY, `Seq` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `Attribute` INTEGER DEFAULT NULL, `ParentID` VARCHAR(255) DEFAULT NULL, `DateCreated` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdHotCueBanklist` (`ID` VARCHAR(255) PRIMARY KEY, `Seq` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `ImagePath` VARCHAR(255) DEFAULT NULL, `Attribute` INTEGER DEFAULT NULL, `ParentID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdKey` (`ID` VARCHAR(255) PRIMARY KEY, `ScaleName` VARCHAR(255) DEFAULT NULL, `Seq` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdLabel` (`ID` VARCHAR(255) PRIMARY KEY, `Name` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdMenuItems` (`ID` VARCHAR(255) PRIMARY KEY, `Class` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdMixerParam` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `GainHigh` INTEGER DEFAULT NULL, `GainLow` INTEGER DEFAULT NULL, `PeakHigh` INTEGER DEFAULT NULL, `PeakLow` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdMyTag` (`ID` VARCHAR(255) PRIMARY KEY, `Seq` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `Attribute` INTEGER DEFAULT NULL, `ParentID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdPlaylist` (`ID` VARCHAR(255) PRIMARY KEY, `Seq` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `ImagePath` VARCHAR(255) DEFAULT NULL, `Attribute` INTEGER DEFAULT NULL, `ParentID` VARCHAR(255) DEFAULT NULL, `SmartList` TEXT DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdProperty` (`DBID` VARCHAR(255) PRIMARY KEY, `DBVersion` VARCHAR(255) DEFAULT NULL, `BaseDBDrive` VARCHAR(255) DEFAULT NULL, `CurrentDBDrive` VARCHAR(255) DEFAULT NULL, `DeviceID` VARCHAR(255) DEFAULT NULL, `Reserved1` TEXT DEFAULT NULL, `Reserved2` TEXT DEFAULT NULL, `Reserved3` TEXT DEFAULT NULL, `Reserved4` TEXT DEFAULT NULL, `Reserved5` TEXT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdRecommendLike` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID1` VARCHAR(255) DEFAULT NULL, `ContentID2` VARCHAR(255) DEFAULT NULL, `LikeRate` INTEGER DEFAULT NULL, `DataCreatedH` INTEGER DEFAULT NULL, `DataCreatedL` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdRelatedTracks` (`ID` VARCHAR(255) PRIMARY KEY, `Seq` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `Attribute` INTEGER DEFAULT NULL, `ParentID` VARCHAR(255) DEFAULT NULL, `Criteria` TEXT DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSampler` (`ID` VARCHAR(255) PRIMARY KEY, `Seq` INTEGER DEFAULT NULL, `Name` VARCHAR(255) DEFAULT NULL, `Attribute` INTEGER DEFAULT NULL, `ParentID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSharedPlaylist` (`ID` VARCHAR(255) PRIMARY KEY, `data_selection` TINYINT DEFAULT 0, `edited_at` DATETIME DEFAULT NULL, `int_1` INTEGER DEFAULT NULL, `int_2` INTEGER DEFAULT NULL, `str_1` VARCHAR(255) DEFAULT NULL, `str_2` VARCHAR(255) DEFAULT NULL, `text_1` TEXT DEFAULT NULL, `text_2` TEXT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSharedPlaylistUser` (`ID` VARCHAR(255) NOT NULL, `member_type` TINYINT DEFAULT 0, `member_id` VARCHAR(255) NOT NULL, `status` TINYINT DEFAULT 0, `invitation_expires_at` DATETIME DEFAULT NULL, `invited_at` DATETIME DEFAULT NULL, `joined_at` DATETIME DEFAULT NULL, `int_1` INTEGER DEFAULT NULL, `int_2` INTEGER DEFAULT NULL, `str_1` VARCHAR(255) DEFAULT NULL, `str_2` VARCHAR(255) DEFAULT NULL, `text_1` TEXT DEFAULT NULL, `text_2` TEXT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL, PRIMARY KEY (`ID`, `member_id`));
CREATE TABLE IF NOT EXISTS `djmdSongHistory` (`ID` VARCHAR(255) PRIMARY KEY, `HistoryID` VARCHAR(255) DEFAULT NULL, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSongHotCueBanklist` (`ID` VARCHAR(255) PRIMARY KEY, `HotCueBanklistID` VARCHAR(255) DEFAULT NULL, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `CueID` VARCHAR(255) DEFAULT NULL, `InMsec` INTEGER DEFAULT NULL, `InFrame` INTEGER DEFAULT NULL, `InMpegFrame` INTEGER DEFAULT NULL, `InMpegAbs` INTEGER DEFAULT NULL, `OutMsec` INTEGER DEFAULT NULL, `OutFrame` INTEGER DEFAULT NULL, `OutMpegFrame` INTEGER DEFAULT NULL, `OutMpegAbs` INTEGER DEFAULT NULL, `Color` INTEGER DEFAULT NULL, `ColorTableIndex` INTEGER DEFAULT NULL, `ActiveLoop` INTEGER DEFAULT NULL, `Comment` VARCHAR(255) DEFAULT NULL, `BeatLoopSize` INTEGER DEFAULT NULL, `CueMicrosec` INTEGER DEFAULT NULL, `InPointSeekInfo` VARCHAR(255) DEFAULT NULL, `OutPointSeekInfo` VARCHAR(255) DEFAULT NULL, `HotCueBanklistUUID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSongMyTag` (`ID` VARCHAR(255) PRIMARY KEY, `MyTagID` VARCHAR(255) DEFAULT NULL, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSongPlaylist` (`ID` VARCHAR(255) PRIMARY KEY, `PlaylistID` VARCHAR(255) DEFAULT NULL, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSongRelatedTracks` (`ID` VARCHAR(255) PRIMARY KEY, `RelatedTracksID` VARCHAR(255) DEFAULT NULL, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSongSampler` (`ID` VARCHAR(255) PRIMARY KEY, `SamplerID` VARCHAR(255) DEFAULT NULL, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSongTagList` (`ID` VARCHAR(255) PRIMARY KEY, `ContentID` VARCHAR(255) DEFAULT NULL, `TrackNo` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `djmdSort` (`ID` VARCHAR(255) PRIMARY KEY, `MenuItemID` VARCHAR(255) DEFAULT NULL, `Seq` INTEGER DEFAULT NULL, `Disable` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `hotCueBanklistCue` (`ID` VARCHAR(255) PRIMARY KEY, `HotCueBanklistID` VARCHAR(255) DEFAULT NULL, `Cues` TEXT DEFAULT NULL, `rb_cue_count` INTEGER DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `imageFile` (`ID` VARCHAR(255) PRIMARY KEY, `TableName` VARCHAR(255) DEFAULT NULL, `TargetUUID` VARCHAR(255) DEFAULT NULL, `TargetID` VARCHAR(255) DEFAULT NULL, `Path` VARCHAR(255) DEFAULT NULL, `Hash` VARCHAR(255) DEFAULT NULL, `Size` INTEGER DEFAULT NULL, `rb_local_path` VARCHAR(255) DEFAULT NULL, `rb_insync_hash` VARCHAR(255) DEFAULT NULL, `rb_insync_local_usn` BIGINT DEFAULT NULL, `rb_file_hash_dirty` INTEGER DEFAULT 0, `rb_local_file_status` INTEGER DEFAULT 0, `rb_in_progress` TINYINT(1) DEFAULT 0, `rb_process_type` INTEGER DEFAULT 0, `rb_temp_path` VARCHAR(255) DEFAULT NULL, `rb_priority` INTEGER DEFAULT 50, `rb_file_size_dirty` INTEGER DEFAULT 0, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `settingFile` (`ID` VARCHAR(255) PRIMARY KEY, `Path` VARCHAR(255) DEFAULT NULL, `Hash` VARCHAR(255) DEFAULT NULL, `Size` INTEGER DEFAULT NULL, `rb_local_path` VARCHAR(255) DEFAULT NULL, `rb_insync_hash` VARCHAR(255) DEFAULT NULL, `rb_insync_local_usn` BIGINT DEFAULT NULL, `rb_file_hash_dirty` INTEGER DEFAULT 0, `rb_file_size_dirty` INTEGER DEFAULT 0, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
CREATE TABLE IF NOT EXISTS `uuidIDMap` (`ID` VARCHAR(255) PRIMARY KEY, `TableName` VARCHAR(255) DEFAULT NULL, `TargetUUID` VARCHAR(255) DEFAULT NULL, `CurrentID` VARCHAR(255) DEFAULT NULL, `UUID` VARCHAR(255) DEFAULT NULL, `rb_data_status` INTEGER DEFAULT 0, `rb_local_data_status` INTEGER DEFAULT 0, `rb_local_deleted` TINYINT(1) DEFAULT 0, `rb_local_synced` TINYINT(1) DEFAULT 0, `usn` BIGINT DEFAULT NULL, `rb_local_usn` BIGINT DEFAULT NULL, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL);
"""

def init_usb_db(usb_con, usb_path: Path):
    usb_con.executescript(SCHEMA_SQL)
    master = open_db(MASTER_DB)

    # Copy djmdKey with full Rekordbox 6 schema
    for k in master.execute(
        "SELECT ID, ScaleName, Seq, UUID, rb_data_status, rb_local_data_status, "
        "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at "
        "FROM djmdKey"
    ).fetchall():
        usb_con.execute(
            "INSERT OR IGNORE INTO djmdKey "
            "(ID, ScaleName, Seq, UUID, rb_data_status, rb_local_data_status, "
            "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", k)

    # Copy djmdColor with full schema (includes UUID, rb_* status columns)
    for c in master.execute(
        "SELECT ID, ColorCode, SortKey, Commnt, UUID, rb_data_status, rb_local_data_status, "
        "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at "
        "FROM djmdColor"
    ).fetchall():
        usb_con.execute(
            "INSERT OR IGNORE INTO djmdColor "
            "(ID, ColorCode, SortKey, Commnt, UUID, rb_data_status, rb_local_data_status, "
            "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", c)

    # Copy djmdMenuItems from master.db
    for m in master.execute(
        "SELECT ID, Class, Name, UUID, rb_data_status, rb_local_data_status, "
        "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at "
        "FROM djmdMenuItems"
    ).fetchall():
        usb_con.execute(
            "INSERT OR IGNORE INTO djmdMenuItems "
            "(ID, Class, Name, UUID, rb_data_status, rb_local_data_status, "
            "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", m)

    # Copy djmdCategory from master.db
    for cat in master.execute(
        "SELECT ID, MenuItemID, Seq, Disable, InfoOrder, UUID, rb_data_status, rb_local_data_status, "
        "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at "
        "FROM djmdCategory"
    ).fetchall():
        usb_con.execute(
            "INSERT OR IGNORE INTO djmdCategory "
            "(ID, MenuItemID, Seq, Disable, InfoOrder, UUID, rb_data_status, rb_local_data_status, "
            "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", cat)

    # Copy djmdSort from master.db (required for Rekordbox to display content)
    sort_cols = [d[0] for d in master.execute("SELECT * FROM djmdSort LIMIT 1").description]
    for row in master.execute("SELECT * FROM djmdSort").fetchall():
        usb_con.execute(
            f"INSERT OR IGNORE INTO djmdSort ({','.join(sort_cols)}) "
            f"VALUES ({','.join(['?']*len(row))})", row)

    master.close()

    db_id = str(make_id(str(usb_path)))
    now = ts()

    # djmdProperty — correct Rekordbox 6 schema
    # Reserved1 is used to persist the last sync USN (see save_sync_usn)
    usb_con.execute(
        "INSERT OR IGNORE INTO djmdProperty "
        "(DBID, DBVersion, BaseDBDrive, CurrentDBDrive, DeviceID, "
        "Reserved1, Reserved2, Reserved3, Reserved4, Reserved5, created_at, updated_at) "
        "VALUES (?, '6000', '', '', ?, '', '', '', '', '', ?, ?)",
        (db_id, new_uuid(), now, now))

    # djmdDevice — register this USB as a known device
    usb_con.execute(
        "INSERT OR IGNORE INTO djmdDevice "
        "(ID, MasterDBID, Name, UUID, rb_data_status, rb_local_data_status, "
        "rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 0, 0, 0, 0, 1, 1, ?, ?)",
        (new_uuid(), db_id, usb_path.name, new_uuid(), now, now))

    usb_con.commit()
    # Switch to WAL journal mode (matching Rekordbox's USB export format)
    usb_con.execute("PRAGMA journal_mode=WAL")

# ── Sync state helpers ─────────────────────────────────────────────────────────
# Sync USN is stored in djmdProperty.Reserved1 (the real schema has no rb_local_usn
# on djmdProperty; Reserved1 is a TEXT field we repurpose for this).

def get_last_sync_usn(usb_con) -> int:
    """Return the last synced USN (stored in djmdProperty.Reserved1), or 0 on first sync.
    Falls back to 0 gracefully if the DB has an old schema (no Reserved1 column)."""
    try:
        row = usb_con.execute("SELECT Reserved1 FROM djmdProperty LIMIT 1").fetchone()
        if row and row[0]:
            return int(row[0])
    except Exception:
        pass
    return 0

def save_sync_usn(usb_con, usn: int):
    """Persist the highest master.db USN seen during this sync into djmdProperty.Reserved1."""
    usb_con.execute(
        "UPDATE djmdProperty SET Reserved1=? WHERE DBID IS NOT NULL",
        (str(usn),))
    usb_con.commit()

# ── Playlist tree ──────────────────────────────────────────────────────────────
def get_playlist_tree(con):
    """Return dict: tuple-path → (id_str, attribute)"""
    def recurse(parent_id, prefix):
        out = {}
        for r in con.execute(
            "SELECT ID, Name, Attribute FROM djmdPlaylist WHERE ParentID=? ORDER BY Seq",
            (str(parent_id),)
        ).fetchall():
            path = prefix + (r[1],)
            out[path] = (str(r[0]), r[2])
            out.update(recurse(r[0], path))
        return out
    tree = {}
    for r in con.execute(
        "SELECT ID, Name, Attribute FROM djmdPlaylist WHERE ParentID='root' ORDER BY Seq"
    ).fetchall():
        path = (r[1],)
        tree[path] = (str(r[0]), r[2])
        tree.update(recurse(r[0], path))
    return tree

def collect_playlist_ids(tree, selected_roots):
    """Return set of playlist IDs under any of the selected root names."""
    selected = set()
    for path, (pl_id, attr) in tree.items():
        if attr == 0:
            if not selected_roots or any(seg in selected_roots for seg in path):
                selected.add(pl_id)
    return selected

# ── Interactive playlist selector ──────────────────────────────────────────────
def run_selector(tree) -> list:
    """
    Show a two-level checkbox menu:
      • Top-level folders shown as headers
      • Selecting a folder toggles all its children
      • Individual playlists can be checked independently
    Returns list of selected playlist IDs.
    """
    try:
        import questionary
        from questionary import Choice, Separator
    except ImportError:
        print("questionary not installed. Run: pip3.11 install questionary")
        sys.exit(1)

    # Build ordered list of choices
    choices = []
    # Gather top-level items
    top_level = [(path, info) for path, info in tree.items() if len(path) == 1]
    top_level.sort(key=lambda x: x[0])

    for (top_path, (top_id, top_attr)) in top_level:
        if top_attr == 1:  # folder
            # Count playlists inside
            children_playlists = [
                (path, pl_id) for path, (pl_id, attr) in tree.items()
                if attr == 0 and len(path) > 1 and path[0] == top_path[0]
            ]
            choices.append(Separator(f"\n── {top_path[0]} ({len(children_playlists)} playlists) ──"))
            # Add sub-folder and playlist entries
            for path, (pl_id, attr) in sorted(tree.items()):
                if attr == 0 and len(path) >= 2 and path[0] == top_path[0]:
                    indent = "  " * (len(path) - 1)
                    label = indent + " / ".join(path[1:])
                    choices.append(Choice(title=label, value=pl_id))
        else:  # root-level playlist
            choices.append(Choice(title=top_path[0], value=top_id))

    if not choices:
        print("No playlists found in library.")
        sys.exit(1)

    print("\n  Use SPACE to select, A to toggle all, ENTER to confirm\n")
    selected = questionary.checkbox(
        "Select playlists to export:",
        choices=choices,
        style=questionary.Style([
            ('qmark',         'fg:#00bcd4 bold'),
            ('question',      'bold'),
            ('answer',        'fg:#00bcd4 bold'),
            ('pointer',       'fg:#00bcd4 bold'),
            ('highlighted',   'fg:#00bcd4 bold'),
            ('selected',      'fg:#00bcd4'),
            ('separator',     'fg:#888888'),
            ('instruction',   'fg:#888888'),
        ])
    ).ask()

    if selected is None:
        print("Cancelled.")
        sys.exit(0)

    # Auto-save checkpoint: user made a playlist selection
    checkpoint("Playlist selection confirmed")
    return selected  # list of pl_id strings

# ── Core export ────────────────────────────────────────────────────────────────
MODE_LABELS = {'update': 'library update', 'push': 'selective push', 'mirror': 'mirror sync'}

def export_to_usb(usb_path: Path, playlist_ids: set, tree: dict, mode: str = 'update', dry_run: bool = False, fetch_nas: bool = False):
    usb_rb_dir  = usb_path / PIONEER_DIR / "rekordbox"
    usb_anlz    = usb_path / PIONEER_DIR / "USBANLZ"
    usb_audio   = usb_path / AUDIO_DIR
    usb_db_path = usb_rb_dir / "exportLibrary.db"

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Exporting to: {usb_path}")
    print(f"  Mode: {MODE_LABELS.get(mode, mode)}")
    print(f"  Playlists: {len(playlist_ids)}")

    # ── Open master.db ────────────────────────────────────────────────────────
    master = open_db(MASTER_DB)
    max_master_usn = master.execute("SELECT MAX(rb_local_usn) FROM djmdContent").fetchone()[0] or 0

    # ── Determine which content IDs to process ────────────────────────────────
    if playlist_ids:
        ph = ','.join('?' * len(playlist_ids))
        all_content_ids = set(
            r[0] for r in master.execute(
                f"SELECT DISTINCT ContentID FROM djmdSongPlaylist WHERE PlaylistID IN ({ph})",
                list(playlist_ids)
            ).fetchall()
        )
    else:
        all_content_ids = set(
            r[0] for r in master.execute("SELECT ID FROM djmdContent").fetchall()
        )
    print(f"  Total tracks in scope: {len(all_content_ids)}")

    # ── Determine existing USB state ─────────────────────────────────────────
    existing_ids = set()
    last_usn = 0
    if usb_db_path.exists():
        try:
            usb_con_check = open_db(usb_db_path)
            last_usn = get_last_sync_usn(usb_con_check)
            existing_ids = set(
                r[0] for r in usb_con_check.execute("SELECT ID FROM djmdContent").fetchall()
            )
            usb_con_check.close()
            print(f"  Last sync USN: {last_usn}  →  master USN: {max_master_usn}")
        except Exception as e:
            print(f"  ⚠️  Could not read USB DB: {e}")
            print(f"  Tip: Ensure USB is still connected and not being accessed by Rekordbox")
            raise

    # ── Compute tracks to process and deletions based on mode ────────────────
    changed_ids = set()

    if mode == 'update':
        # New tracks: in scope but not yet on USB
        new_ids = all_content_ids - existing_ids
        # Changed tracks: already on USB but updated since last sync
        if last_usn > 0:
            changed_ids = {r[0] for r in master.execute(
                "SELECT ID FROM djmdContent WHERE rb_local_usn > ?", (last_usn,)
            ).fetchall()} & existing_ids
        # Delete only tracks completely gone from master.db
        all_master_ids = set(r[0] for r in master.execute(
            "SELECT ID FROM djmdContent"
        ).fetchall())
        deleted_ids = existing_ids - all_master_ids
        tracks_to_process = new_ids | changed_ids
        print(f"  New: {len(new_ids)}  Changed: {len(changed_ids)}  Deleted: {len(deleted_ids)}")

    elif mode == 'push':
        # Only add tracks not already on USB — never delete
        tracks_to_process = all_content_ids - existing_ids
        deleted_ids = set()
        print(f"  New: {len(tracks_to_process)}  (push mode — no deletions)")

    elif mode == 'mirror':
        # New tracks: in scope but not on USB
        new_ids = all_content_ids - existing_ids
        # Changed tracks: on USB and updated since last sync, within scope
        if last_usn > 0:
            changed_ids = {r[0] for r in master.execute(
                "SELECT ID FROM djmdContent WHERE rb_local_usn > ?", (last_usn,)
            ).fetchall()} & all_content_ids
        # Delete tracks no longer in scope
        deleted_ids = existing_ids - all_content_ids
        tracks_to_process = new_ids | changed_ids
        print(f"  New: {len(new_ids)}  Changed: {len(changed_ids)}  Deleted: {len(deleted_ids)}")

    # ── Load track metadata ────────────────────────────────────────────────────
    tracks = {}
    if tracks_to_process:
        ph2 = ','.join('?' * len(tracks_to_process))
        for r in master.execute(f"""
            SELECT c.ID, c.FolderPath, c.FileNameL, c.Title, c.BPM, c.Length,
                   c.FileType, c.BitRate, c.SampleRate, c.Commnt, c.Rating,
                   c.ColorID, c.KeyID, c.UUID, a.Name
            FROM djmdContent c
            LEFT JOIN djmdArtist a ON c.ArtistID = a.ID
            WHERE c.ID IN ({ph2})
        """, list(tracks_to_process)).fetchall():
            tracks[r[0]] = r

    # ANLZ mapping for tracks to process
    anlz_map = {}
    if tracks_to_process:
        for r in master.execute(
            f"SELECT ContentID, Path, rb_local_path FROM contentFile WHERE ContentID IN ({ph2})",
            list(tracks_to_process)
        ).fetchall():
            anlz_map.setdefault(r[0], []).append((r[1], r[2]))

    # Cue points for tracks to process
    cues = {}
    if tracks_to_process:
        for r in master.execute(
            f"SELECT * FROM djmdCue WHERE ContentID IN ({ph2})",
            list(tracks_to_process)
        ).fetchall():
            cues.setdefault(r[1], []).append(r)

    master.close()

    # ── NAS lookup for missing tracks ──────────────────────────────────────────
    nas_available = {}
    if fetch_nas:
        try:
            from nas_lookup import lookup_nas_tracks, check_traktor_ml_reachable, TRAKTOR_ML_API
            # Collect paths of all tracks to check which are missing locally
            missing_paths = []
            for cid, row in tracks.items():
                folder_path = row[1]
                if folder_path and not Path(folder_path).exists():
                    missing_paths.append(folder_path)
            if missing_paths:
                nas_available = lookup_nas_tracks(missing_paths)
                nas_reachable = check_traktor_ml_reachable()
                if nas_available and not nas_reachable:
                    print(f"  ⚠️  {len(nas_available)} tracks found on NAS but traktor-ml API is unreachable")
                    print(f"      Start the server and SSH tunnel to fetch them")
                    nas_available = {}
                elif nas_available:
                    total_size = sum(t.size_bytes for t in nas_available.values())
                    print(f"  🌐 NAS: {len(nas_available)} tracks available ({total_size / 1_048_576:.0f} MB)")
        except ImportError:
            print("  ⚠️  nas_lookup.py not found — --fetch-nas disabled")
            fetch_nas = False

    if dry_run:
        # Count local vs NAS vs truly missing
        local_count = 0
        nas_count = len(nas_available)
        truly_missing = 0
        for cid, row in tracks.items():
            folder_path = row[1]
            if folder_path and Path(folder_path).exists():
                local_count += 1
            elif folder_path and folder_path in nas_available:
                pass  # already counted in nas_count
            else:
                truly_missing += 1

        print(f"\n  Would copy {local_count} local audio files")
        if fetch_nas and nas_count > 0:
            total_nas_size = sum(t.size_bytes for t in nas_available.values())
            print(f"  Would fetch {nas_count} tracks from NAS ({total_nas_size / 1_048_576:.0f} MB)")
        if truly_missing > 0:
            print(f"  ⚠️  {truly_missing} tracks unavailable (not local or NAS)")
        print(f"  Would copy {sum(len(v) for v in anlz_map.values())} ANLZ files")
        if deleted_ids:
            print(f"  Would remove {len(deleted_ids)} deleted tracks from DB")
        if mode == 'push':
            print(f"  Would merge {len(playlist_ids)} playlists into existing tree (push — no wipe)")
        elif mode == 'mirror':
            print(f"  Would rebuild playlist tree ({len(playlist_ids)} playlists, mirror — exact match)")
            print(f"  Would clean up orphaned tracks not in any playlist")
        else:
            print(f"  Would rebuild playlist tree ({len(playlist_ids)} playlists)")
        return

    # ── Prepare directories + DB ───────────────────────────────────────────────
    for d in [usb_rb_dir, usb_anlz, usb_audio]:
        d.mkdir(parents=True, exist_ok=True)

    is_fresh = not usb_db_path.exists()
    usb_con = open_db(usb_db_path)
    if is_fresh:
        init_usb_db(usb_con, usb_path)

    usn = 1  # USN to stamp all our writes with
    usb_db_id = str(make_id(str(usb_path)))  # This USB's DBID (matches djmdProperty.DBID)

    # ── Artist cache ──────────────────────────────────────────────────────────
    artist_cache = {}
    def get_or_insert_artist(name):
        if not name:
            return None
        if name in artist_cache:
            return artist_cache[name]
        aid = str(make_id(f"artist:{name}"))
        usb_con.execute("""INSERT OR IGNORE INTO djmdArtist
            (ID, Name, SearchStr, UUID, rb_data_status, rb_local_data_status,
             rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at)
            VALUES (?,?,?,?,0,0,0,0,?,?,?,?)""",
            (aid, name, name, new_uuid(), usn, usn, ts(), ts()))
        artist_cache[name] = aid
        return aid

    # ── Remove deleted tracks ─────────────────────────────────────────────────
    if deleted_ids:
        ph_del = ','.join('?' * len(deleted_ids))
        usb_con.execute(f"DELETE FROM djmdSongPlaylist WHERE ContentID IN ({ph_del})", list(deleted_ids))
        usb_con.execute(f"DELETE FROM djmdCue WHERE ContentID IN ({ph_del})", list(deleted_ids))
        usb_con.execute(f"DELETE FROM djmdContent WHERE ID IN ({ph_del})", list(deleted_ids))
        print(f"  🗑  Removed {len(deleted_ids)} deleted tracks")

    # ── Copy audio + ANLZ, insert into DB ─────────────────────────────────────
    copied_audio = 0
    skipped_audio = 0
    copied_anlz  = 0
    missing_audio = []
    fetched_from_nas = 0
    nas_fetch_failed = 0

    total = len(tracks)
    for i, (cid, row) in enumerate(tracks.items(), 1):
        if i % 200 == 0 or i == total:
            print(f"  [{i}/{total}] Processing tracks…", end='\r')

        (db_id, folder_path, filename, title, bpm, length, ftype,
         bitrate, samplerate, comment, rating, color_id, key_id, track_uuid, artist_name) = row

        # Audio
        artist_slug = (artist_name or 'Unknown').replace('/', '_').replace(':', '_')[:50]
        src_audio = Path(folder_path) if folder_path else None
        got_audio = False

        if src_audio and src_audio.exists():
            # File exists locally — copy to USB
            dst_dir = usb_audio / artist_slug
            dst_dir.mkdir(exist_ok=True)
            dst_audio = dst_dir / filename
            if not dst_audio.exists():
                safe_copy(src_audio, dst_audio)
                copied_audio += 1
            else:
                skipped_audio += 1
            got_audio = True

        elif fetch_nas and folder_path and folder_path in nas_available:
            # File missing locally but available on NAS — download to USB
            from nas_lookup import download_from_nas, TRAKTOR_ML_API
            dst_dir = usb_audio / artist_slug
            dst_dir.mkdir(exist_ok=True)
            dst_audio = dst_dir / filename
            if dst_audio.exists():
                skipped_audio += 1
                got_audio = True
            else:
                nas_info = nas_available[folder_path]
                if download_from_nas(folder_path, dst_audio, TRAKTOR_ML_API, nas_info.file_hash):
                    fetched_from_nas += 1
                    got_audio = True
                else:
                    nas_fetch_failed += 1

        if not got_audio:
            if cid in existing_ids:
                # Track already on USB — keep its audio, just update DB entry
                usb_audio_rel = f"/{AUDIO_DIR}/{artist_slug}/{filename}"
                skipped_audio += 1
            else:
                # Track is genuinely missing — skip entirely
                if folder_path:
                    missing_audio.append(folder_path)
                continue

        else:
            usb_audio_rel = f"/{AUDIO_DIR}/{artist_slug}/{filename}"

        # ANLZ
        for (usb_anlz_path, local_anlz_path) in anlz_map.get(cid, []):
            if not local_anlz_path:
                continue
            src = Path(local_anlz_path)
            if not src.exists():
                continue
            rel_parts = Path(usb_anlz_path.lstrip('/')).parts
            if len(rel_parts) >= 3 and rel_parts[0] == 'PIONEER' and rel_parts[1] == 'USBANLZ':
                dst_anlz = usb_path / PIONEER_DIR / 'USBANLZ' / Path(*rel_parts[2:])
            else:
                dst_anlz = usb_anlz / Path(usb_anlz_path.lstrip('/'))
            dst_anlz.parent.mkdir(parents=True, exist_ok=True)
            if not dst_anlz.exists():
                safe_copy(src, dst_anlz)
                copied_anlz += 1

        # DB: content — full Rekordbox 6 schema
        artist_id = get_or_insert_artist(artist_name)
        file_name_s = Path(filename).stem if filename else ''
        search_str  = f"{title or ''} {artist_name or ''}".strip()
        # Use first ANLZ path if available for AnalysisDataPath
        _anlz_entries = anlz_map.get(cid, [])
        anlz_data_path = _anlz_entries[0][0] if _anlz_entries else ''
        usb_con.execute("""INSERT OR REPLACE INTO djmdContent (
            ID, FolderPath, FileNameL, FileNameS, Title, ArtistID, AlbumID, GenreID,
            BPM, Length, TrackNo, BitRate, BitDepth, Commnt, FileType, Rating,
            ReleaseYear, RemixerID, LabelID, OrgArtistID, KeyID, StockDate, ColorID,
            DJPlayCount, ImagePath, MasterDBID, MasterSongID, AnalysisDataPath,
            SearchStr, FileSize, DiscNo, ComposerID, Subtitle, SampleRate,
            DisableQuantize, Analysed, ReleaseDate, DateCreated, ContentLink, Tag,
            ModifiedByRBM, HotCueAutoLoad, DeliveryControl, DeliveryComment,
            CueUpdated, AnalysisUpdated, TrackInfoUpdated, Lyricist, ISRC,
            SamplerTrackInfo, SamplerPlayOffset, SamplerGain, VideoAssociate,
            LyricStatus, ServiceID, OrgFolderPath,
            Reserved1, Reserved2, Reserved3, Reserved4, ExtInfo,
            rb_file_id, DeviceID, rb_LocalFolderPath,
            SrcID, SrcTitle, SrcArtistName, SrcAlbumName, SrcLength,
            UUID, rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
            usn, rb_local_usn, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(db_id), usb_audio_rel, filename, file_name_s,
             title or filename, artist_id, '', '',
             bpm, length, 0, bitrate, 0, comment, ftype, rating or 0,
             0, '', '', '', key_id, '', color_id,
             0, '', usb_db_id, str(db_id), anlz_data_path or '',
             search_str, 0, 0, '', '', samplerate,
             0, 1, '', ts(), 0, '',
             '', '', '', '', '', '', '', '', '',
             0, 0, 0.0, '', 0, 0, '',
             '', '', '', '', '',
             '', '', '',
             '', '', '', '', 0,
             track_uuid or new_uuid(), 257, 0, 0, 0,
             usn, usn, ts(), ts()))

        # DB: cues (replace on sync to pick up changes)
        # master.db djmdCue column order (SELECT *):
        #   0:ID 1:ContentID 2:InMsec 3:InFrame 4:InMpegFrame 5:InMpegAbs
        #   6:OutMsec 7:OutFrame 8:OutMpegFrame 9:OutMpegAbs 10:Kind 11:Color
        #   12:ColorTableIndex 13:ActiveLoop 14:Comment 15:BeatLoopSize 16:CueMicrosec
        #   17:InPointSeekInfo 18:OutPointSeekInfo 19:ContentUUID 20:UUID
        #   21:rb_data_status 22:rb_local_data_status 23:rb_local_deleted
        #   24:rb_local_synced 25:usn 26:rb_local_usn 27:created_at 28:updated_at
        usb_con.execute(f"DELETE FROM djmdCue WHERE ContentID=?", (str(db_id),))
        for cue in cues.get(cid, []):
            usb_con.execute("""INSERT OR IGNORE INTO djmdCue (
                ID, ContentID, InMsec, InFrame, InMpegFrame, InMpegAbs,
                OutMsec, OutFrame, OutMpegFrame, OutMpegAbs, Kind, Color,
                ColorTableIndex, ActiveLoop, Comment, BeatLoopSize, CueMicrosec,
                InPointSeekInfo, OutPointSeekInfo, ContentUUID, UUID,
                rb_data_status, rb_local_data_status,
                rb_local_deleted, rb_local_synced, usn, rb_local_usn, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,?,?,?,?)""",
                (cue[0], str(db_id), cue[2], cue[3], cue[4], cue[5],
                 cue[6], cue[7], cue[8], cue[9], cue[10], cue[11],
                 cue[12], cue[13], cue[14], cue[15], cue[16],
                 cue[17], cue[18], cue[19], cue[20],
                 usn, usn, ts(), ts()))

    print()  # newline after progress
    usb_con.commit()
    print(f"  ✅ Audio:  {copied_audio} local, {skipped_audio} already present, {len(missing_audio)} missing")
    if fetch_nas:
        print(f"  🌐 NAS:   {fetched_from_nas} fetched, {nas_fetch_failed} failed")
    print(f"  ✅ ANLZ:   {copied_anlz} new files")

    # ── Rebuild playlist structure ────────────────────────────────────────────
    if mode == 'push':
        # Push mode: merge into existing playlist tree (don't wipe)
        existing_playlist_ids = set(
            str(r[0]) for r in usb_con.execute("SELECT ID FROM djmdPlaylist").fetchall()
        )
        existing_song_keys = set(
            (str(r[0]), str(r[1])) for r in usb_con.execute(
                "SELECT PlaylistID, ContentID FROM djmdSongPlaylist"
            ).fetchall()
        )
    else:
        # Update / mirror: wipe and rebuild from scratch
        usb_con.execute("DELETE FROM djmdPlaylist")
        usb_con.execute("DELETE FROM djmdSongPlaylist")
        existing_playlist_ids = set()
        existing_song_keys = set()

    # Build ancestor paths for all selected playlists
    master = open_db(MASTER_DB)

    needed_paths = set()
    for path, (pl_id, attr) in tree.items():
        if attr == 0 and pl_id in playlist_ids:
            for i in range(1, len(path) + 1):
                needed_paths.add(path[:i])

    # Determine which content IDs are valid on USB for playlist links
    usb_valid_ids = set(
        str(r[0]) for r in usb_con.execute("SELECT ID FROM djmdContent").fetchall()
    )

    manifest_nodes = []
    pl_count = fold_count = link_count = 0
    sibling_seq = {}

    for path in sorted(needed_paths, key=lambda p: (len(p), p)):
        item = tree.get(path)
        if not item:
            continue
        pl_id, attr = item
        parent_path  = path[:-1]
        parent_db_id = tree.get(parent_path, ('root',))[0] if parent_path else 'root'

        seq_key = str(parent_db_id)
        seq = sibling_seq.get(seq_key, 0)
        sibling_seq[seq_key] = seq + 1

        manifest_nodes.append((int(pl_id), int(parent_db_id) if parent_db_id != 'root' else 0, attr))

        if mode == 'push' and str(pl_id) in existing_playlist_ids:
            # Push mode: playlist already exists — don't recreate, just add new tracks
            if attr == 0:
                pl_count += 1
                links = master.execute(
                    "SELECT ID, ContentID, TrackNo FROM djmdSongPlaylist WHERE PlaylistID=?",
                    (str(pl_id),)
                ).fetchall()
                for link in links:
                    if str(link[1]) in usb_valid_ids and (str(pl_id), str(link[1])) not in existing_song_keys:
                        usb_con.execute("""INSERT OR IGNORE INTO djmdSongPlaylist
                            (ID,PlaylistID,ContentID,TrackNo,UUID,
                             rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                             rb_local_usn,created_at,updated_at) VALUES (?,?,?,?,?,0,0,0,0,?,?,?)""",
                            (str(link[0]), str(pl_id), str(link[1]), link[2],
                             new_uuid(), usn, ts(), ts()))
                        link_count += 1
            else:
                fold_count += 1
        else:
            usb_con.execute("""INSERT OR REPLACE INTO djmdPlaylist
                (ID,Seq,Name,Attribute,ParentID,UUID,
                 rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                 rb_local_usn,created_at,updated_at) VALUES (?,?,?,?,?,?,0,0,0,0,?,?,?)""",
                (str(pl_id), seq, path[-1], attr,
                 str(parent_db_id) if parent_db_id != 'root' else 'root',
                 new_uuid(), usn, ts(), ts()))

            if attr == 0:
                pl_count += 1
                links = master.execute(
                    "SELECT ID, ContentID, TrackNo FROM djmdSongPlaylist WHERE PlaylistID=?",
                    (str(pl_id),)
                ).fetchall()
                for link in links:
                    if str(link[1]) in usb_valid_ids:
                        usb_con.execute("""INSERT OR IGNORE INTO djmdSongPlaylist
                            (ID,PlaylistID,ContentID,TrackNo,UUID,
                             rb_data_status,rb_local_data_status,rb_local_deleted,rb_local_synced,
                             rb_local_usn,created_at,updated_at) VALUES (?,?,?,?,?,0,0,0,0,?,?,?)""",
                            (str(link[0]), str(pl_id), str(link[1]), link[2],
                             new_uuid(), usn, ts(), ts()))
                        link_count += 1
            else:
                fold_count += 1

    master.close()
    usb_con.commit()
    checkpoint("Tracks & playlists committed to DB")
    print(f"  ✅ Playlists: {pl_count} playlists, {fold_count} folders, {link_count} links")

    # ── Mirror mode: orphan cleanup ───────────────────────────────────────────
    if mode == 'mirror':
        orphan_rows = usb_con.execute(
            "SELECT c.ID, c.FolderPath FROM djmdContent c WHERE NOT EXISTS "
            "(SELECT 1 FROM djmdSongPlaylist sp WHERE sp.ContentID = c.ID)"
        ).fetchall()
        if orphan_rows:
            orphan_ids = [r[0] for r in orphan_rows]
            orphan_paths = [r[1] for r in orphan_rows]
            ph_orph = ','.join('?' * len(orphan_ids))
            usb_con.execute(f"DELETE FROM djmdCue WHERE ContentID IN ({ph_orph})", orphan_ids)
            usb_con.execute(f"DELETE FROM djmdContent WHERE ID IN ({ph_orph})", orphan_ids)
            # Delete orphan audio files from USB
            for fpath in orphan_paths:
                if fpath:
                    audio_file = usb_path / fpath.lstrip('/')
                    if audio_file.exists():
                        audio_file.unlink()
            usb_con.commit()
            print(f"  🧹 Cleaned up {len(orphan_ids)} orphaned tracks")

        # Scan /Contents/ for audio files not in DB
        db_paths = set(
            r[0] for r in usb_con.execute("SELECT FolderPath FROM djmdContent").fetchall()
            if r[0]
        )
        audio_dir = usb_path / AUDIO_DIR
        if audio_dir.exists():
            stale_files = 0
            for audio_file in audio_dir.rglob('*'):
                if audio_file.is_file():
                    rel_path = '/' + str(audio_file.relative_to(usb_path))
                    if rel_path not in db_paths:
                        audio_file.unlink()
                        stale_files += 1
            # Clean up empty artist directories
            for d in audio_dir.iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            if stale_files:
                print(f"  🧹 Removed {stale_files} stale audio files from {AUDIO_DIR}/")

    # ── Push mode: rebuild manifest from USB DB to include all playlists ──────
    if mode == 'push':
        manifest_nodes = []
        for r in usb_con.execute(
            "SELECT ID, ParentID, Attribute FROM djmdPlaylist ORDER BY Seq"
        ).fetchall():
            parent_dec = 0 if str(r[1]) == 'root' else int(r[1])
            manifest_nodes.append((int(r[0]), parent_dec, r[2]))

    # ── masterPlaylists6.xml ───────────────────────────────────────────────────
    xml_manifest = usb_rb_dir / "masterPlaylists6.xml"
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
            f'Attribute="{attribute}" Timestamp="{ts_ms}" Lib_Type="0" CheckType="0"/>'
        )
    lines += ['  </PLAYLISTS>', '</MASTER_PLAYLIST>', '']
    xml_manifest.write_text('\n'.join(lines), encoding='utf-8')
    checkpoint("Playlist manifest written")

    # ── Save sync state ────────────────────────────────────────────────────────
    save_sync_usn(usb_con, max_master_usn)
    usb_con.close()
    checkpoint("Sync state saved, USB export complete")

    if missing_audio:
        print(f"\n  ⚠️  {len(missing_audio)} audio files not found locally:")
        for p in missing_audio[:5]:
            print(f"     {p}")
        if len(missing_audio) > 5:
            print(f"     … and {len(missing_audio)-5} more")

    print(f"\n  ✅ Done → {usb_path}")
    print(f"     exportLibrary.db : {usb_db_path}")
    print(f"     masterPlaylists6.xml : {xml_manifest}")


# ── Device Library Plus conversion ─────────────────────────────────────────────

DEVICE_LIB_PLUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS album(album_id integer primary key, name varchar, artist_id integer, image_id integer, isComplation integer, nameForSearch varchar);
CREATE TABLE IF NOT EXISTS artist(artist_id integer primary key, name varchar, nameForSearch varchar);
CREATE TABLE IF NOT EXISTS category(category_id integer primary key, menuItem_id integer, sequenceNo integer, isVisible integer);
CREATE TABLE IF NOT EXISTS color(color_id integer primary key, name varchar);
CREATE TABLE IF NOT EXISTS content(content_id integer primary key, title varchar, titleForSearch varchar, subtitle varchar, bpmx100 integer, length integer, trackNo integer, discNo integer, artist_id_artist integer, artist_id_remixer integer, artist_id_originalArtist integer, artist_id_composer integer, artist_id_lyricist integer, album_id integer, genre_id integer, label_id integer, key_id integer, color_id integer, image_id integer, djComment varchar, rating integer, releaseYear integer, releaseDate varchar, dateCreated varchar, dateAdded varchar, path varchar, fileName varchar, fileSize integer, fileType integer, bitrate integer, bitDepth integer, samplingRate integer, isrc varchar, djPlayCount integer, isHotCueAutoLoadOn integer, isKuvoDeliverStatusOn integer, kuvoDeliveryComment varchar, masterDbId integer, masterContentId integer, analysisDataFilePath varchar, analysedBits integer, contentLink integer, hasModified integer, cueUpdateCount integer, analysisDataUpdateCount integer, informationUpdateCount integer);
CREATE TABLE IF NOT EXISTS cue(cue_id integer primary key, content_id integer, kind integer, colorTableIndex integer, cueComment varchar, isActiveLoop integer, beatLoopNumerator integer, beatLoopDenominator integer, inUsec integer, outUsec integer, in150FramePerSec integer, out150FramePerSec integer, inMpegFrameNumber integer, outMpegFrameNumber integer, inMpegAbs integer, outMpegAbs integer, inDecodingStartFramePosition integer, outDecodingStartFramePosition integer, inFileOffsetInBlock integer, OutFileOffsetInBlock integer, inNumberOfSampleInBlock integer, outNumberOfSampleInBlock integer);
CREATE TABLE IF NOT EXISTS genre(genre_id integer primary key, name varchar);
CREATE TABLE IF NOT EXISTS history(history_id integer primary key, sequenceNo integer, name varchar, attribute integer, history_id_parent integer);
CREATE TABLE IF NOT EXISTS history_content(history_id integer, content_id integer, sequenceNo integer);
CREATE TABLE IF NOT EXISTS hotCueBankList(hotCueBankList_id integer primary key, sequenceNo integer, name varchar, image_id integer, attribute integer, hotCueBankList_id_parent integer);
CREATE TABLE IF NOT EXISTS hotCueBankList_cue(hotCueBankList_id integer, cue_id integer, sequenceNo integer);
CREATE TABLE IF NOT EXISTS image(image_id integer primary key, path varchar);
CREATE TABLE IF NOT EXISTS key(key_id integer primary key, name varchar);
CREATE TABLE IF NOT EXISTS label(label_id integer primary key, name varchar);
CREATE TABLE IF NOT EXISTS menuItem(menuItem_id integer primary key, kind integer, name varchar);
CREATE TABLE IF NOT EXISTS myTag(myTag_id integer primary key, sequenceNo integer, name varchar, attribute integer, myTag_id_parent integer);
CREATE TABLE IF NOT EXISTS myTag_content(myTag_id integer, content_id integer);
CREATE TABLE IF NOT EXISTS playlist(playlist_id integer primary key, sequenceNo integer, name varchar, image_id integer, attribute integer, playlist_id_parent integer);
CREATE TABLE IF NOT EXISTS playlist_content(playlist_id integer, content_id integer, sequenceNo integer);
CREATE TABLE IF NOT EXISTS property(deviceName varchar, dbVersion varchar, numberOfContents integer, createdDate varchar, backGroundColorType integer, myTagMasterDBID integer);
CREATE TABLE IF NOT EXISTS recommendedLike(content_id_1 integer, content_id_2 integer, rating integer, createdDate integer);
CREATE TABLE IF NOT EXISTS sort(sort_id integer primary key, menuItem_id integer, sequenceNo integer, isVisible integer, isSelectedAsSubColumn integer);
CREATE INDEX IF NOT EXISTS index_hotCueBankList_cue_hotCueBankList_id on hotCueBankList_cue(hotCueBankList_id);
CREATE INDEX IF NOT EXISTS index_myTag_content_content_id on myTag_content(content_id);
CREATE INDEX IF NOT EXISTS index_myTag_content_myTag_id on myTag_content(myTag_id);
CREATE INDEX IF NOT EXISTS index_playlist_content_playlist_id on playlist_content(playlist_id);
"""

def convert_to_device_library_plus(djmd_db_path: Path, output_path: Path, dry_run: bool = False):
    """Convert a djmd-format exportLibrary.db to Device Library Plus format.

    Reads the current exportLibrary.db (master.db schema, master key),
    writes a new one with Device Library Plus schema and export key.
    """
    if not djmd_db_path.exists():
        print("  ⚠️  No exportLibrary.db to convert")
        return False

    # Open source DB (djmd format, master key, legacy=4)
    src = open_db(djmd_db_path)

    # Collect data from djmd tables
    content_rows = src.execute("""
        SELECT ID, Title, SearchStr, Subtitle, BPM, Length, TrackNo, DiscNo,
               ArtistID, RemixerID, OrgArtistID, ComposerID, Lyricist,
               AlbumID, GenreID, LabelID, KeyID, ColorID, ImagePath,
               Commnt, Rating, ReleaseYear, ReleaseDate, DateCreated, StockDate,
               FolderPath, FileNameL, FileSize, FileType, BitRate, BitDepth,
               SampleRate, ISRC, DJPlayCount, HotCueAutoLoad, DeliveryControl,
               DeliveryComment, MasterDBID, MasterSongID, AnalysisDataPath,
               Analysed, ContentLink, ModifiedByRBM, CueUpdated, AnalysisUpdated,
               TrackInfoUpdated
        FROM djmdContent WHERE rb_local_deleted=0
    """).fetchall()

    artist_rows = src.execute(
        "SELECT ID, Name, SearchStr FROM djmdArtist WHERE rb_local_deleted=0"
    ).fetchall()

    album_rows = src.execute(
        "SELECT ID, Name, ArtistID, ImagePath, Compilation, SearchStr FROM djmdAlbum WHERE rb_local_deleted=0"
    ).fetchall()

    genre_rows = src.execute("SELECT ID, Name FROM djmdGenre WHERE rb_local_deleted=0").fetchall()
    label_rows = src.execute("SELECT ID, Name FROM djmdLabel WHERE rb_local_deleted=0").fetchall()
    key_rows = src.execute("SELECT ID, ScaleName FROM djmdKey WHERE rb_local_deleted=0").fetchall()
    color_rows = src.execute("SELECT ID, Commnt FROM djmdColor WHERE rb_local_deleted=0").fetchall()

    playlist_rows = src.execute(
        "SELECT ID, Seq, Name, ImagePath, Attribute, ParentID FROM djmdPlaylist WHERE rb_local_deleted=0"
    ).fetchall()

    song_playlist_rows = src.execute(
        "SELECT PlaylistID, ContentID, TrackNo FROM djmdSongPlaylist WHERE rb_local_deleted=0"
    ).fetchall()

    src.close()

    n_tracks = len(content_rows)
    n_playlists = len(playlist_rows)
    n_entries = len(song_playlist_rows)

    if dry_run:
        print(f"  Would create Device Library Plus DB: {n_tracks} tracks, {n_playlists} playlists, {n_entries} entries")
        return True

    # Build ID maps (djmd uses string IDs, Device Library Plus uses integer IDs)
    # Map string IDs to sequential integers starting from 1
    def build_id_map(rows, id_col=0):
        """Map string IDs to sequential integers."""
        id_map = {}
        for i, row in enumerate(rows, 1):
            id_map[str(row[id_col])] = i
        return id_map

    content_id_map = build_id_map(content_rows)
    artist_id_map = build_id_map(artist_rows)
    album_id_map = build_id_map(album_rows)
    genre_id_map = build_id_map(genre_rows)
    label_id_map = build_id_map(label_rows)
    key_id_map = build_id_map(key_rows)
    color_id_map = build_id_map(color_rows)
    playlist_id_map = {}

    def map_id(val, id_map):
        """Map a string ID to its integer equivalent, or None."""
        if val is None or str(val) == '' or str(val) == 'None':
            return None
        return id_map.get(str(val))

    # Remove old file + WAL/SHM
    for ext in ['', '-wal', '-shm']:
        p = Path(str(output_path) + ext)
        if p.exists():
            p.unlink()

    # Create new DB with export key (SQLCipher 4 defaults)
    out = open_export_db(output_path)
    out.executescript(DEVICE_LIB_PLUS_SCHEMA)

    # Insert artists
    for row in artist_rows:
        new_id = artist_id_map[str(row[0])]
        out.execute("INSERT INTO artist VALUES (?,?,?)",
                    (new_id, row[1], row[2]))

    # Insert albums
    for row in album_rows:
        new_id = album_id_map[str(row[0])]
        out.execute("INSERT INTO album VALUES (?,?,?,?,?,?)",
                    (new_id, row[1], map_id(row[2], artist_id_map), None,
                     safe_int(row[4]) if row[4] else 0, row[5]))

    # Insert genres
    for row in genre_rows:
        new_id = genre_id_map[str(row[0])]
        out.execute("INSERT INTO genre VALUES (?,?)", (new_id, row[1]))

    # Insert labels
    for row in label_rows:
        new_id = label_id_map[str(row[0])]
        out.execute("INSERT INTO label VALUES (?,?)", (new_id, row[1]))

    # Insert keys
    for row in key_rows:
        new_id = key_id_map[str(row[0])]
        out.execute("INSERT INTO key VALUES (?,?)", (new_id, row[1]))

    # Insert colors
    for row in color_rows:
        new_id = color_id_map[str(row[0])]
        out.execute("INSERT INTO color VALUES (?,?)", (new_id, row[1]))

    # Insert images (from content image paths)
    image_map = {}
    image_id_seq = 1
    for row in content_rows:
        img_path = row[18]  # ImagePath
        if img_path and img_path not in image_map:
            image_map[img_path] = image_id_seq
            out.execute("INSERT INTO image VALUES (?,?)", (image_id_seq, img_path))
            image_id_seq += 1

    # Insert content
    for row in content_rows:
        cid = content_id_map[str(row[0])]
        out.execute("""INSERT INTO content VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )""", (
            cid,
            row[1],   # title
            row[2],   # titleForSearch
            row[3],   # subtitle
            safe_int(row[4]),  # bpmx100
            safe_int(row[5]),  # length
            safe_int(row[6]),  # trackNo
            safe_int(row[7]),  # discNo
            map_id(row[8], artist_id_map),   # artist_id_artist
            map_id(row[9], artist_id_map),   # artist_id_remixer
            map_id(row[10], artist_id_map),  # artist_id_originalArtist
            map_id(row[11], artist_id_map),  # artist_id_composer
            map_id(row[12], artist_id_map),  # artist_id_lyricist
            map_id(row[13], album_id_map),   # album_id
            map_id(row[14], genre_id_map),   # genre_id
            map_id(row[15], label_id_map),   # label_id
            map_id(row[16], key_id_map),     # key_id
            map_id(row[17], color_id_map),   # color_id
            image_map.get(row[18]),           # image_id
            row[19],  # djComment
            safe_int(row[20]),  # rating
            safe_int(row[21]),  # releaseYear
            row[22],  # releaseDate
            row[23],  # dateCreated
            row[24],  # dateAdded
            row[25],  # path (FolderPath)
            row[26],  # fileName
            safe_int(row[27]),  # fileSize
            safe_int(row[28]),  # fileType
            safe_int(row[29]),  # bitrate
            safe_int(row[30]),  # bitDepth
            safe_int(row[31]),  # samplingRate
            row[32],  # isrc
            safe_int(row[33]),  # djPlayCount
            1 if row[34] else 0,  # isHotCueAutoLoadOn
            1 if row[35] else 0,  # isKuvoDeliverStatusOn
            row[36],  # kuvoDeliveryComment
            row[37],  # masterDbId
            row[38],  # masterContentId
            row[39],  # analysisDataFilePath
            safe_int(row[40]),  # analysedBits
            safe_int(row[41]),  # contentLink
            1 if row[42] else 0,  # hasModified
            safe_int(row[43]),  # cueUpdateCount
            safe_int(row[44]),  # analysisDataUpdateCount
            safe_int(row[45]),  # informationUpdateCount
        ))

    # Insert playlists
    for row in playlist_rows:
        old_id = str(row[0])
        parent_old = str(row[5]) if row[5] else "0"
        # Generate sequential ID
        if old_id not in playlist_id_map:
            playlist_id_map[old_id] = len(playlist_id_map) + 1
        new_id = playlist_id_map[old_id]
        # Map parent (root='root' or '0' → 0)
        if parent_old in ('root', '0', '', 'None'):
            parent_new = 0
        else:
            if parent_old not in playlist_id_map:
                playlist_id_map[parent_old] = len(playlist_id_map) + 1
            parent_new = playlist_id_map[parent_old]

        out.execute("INSERT INTO playlist VALUES (?,?,?,?,?,?)",
                    (new_id, safe_int(row[1]), row[2], None,
                     safe_int(row[4]), parent_new))

    # Insert playlist_content
    for row in song_playlist_rows:
        pl_id = playlist_id_map.get(str(row[0]))
        ct_id = content_id_map.get(str(row[1]))
        if pl_id and ct_id:
            out.execute("INSERT INTO playlist_content VALUES (?,?,?)",
                        (pl_id, ct_id, safe_int(row[2])))

    # Insert property
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    out.execute("INSERT INTO property VALUES (?,?,?,?,?,?)",
                ('', '1000', n_tracks, today, 0, 0))

    # Insert default sort/category/menuItem entries
    menu_items = [
        (1, 0, 'All'), (2, 1, 'Artist'), (3, 2, 'Album'), (4, 3, 'Track'),
        (5, 4, 'BPM'), (6, 5, 'Genre'), (7, 6, 'Label'), (8, 7, 'Key'),
        (9, 8, 'Bitrate'), (10, 9, 'DJ Play Count'), (11, 10, 'Rating'),
        (12, 11, 'Color'), (13, 12, 'Original Artist'), (14, 13, 'Remixer'),
        (15, 14, 'Date Added'), (16, 15, 'Lyricist'), (17, 16, 'Composer'),
        (18, 17, 'Comment'), (19, 18, 'History'), (20, 19, 'My Tag'),
        (21, 20, 'File Name'), (22, 21, 'Release Date'), (23, 22, 'Year'),
        (24, 23, 'Playlist'), (25, 24, 'Search'), (26, 25, 'Folder'),
        (27, 26, 'Hot Cue Bank'),
    ]
    for mid, kind, name in menu_items:
        out.execute("INSERT OR IGNORE INTO menuItem VALUES (?,?,?)", (mid, kind, name))

    # Default categories
    for cid in range(1, 23):
        out.execute("INSERT OR IGNORE INTO category VALUES (?,?,?,?)", (cid, cid, cid - 1, 1))

    # Default sort entries
    for sid in range(1, 18):
        out.execute("INSERT OR IGNORE INTO sort VALUES (?,?,?,?,?)", (sid, sid, sid - 1, 1, 0))

    out.commit()
    # Switch to WAL mode (Rekordbox expects WAL journal mode)
    out.execute("PRAGMA journal_mode=wal")
    out.close()

    out_size = os.path.getsize(output_path)
    print(f"  ✅ Device Library Plus: {n_tracks} tracks, {n_playlists} playlists, {n_entries} entries ({out_size:,} bytes)")
    return True


def safe_int(val, default=0):
    if val is None or val == '' or val == 'None':
        return default
    try:
        return int(val) & 0xFFFFFFFF
    except (ValueError, TypeError):
        return default

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument('--select',    action='store_true', help='Interactive UI to select playlists')
    scope.add_argument('--all',       action='store_true', help='Export entire library')
    scope.add_argument('--playlists', nargs='+', metavar='NAME',
                      help='Folder/playlist names to export')

    ap.add_argument('--usb',      metavar='PATH', help='USB mount point (auto-detected if omitted)')
    ap.add_argument('--mode',     choices=['update', 'push', 'mirror'], default=None,
                    help='Sync mode: update (skip existing, clean deleted), push (additive only), mirror (exact match)')
    ap.add_argument('--sync',     action='store_true',
                    help='[Deprecated] Alias for --mode update')
    ap.add_argument('--dry-run',  action='store_true', help='Preview without writing')
    ap.add_argument('--fetch-nas', action='store_true',
                    help='Fetch missing tracks from NAS via traktor-ml (requires server + SSH tunnel)')
    ap.add_argument('--wipe',     action='store_true',
                    help='Wipe all Rekordbox data from USB (DB, playlists, audio, ANLZ)')
    args = ap.parse_args()

    # Resolve sync mode
    if args.mode:
        sync_mode = args.mode
    elif args.sync:
        print("  ⚠️  --sync is deprecated, use --mode update")
        sync_mode = 'update'
    else:
        sync_mode = 'update'  # default

    try:
        # ── Resolve USB path ──────────────────────────────────────────────────────
        if args.usb:
            usb_path = Path(args.usb)
            if not usb_path.exists() and not args.dry_run:
                ap.error(f"USB path not found: {usb_path}")
            elif not usb_path.exists() and args.dry_run:
                # For dry-run, use the path even if it doesn't exist
                pass
        else:
            candidates = detect_pioneer_usbs()
            if not candidates:
                if not args.dry_run:
                    ap.error("No Pioneer USB drive detected. Plug in your USB or use --usb PATH.")
                else:
                    # For dry-run preview, use a placeholder path
                    usb_path = Path("/Volumes/PIONEER")
                    print(f"📋 DRY-RUN MODE: No USB detected. Previewing with placeholder: {usb_path}")
            elif len(candidates) == 1:
                usb_path = candidates[0]
                print(f"Auto-detected USB: {usb_path}")
            else:
                # Multiple USBs — ask which one
                try:
                    import questionary
                    usb_path = Path(questionary.select(
                        "Multiple Pioneer USBs detected. Which one?",
                        choices=[str(p) for p in candidates]
                    ).ask())
                except ImportError:
                    print("Multiple USBs found:")
                    for i, p in enumerate(candidates):
                        print(f"  [{i}] {p}")
                    idx = int(input("Select index: "))
                    usb_path = candidates[idx]

        if not args.dry_run:
            # Ensure USB is writable
            test_file = usb_path / ".copilot_write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except OSError as e:
                ap.error(f"USB is read-only or not writable: {e}")

        # ── Wipe mode (early exit) ───────────────────────────────────────────────
        if args.wipe:
            wipe_usb(usb_path, args.dry_run)
            sys.exit(0)

        # ── Load playlist tree from master.db ────────────────────────────────────
        master = open_db(MASTER_DB)
        tree = get_playlist_tree(master)
        master.close()

        # ── Determine selected playlist IDs ──────────────────────────────────────
        if args.select:
            selected_ids = run_selector(tree)
            if not selected_ids:
                print("Nothing selected. Exiting.")
                sys.exit(0)
            playlist_ids = set(selected_ids)
        elif args.all:
            playlist_ids = {pl_id for _, (pl_id, attr) in tree.items() if attr == 0}
        elif args.playlists:
            playlist_ids = collect_playlist_ids(tree, args.playlists)
            if not playlist_ids:
                top = sorted({p[0] for p in tree})
                ap.error(
                    f"No playlists found matching: {args.playlists}\n"
                    "Available top-level folders:\n" +
                    '\n'.join(f"  • {n}" for n in top)
                )
        else:
            # No mode given: default to --select if interactive, else print help
            if sys.stdin.isatty():
                selected_ids = run_selector(tree)
                playlist_ids = set(selected_ids) if selected_ids else set()
                if not playlist_ids:
                    print("Nothing selected. Exiting.")
                    sys.exit(0)
            else:
                ap.print_help()
                sys.exit(1)

        export_to_usb(usb_path, playlist_ids, tree, sync_mode, args.dry_run, args.fetch_nas)

        # Generate export.pdb so Rekordbox desktop / CDJs can read the USB
        try:
            from write_pdb import read_export_db, build_pdb, backup_pdb
            pdb_path = usb_path / "PIONEER" / "rekordbox" / "export.pdb"
            db_path = usb_path / "PIONEER" / "rekordbox" / "exportLibrary.db"
            if db_path.exists():
                print("\n🔨 Generating export.pdb ...")
                pdb_data = read_export_db(db_path)
                pdb_bytes = build_pdb(pdb_data)
                if args.dry_run:
                    print(f"  Would write {len(pdb_bytes):,} bytes to {pdb_path}")
                else:
                    if pdb_path.exists():
                        backup_pdb(pdb_path)
                    pdb_path.write_bytes(pdb_bytes)
                    print(f"  ✅ Written {len(pdb_bytes):,} bytes ({len(pdb_bytes)//4096} pages)")
        except Exception as e:
            print(f"\n⚠️  export.pdb generation failed (USB still usable via exportLibrary.db): {e}")

        # Convert exportLibrary.db from djmd format to Device Library Plus format
        # (Rekordbox desktop reads the DLP format, not the djmd format)
        db_path = usb_path / "PIONEER" / "rekordbox" / "exportLibrary.db"
        if db_path.exists():
            print("\n🔄 Converting to Device Library Plus format ...")
            dlp_path = db_path.parent / "exportLibrary_dlp.db"
            try:
                if convert_to_device_library_plus(db_path, dlp_path, args.dry_run):
                    if not args.dry_run:
                        # Replace old DB with new DLP DB
                        for ext in ['', '-wal', '-shm']:
                            old = Path(str(db_path) + ext)
                            if old.exists():
                                old.unlink()
                        dlp_path.rename(db_path)
                        print("  ✅ exportLibrary.db now in Device Library Plus format")
            except Exception as e:
                print(f"  ⚠️  DLP conversion failed: {e}")
                import traceback
                traceback.print_exc()
                # Clean up partial output
                if dlp_path.exists():
                    dlp_path.unlink()

        print("\n✅ Export completed successfully")

    except Exception as e:
        print(f"\n❌ Export failed: {e}")
        checkpoint(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
