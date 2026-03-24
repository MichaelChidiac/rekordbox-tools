#!/usr/bin/env python3.11
"""Export DLP (exportLibrary.db) data as JSON for the Rust PDB writer."""

import json
import sys
import sqlcipher3

DLP_KEY = "r8gddnr4k847830ar6cqzbkk0el6qytmb3trbbx805jm74vez64i5o8fnrqryqls"

# Standard columns/menu/sort from reference PDB
STANDARD_COLUMNS = [
    (1, 128, "GENRE"), (2, 129, "ARTIST"), (3, 130, "ALBUM"), (4, 131, "TRACK"),
    (5, 133, "BPM"), (6, 134, "RATING"), (7, 135, "YEAR"), (8, 136, "REMIXER"),
    (9, 137, "LABEL"), (10, 138, "ORIGINAL ARTIST"), (11, 139, "KEY"), (12, 141, "CUE"),
    (13, 142, "COLOR"), (14, 146, "TIME"), (15, 147, "BITRATE"), (16, 148, "FILE NAME"),
    (17, 132, "PLAYLIST"), (18, 152, "HOT CUE BANK"), (19, 149, "HISTORY"),
    (20, 145, "SEARCH"), (21, 150, "COMMENTS"), (22, 140, "DATE ADDED"),
    (23, 151, "DJ PLAY COUNT"), (24, 144, "FOLDER"), (25, 161, "DEFAULT"),
    (26, 162, "ALPHABET"), (27, 170, "MATCHING"),
]

# Menu from reference PDB (exact data)
STANDARD_MENU = [
    (1, 1, 99, 1, 0),    # Hidden
    (5, 6, 5, 1, 0),     # Hidden
    (6, 7, 99, 1, 0),    # Hidden
    (7, 8, 99, 1, 0),    # Hidden
    (8, 9, 99, 1, 0),    # Hidden
    (9, 10, 99, 1, 0),   # Hidden
    (10, 11, 99, 1, 0),  # Hidden
    (14, 19, 4, 1, 0),   # Hidden
    (15, 20, 6, 1, 0),   # Hidden
    (16, 21, 99, 1, 0),  # Hidden
    (18, 23, 99, 1, 0),  # Hidden
    (2, 2, 2, 0, 1),     # Visible
    (3, 3, 3, 0, 2),     # Visible
    (4, 4, 1, 0, 3),     # Visible
    (11, 12, 99, 0, 4),  # Visible
    (13, 15, 99, 0, 5),  # Visible
    (17, 5, 99, 0, 6),   # Visible
    (19, 22, 99, 0, 7),  # Visible
    (20, 18, 99, 0, 8),  # Visible
    (27, 26, 99, 2, 9),  # Unknown(2) visibility
    (24, 17, 99, 0, 10), # Visible
    (22, 27, 99, 0, 11), # Visible
]


def wrap_string(s):
    """Wrap string with DeviceSQL markers \ufffa...\ufffb."""
    if s is None:
        return "\ufffa\ufffb"
    return f"\ufffa{s}\ufffb"


