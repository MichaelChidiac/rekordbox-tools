#!/usr/bin/env node
/**
 * read_history.js
 *
 * Reads HISTORY playlists from a Rekordbox USB drive's export.pdb.
 *
 * Usage:
 *   node read_history.js --list [--pdb <path>]
 *   node read_history.js --playlist "HISTORY 008" [--pdb <path>]
 *
 * Default PDB path: /Volumes/Extreme SSD/.PIONEER/rekordbox/export.pdb
 */

const { parsePdb, RekordboxPdb, tableRows } = require('rekordbox-parser');
const fs = require('fs');
const path = require('path');

const DEFAULT_PDB = '/Volumes/Extreme SSD/.PIONEER/rekordbox/export.pdb';
const { PageType } = RekordboxPdb;

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { pdb: DEFAULT_PDB, list: false, playlist: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--pdb')      opts.pdb      = args[++i];
    if (args[i] === '--list')     opts.list     = true;
    if (args[i] === '--playlist') opts.playlist = args[++i];
  }
  return opts;
}

function loadDb(pdbPath) {
  if (!fs.existsSync(pdbPath)) {
    console.error(`Error: PDB file not found: ${pdbPath}`);
    console.error('Is the USB drive mounted?');
    process.exit(1);
  }
  return parsePdb(fs.readFileSync(pdbPath));
}

function buildTrackMap(db) {
  const tracks = new Map();
  const tracksTable = db.tables.find(t => t.type === PageType.TRACKS);
  for (const row of tableRows(tracksTable)) {
    tracks.set(row.id, row);
  }
  return tracks;
}

function buildArtistMap(db) {
  const artists = new Map();
  const artistsTable = db.tables.find(t => t.type === PageType.ARTISTS);
  for (const row of tableRows(artistsTable)) {
    artists.set(row.id, row.name.body.text);
  }
  return artists;
}

function getHistoryPlaylists(db) {
  const table = db.tables.find(t => t.type === PageType.HISTORY_PLAYLISTS);
  const playlists = [];
  for (const row of tableRows(table)) {
    playlists.push({ id: row.id, name: row.name.body.text });
  }
  return playlists;
}

function getHistoryEntries(db, playlistId) {
  const table = db.tables.find(t => t.type === PageType.HISTORY_ENTRIES);
  const entries = [];
  for (const row of tableRows(table)) {
    if (row.playlistId === playlistId) {
      entries.push({ entryIndex: row.entryIndex, trackId: row.trackId });
    }
  }
  return entries.sort((a, b) => a.entryIndex - b.entryIndex);
}

function printTrackList(entries, trackMap, artistMap) {
  for (const entry of entries) {
    const track = trackMap.get(entry.trackId);
    if (!track) {
      console.log(`${entry.entryIndex}. [Track ID ${entry.trackId} - not found]`);
      continue;
    }
    const artist  = artistMap.get(track.artistId) || 'Unknown Artist';
    const title   = track.title.body.text;
    const bpm     = (track.tempo / 100).toFixed(1);
    const file    = track.filename?.body?.text || track.filePath?.body?.text?.split('/').pop() || '';
    console.log(`${entry.entryIndex}. [${bpm} BPM] ${artist} - ${title}`);
    console.log(`   File: ${file}`);
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────

const opts = parseArgs();

if (!opts.list && !opts.playlist) {
  console.log('Usage:');
  console.log('  node read_history.js --list [--pdb <path>]');
  console.log('  node read_history.js --playlist "HISTORY 008" [--pdb <path>]');
  process.exit(0);
}

const db = loadDb(opts.pdb);

if (opts.list) {
  console.log(`\nHistory playlists in: ${opts.pdb}\n`);
  const playlists = getHistoryPlaylists(db);
  for (const pl of playlists) {
    console.log(`  [${pl.id}] ${pl.name}`);
  }
  console.log('');
  process.exit(0);
}

// Print specific playlist
const playlists = getHistoryPlaylists(db);
const target = playlists.find(p => p.name.toLowerCase() === opts.playlist.toLowerCase());
if (!target) {
  console.error(`Playlist not found: "${opts.playlist}"`);
  console.error('Available:', playlists.map(p => p.name).join(', '));
  process.exit(1);
}

const trackMap  = buildTrackMap(db);
const artistMap = buildArtistMap(db);
const entries   = getHistoryEntries(db, target.id);

console.log(`\n=== ${target.name} (${entries.length} tracks) ===\n`);
printTrackList(entries, trackMap, artistMap);
console.log('');
