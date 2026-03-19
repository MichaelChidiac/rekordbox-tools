#!/usr/bin/env node
/**
 * validate_usb.js
 *
 * Validates a Rekordbox-exported USB drive without plugging into a CDJ.
 *
 * Checks:
 *   1. All tracks referenced in the PDB have their audio file on the USB
 *   2. All tracks have their ANLZ analysis file (.DAT) present
 *   3. All tracks have their ANLZ extended file (.EXT) present
 *   4. Playlist structure summary (folders, playlists, track counts)
 *
 * Usage:
 *   node validate_usb.js                          # auto-detect all mounted Pioneer USBs
 *   node validate_usb.js /Volumes/PATRIOT         # specific drive
 *   node validate_usb.js --verbose                # show every missing file
 *
 * Exit code: 0 if all drives pass, 1 if any issues found.
 */

const { RekordboxPdb, parsePdb, tableRows } = require('rekordbox-parser');
const fs   = require('fs');
const path = require('path');

const { PageType } = RekordboxPdb;

// ── CLI args ──────────────────────────────────────────────────────────────────
const args    = process.argv.slice(2);
const verbose = args.includes('--verbose') || args.includes('-v');
const drives  = args.filter(a => !a.startsWith('-'));

// ── Auto-detect Pioneer USB mounts ───────────────────────────────────────────
function findPioneerDrives() {
  const found = [];
  const vols  = fs.readdirSync('/Volumes');
  for (const vol of vols) {
    const base = path.join('/Volumes', vol);
    // Rekordbox uses .PIONEER (hidden) or PIONEER (visible) depending on drive format
    for (const dir of ['.PIONEER', 'PIONEER']) {
      const pdbPath = path.join(base, dir, 'rekordbox', 'export.pdb');
      if (fs.existsSync(pdbPath)) {
        found.push({ mount: base, pioneerDir: dir, pdb: pdbPath });
        break;
      }
    }
  }
  return found;
}

// ── Build helpers ─────────────────────────────────────────────────────────────
function buildTrackMap(db) {
  const map   = new Map();
  const table = db.tables.find(t => t.type === PageType.TRACKS);
  for (const row of tableRows(table)) map.set(row.id, row);
  return map;
}

function buildArtistMap(db) {
  const map   = new Map();
  const table = db.tables.find(t => t.type === PageType.ARTISTS);
  for (const row of tableRows(table)) map.set(row.id, row.name?.body?.text || '?');
  return map;
}

function buildPlaylistTree(db) {
  const table = db.tables.find(t => t.type === PageType.PLAYLIST_TREE);
  const nodes = new Map();
  for (const row of tableRows(table)) {
    nodes.set(row.id, {
      id:       row.id,
      parentId: row.parentId,
      name:     row.name?.body?.text || '?',
      isFolder: row.isFolder,
    });
  }
  return nodes;
}

function buildPlaylistEntries(db) {
  const table = db.tables.find(t => t.type === PageType.PLAYLIST_ENTRIES);
  const map   = new Map(); // playlistId → Set of trackIds
  for (const row of tableRows(table)) {
    if (!map.has(row.playlistId)) map.set(row.playlistId, new Set());
    map.get(row.playlistId).add(row.trackId);
  }
  return map;
}

