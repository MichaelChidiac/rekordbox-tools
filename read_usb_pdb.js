#!/usr/bin/env node
/**
 * read_usb_pdb.js
 *
 * Reads a Pioneer USB drive's export.pdb and outputs JSON with playlists,
 * tracks, artists, and playlist entries. Used as a fallback when
 * exportLibrary.db is encrypted (Rekordbox-created USBs).
 *
 * Usage:
 *   node read_usb_pdb.js /Volumes/PATRIOT
 *   node read_usb_pdb.js /Volumes/PATRIOT --summary
 *   node read_usb_pdb.js /Volumes/PATRIOT --playlists
 *   node read_usb_pdb.js /Volumes/PATRIOT --tracks
 *
 * Default: outputs full JSON with all data.
 */

const { parsePdb, tableRows, RekordboxPdb } = require('rekordbox-parser');
const fs = require('fs');
const path = require('path');

const { PageType } = RekordboxPdb;

function findPdbPath(usbRoot) {
    // Try both PIONEER and .PIONEER paths
    const candidates = [
        path.join(usbRoot, 'PIONEER', 'rekordbox', 'export.pdb'),
        path.join(usbRoot, '.PIONEER', 'rekordbox', 'export.pdb'),
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return null;
}

function getText(field) {
    if (!field) return '';
    if (field.body && field.body.text !== undefined) return field.body.text;
    return '';
}

function readPdb(pdbPath) {
    const buf = fs.readFileSync(pdbPath);
    const pdb = parsePdb(buf);

    // Build artist lookup
    const artists = {};
    for (const row of tableRows(pdb.tables[PageType.ARTISTS])) {
        artists[row.id] = { id: row.id, name: getText(row.name) };
    }

    // Build genre lookup
    const genres = {};
    for (const row of tableRows(pdb.tables[PageType.GENRES])) {
        genres[row.id] = { id: row.id, name: getText(row.name) };
    }

    // Build key lookup
    const keys = {};
    for (const row of tableRows(pdb.tables[PageType.KEYS])) {
        keys[row.id] = { id: row.id, name: getText(row.name) };
    }

    // Build album lookup
    const albums = {};
    for (const row of tableRows(pdb.tables[PageType.ALBUMS])) {
        albums[row.id] = { id: row.id, name: getText(row.name), artistId: row.artistId };
    }

    // Build color lookup
    const colors = {};
    try {
        for (const row of tableRows(pdb.tables[PageType.COLORS])) {
            colors[row.id] = { id: row.id, name: getText(row.name) };
        }
    } catch (e) { /* colors table may be empty */ }

    // Read tracks
    const tracks = {};
    for (const row of tableRows(pdb.tables[PageType.TRACKS])) {
        const track = {
            id: row.id,
            title: getText(row.title),
            artistId: row.artistId,
            artistName: artists[row.artistId] ? artists[row.artistId].name : '',
            albumId: row.albumId,
            albumName: albums[row.albumId] ? albums[row.albumId].name : '',
            genreId: row.genreId,
            genreName: genres[row.genreId] ? genres[row.genreId].name : '',
            keyId: row.keyId,
            keyName: keys[row.keyId] ? keys[row.keyId].name : '',
            colorId: row.colorId,
            colorName: colors[row.colorId] ? colors[row.colorId].name : '',
            filePath: getText(row.filePath),
            duration: row.duration,
            tempo: row.tempo,
            bitrate: row.bitrate,
            rating: row.rating,
            year: row.year,
            sampleRate: row.sampleRate,
            sampleDepth: row.sampleDepth,
        };
        tracks[row.id] = track;
    }

    // Read playlist tree
    const playlists = [];
    for (const row of tableRows(pdb.tables[PageType.PLAYLIST_TREE])) {
        playlists.push({
            id: row.id,
            parentId: row.parentId,
            name: getText(row.name),
            isFolder: row.rawIsFolder !== 0,
            sortOrder: row.sortOrder,
        });
    }

    // Read playlist entries
    const playlistEntries = [];
    for (const row of tableRows(pdb.tables[PageType.PLAYLIST_ENTRIES])) {
        playlistEntries.push({
            playlistId: row.playlistId,
            trackId: row.trackId,
        });
    }

    // Build playlist tree structure with tracks
    const playlistMap = {};
    for (const p of playlists) {
        playlistMap[p.id] = { ...p, children: [], tracks: [] };
    }

    // Assign entries to playlists
    for (const entry of playlistEntries) {
        if (playlistMap[entry.playlistId]) {
            const track = tracks[entry.trackId];
            if (track) {
                playlistMap[entry.playlistId].tracks.push(track);
            }
        }
    }

    // Build tree (children under parents)
    const rootPlaylists = [];
    for (const p of playlists) {
        if (p.parentId === 0) {
            rootPlaylists.push(playlistMap[p.id]);
        } else if (playlistMap[p.parentId]) {
            playlistMap[p.parentId].children.push(playlistMap[p.id]);
        }
    }

    // Sort by sortOrder
    const sortFn = (a, b) => a.sortOrder - b.sortOrder;
    rootPlaylists.sort(sortFn);
    for (const p of Object.values(playlistMap)) {
        p.children.sort(sortFn);
    }

    return {
        summary: {
            tracks: Object.keys(tracks).length,
            artists: Object.keys(artists).length,
            albums: Object.keys(albums).length,
            genres: Object.keys(genres).length,
            playlists: playlists.length,
            playlistEntries: playlistEntries.length,
        },
        tree: rootPlaylists,
        tracks: Object.values(tracks),
        artists: Object.values(artists),
    };
}

// CLI interface
function main() {
    const args = process.argv.slice(2);
    if (args.length === 0) {
        console.error('Usage: node read_usb_pdb.js <usb_root_path> [--summary|--playlists|--tracks]');
        process.exit(1);
    }

    const usbRoot = args[0];
    const flags = args.slice(1);

    const pdbPath = findPdbPath(usbRoot);
    if (!pdbPath) {
        console.error(JSON.stringify({ error: `No export.pdb found on ${usbRoot}` }));
        process.exit(1);
    }

    try {
        const data = readPdb(pdbPath);

        if (flags.includes('--summary')) {
            console.log(JSON.stringify(data.summary, null, 2));
        } else if (flags.includes('--playlists')) {
            console.log(JSON.stringify(data.tree, null, 2));
        } else if (flags.includes('--tracks')) {
            console.log(JSON.stringify(data.tracks, null, 2));
        } else {
            // Full JSON output (used by web API)
            console.log(JSON.stringify(data));
        }
    } catch (err) {
        console.error(JSON.stringify({ error: err.message }));
        process.exit(1);
    }
}

main();