def export_dlp(dlp_path):
    con = sqlcipher3.connect(dlp_path)
    con.execute(f"PRAGMA key='{DLP_KEY}'")

    cur = con.cursor()

    # Tracks
    tracks = []
    cur.execute("""
        SELECT content_id, title, subtitle, bpmx100, length, trackNo, discNo,
               artist_id_artist, artist_id_remixer, artist_id_originalArtist,
               artist_id_composer, artist_id_lyricist,
               album_id, genre_id, label_id, key_id, color_id, image_id,
               djComment, rating, releaseYear, releaseDate, dateCreated, dateAdded,
               path, fileName, fileSize, fileType, bitrate, bitDepth, samplingRate,
               isrc, djPlayCount, isHotCueAutoLoadOn,
               masterContentId, analysisDataFilePath, contentLink
        FROM content ORDER BY content_id
    """)
    for row in cur.fetchall():
        (cid, title, subtitle, bpm, length, track_no, disc_no,
         artist_id, remixer_id, orig_artist_id, composer_id, lyricist_id,
         album_id, genre_id, label_id, key_id, color_id, image_id,
         dj_comment, rating, release_year, release_date, date_created, date_added,
         path, filename, file_size, file_type, bitrate, bit_depth, sampling_rate,
         isrc, play_count, hotcue_autoload,
         master_content_id, analyze_path, content_link) = row

        tracks.append({
            "id": cid,
            "sample_rate": sampling_rate or 44100,
            "composer_id": composer_id or 0,
            "file_size": file_size or 0,
            "unknown2": master_content_id or 0,
            "artwork_id": image_id or 0,
            "key_id": key_id or 0,
            "orig_artist_id": orig_artist_id or 0,
            "label_id": label_id or 0,
            "remixer_id": remixer_id or 0,
            "bitrate": bitrate or 0,
            "track_number": track_no or 0,
            "tempo": bpm or 0,
            "genre_id": genre_id or 0,
            "album_id": album_id or 0,
            "artist_id": artist_id or 0,
            "disc_number": disc_no or 0,
            "play_count": play_count or 0,
            "year": release_year or 0,
            "sample_depth": bit_depth or 0,
            "duration": length or 0,
            "color": color_id or 0,
            "rating": rating or 0,
            "file_type": file_type or 0,
            "isrc": wrap_string(isrc or ""),
            "unknown_string2": wrap_string(""),
            "unknown_string3": wrap_string(""),
            "unknown_string4": wrap_string(""),
            "message": wrap_string(dj_comment or ""),
            "autoload_hotcues": wrap_string(str(hotcue_autoload) if hotcue_autoload else ""),
            "date_added": wrap_string(date_added or ""),
            "release_date": wrap_string(release_date or ""),
            "mix_name": wrap_string(subtitle or ""),
            "analyze_path": wrap_string(analyze_path or ""),
            "analyze_date": wrap_string(date_created or ""),
            "comment": wrap_string(dj_comment or ""),
            "title": wrap_string(title or ""),
            "filename": wrap_string(filename or ""),
            "file_path": wrap_string(path or ""),
        })

    # Artists
    artists = []
    cur.execute("SELECT artist_id, name FROM artist ORDER BY artist_id")
    for r in cur.fetchall():
        artists.append({"id": r[0], "name": wrap_string(r[1] or "")})

    # Genres
    genres = []
    cur.execute("SELECT genre_id, name FROM genre ORDER BY genre_id")
    for r in cur.fetchall():
        genres.append({"id": r[0], "name": wrap_string(r[1] or "")})

    # Albums
    albums = []
    cur.execute("SELECT album_id, name, artist_id FROM album ORDER BY album_id")
    for r in cur.fetchall():
        albums.append({"id": r[0], "name": wrap_string(r[1] or ""), "artist_id": r[2] or 0})

    # Labels
    labels = []
    cur.execute("SELECT label_id, name FROM label ORDER BY label_id")
    for r in cur.fetchall():
        labels.append({"id": r[0], "name": wrap_string(r[1] or "")})

    # Keys
    keys = []
    cur.execute("SELECT key_id, name FROM key ORDER BY key_id")
    for r in cur.fetchall():
        keys.append({"id": r[0], "id2": r[0], "name": wrap_string(r[1] or "")})

    # Colors
    colors = []
    cur.execute("SELECT color_id, name FROM color ORDER BY color_id")
    for r in cur.fetchall():
        colors.append({"id": r[0], "name": wrap_string(r[1] or "")})

    # Playlist tree
    playlist_tree = []
    cur.execute("SELECT playlist_id, sequenceNo, name, image_id, attribute, playlist_id_parent FROM playlist ORDER BY playlist_id")
    for r in cur.fetchall():
        pid, seq, name, img, attr, parent = r
        is_folder = 1 if attr == 1 else 0
        playlist_tree.append({
            "id": pid,
            "parent_id": parent or 0,
            "sort_order": seq or 0,
            "is_folder": is_folder,
            "name": wrap_string(name or ""),
        })

    # Playlist entries
    playlist_entries = []
    cur.execute("SELECT playlist_id, content_id, sequenceNo FROM playlist_content ORDER BY playlist_id, sequenceNo")
    for r in cur.fetchall():
        playlist_entries.append({
            "entry_index": r[2] or 0,
            "track_id": r[1],
            "playlist_id": r[0],
        })

    # Artwork / images
    artwork = []
    cur.execute("SELECT image_id, path FROM image ORDER BY image_id")
    for r in cur.fetchall():
        artwork.append({"id": r[0], "path": wrap_string(r[1] or "")})

    # Columns (standard)
    columns = [{"id": c[0], "unknown0": c[1], "name": wrap_string(c[2])} for c in STANDARD_COLUMNS]

    # Menu (standard from reference)
    menu = [{"category_id": m[0], "content_pointer": m[1], "unknown": m[2], "visibility": m[3], "sort_order": m[4]} for m in STANDARD_MENU]

    # History (empty for fresh export)
    history_playlists = []
    history_entries = []

    data = {
        "tracks": tracks,
        "artists": artists,
        "genres": genres,
        "albums": albums,
        "labels": labels,
        "keys": keys,
        "colors": colors,
        "playlist_tree": playlist_tree,
        "playlist_entries": playlist_entries,
        "artwork": artwork,
        "columns": columns,
        "menu": menu,
        "history_playlists": history_playlists,
        "history_entries": history_entries,
    }

    con.close()
    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: export_pdb_json.py <exportLibrary.db> [output.json]", file=sys.stderr)
        sys.exit(1)

    dlp_path = sys.argv[1]
    data = export_dlp(dlp_path)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'w') as f:
            json.dump(data, f)
        print(f"Written {len(data['tracks'])} tracks, {len(data['artists'])} artists, "
              f"{len(data['playlist_tree'])} playlists to {sys.argv[2]}", file=sys.stderr)
    else:
        json.dump(data, sys.stdout)