// ── Validate one drive ────────────────────────────────────────────────────────
function validateDrive({ mount, pioneerDir, pdb: pdbPath }) {
  const divider = '─'.repeat(60);
  console.log(`\n${divider}`);
  console.log(`Drive:  ${mount}`);
  console.log(`PDB:    ${pdbPath}`);
  console.log(divider);

  const db = parsePdb(fs.readFileSync(pdbPath));

  const trackMap     = buildTrackMap(db);
  const artistMap    = buildArtistMap(db);
  const playlistTree = buildPlaylistTree(db);
  const plEntries    = buildPlaylistEntries(db);

  const totalTracks = trackMap.size;
  console.log(`Tracks in PDB:  ${totalTracks}`);

  // ── 1. Playlist summary ──────────────────────────────────────────────────
  let folderCount = 0, playlistCount = 0, totalLinks = 0;
  for (const node of playlistTree.values()) {
    if (node.isFolder) folderCount++;
    else {
      playlistCount++;
      totalLinks += (plEntries.get(node.id)?.size || 0);
    }
  }
  console.log(`Folders:        ${folderCount}`);
  console.log(`Playlists:      ${playlistCount}`);
  console.log(`Track links:    ${totalLinks}`);

  // ── 2. Check audio files & ANLZ ─────────────────────────────────────────
  let missingAudio = [], missingDat = [], missingExt = [];

  for (const [id, track] of trackMap) {
    const filePath    = track.filePath?.body?.text;
    const analyzePath = track.analyzePath?.body?.text;
    const artist      = artistMap.get(track.artistId) || 'Unknown';
    const title       = track.title?.body?.text || '?';
    const label       = `[${id}] ${artist} - ${title}`;

    // Audio file check
    if (filePath) {
      const absAudio = path.join(mount, filePath);
      if (!fs.existsSync(absAudio)) {
        missingAudio.push({ label, path: filePath });
      }
    }

    // ANLZ .DAT check
    if (analyzePath) {
      const absAnlz = path.join(mount, pioneerDir, analyzePath.replace(/^\/.PIONEER\//, '/').replace(/^\/PIONEER\//, '/'));
      // analyzePath is relative to the pioneer root e.g. /.PIONEER/USBANLZ/...
      // strip the leading /.PIONEER or /PIONEER prefix since we already have pioneerDir
      const anlzRelative = analyzePath.replace(/^\/(\.PIONEER|PIONEER)\//, '');
      const datPath = path.join(mount, pioneerDir, anlzRelative);
      const extPath = datPath.replace(/ANLZ(\d+)\.DAT$/, 'ANLZ$1.EXT');

      if (!fs.existsSync(datPath)) {
        missingDat.push({ label, path: datPath });
      }
      if (!fs.existsSync(extPath)) {
        missingExt.push({ label, path: extPath });
      }
    } else {
      missingDat.push({ label, path: '(no analyzePath in PDB)' });
      missingExt.push({ label, path: '(no analyzePath in PDB)' });
    }
  }

  // ── 3. Report ────────────────────────────────────────────────────────────
  const ok = missingAudio.length === 0 && missingDat.length === 0 && missingExt.length === 0;
  console.log('');

  function reportSection(label, items, icon) {
    if (items.length === 0) {
      console.log(`  ✅ ${label}: all present`);
    } else {
      console.log(`  ${icon} ${label}: ${items.length} missing`);
      if (verbose) {
        for (const { label: l, path: p } of items.slice(0, 50)) {
          console.log(`      • ${l}`);
          console.log(`        ${p}`);
        }
        if (items.length > 50) console.log(`      … and ${items.length - 50} more`);
      } else {
        console.log(`      (run with --verbose to see details)`);
      }
    }
  }

  reportSection('Audio files', missingAudio, '❌');
  reportSection('ANLZ .DAT files', missingDat, '⚠️ ');
  reportSection('ANLZ .EXT files', missingExt, '⚠️ ');

  if (ok) {
    console.log(`\n  ✅  Drive looks good — ${totalTracks} tracks, all files present.`);
  } else {
    const total = missingAudio.length + missingDat.length + missingExt.length;
    console.log(`\n  ⚠️   ${total} issue(s) found.`);
  }

  // ── 4. Top 10 largest playlists ──────────────────────────────────────────
  console.log('\nTop 10 playlists by track count:');
  const playlistSizes = [];
  for (const [plId, trackSet] of plEntries) {
    const node = playlistTree.get(plId);
    if (node && !node.isFolder) {
      playlistSizes.push({ name: node.name, count: trackSet.size });
    }
  }
  playlistSizes.sort((a, b) => b.count - a.count);
  for (const { name, count } of playlistSizes.slice(0, 10)) {
    console.log(`  ${String(count).padStart(5)}  ${name}`);
  }

  return ok;
}

// ── Main ──────────────────────────────────────────────────────────────────────
const targets = drives.length > 0
  ? drives.map(mount => {
      for (const dir of ['.PIONEER', 'PIONEER']) {
        const pdb = path.join(mount, dir, 'rekordbox', 'export.pdb');
        if (fs.existsSync(pdb)) return { mount, pioneerDir: dir, pdb };
      }
      console.error(`No Rekordbox export found at: ${mount}`);
      process.exit(1);
    })
  : findPioneerDrives();

if (targets.length === 0) {
  console.error('No Pioneer USB drives found. Plug in your USB and try again.');
  process.exit(1);
}

console.log(`Found ${targets.length} Pioneer USB drive(s).`);

let allOk = true;
for (const target of targets) {
  const ok = validateDrive(target);
  if (!ok) allOk = false;
}

console.log('\n' + '═'.repeat(60));
console.log(allOk ? '✅  All drives passed validation.' : '⚠️   Some issues found — see above.');
process.exit(allOk ? 0 : 1);
