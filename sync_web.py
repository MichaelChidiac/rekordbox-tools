#!/usr/bin/env python3.11
"""
sync_web.py
===========
Simple web UI for sync operations (no dependencies on Flask/Django).

Uses Python's built-in http.server for zero-dependency setup.

Start server:
  python3.11 sync_web.py

Then open: http://localhost:8080
"""

import os
import sys
import json
import subprocess
import re
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

TOOLS_DIR = Path(__file__).parent
SYNC_MASTER = TOOLS_DIR / "sync_master.py"
SQLCIPHER_KEY = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"
MASTER_DB = Path.home() / "Library/Pioneer/rekordbox/master.db"
SYNC_CONFIG = TOOLS_DIR / "sync_config.json"

class SyncHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve HTML UI."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        
        elif parsed_path.path == '/api/status':
            self.send_json(200, {"status": "ready"})
        
        elif parsed_path.path == '/api/history-playlists':
            self.list_history_playlists()
        
        elif parsed_path.path == '/api/nas-status':
            try:
                from nas_lookup import check_traktor_ml_reachable, lookup_nas_tracks, TRAKTOR_ML_DB
                db_exists = TRAKTOR_ML_DB.exists()
                api_reachable = check_traktor_ml_reachable() if db_exists else False
                self.send_json(200, {
                    "available": db_exists and api_reachable,
                    "db_found": db_exists,
                    "api_reachable": api_reachable
                })
            except ImportError:
                self.send_json(200, {"available": False, "db_found": False, "api_reachable": False})
        
        elif parsed_path.path == '/api/playlists':
            self.get_playlist_tree_json()
        
        elif parsed_path.path == '/api/sync-config':
            try:
                if SYNC_CONFIG.exists():
                    data = json.loads(SYNC_CONFIG.read_text())
                else:
                    data = {"pinned_playlists": []}
                self.send_json(200, data)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
        
        elif parsed_path.path == '/api/usb-status':
            usb_path = self.detect_usb()
            if usb_path:
                self.send_json(200, {"connected": True, "path": usb_path})
            else:
                self.send_json(200, {"connected": False})
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle sync requests."""
        parsed_path = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()
        
        if parsed_path.path == '/api/sync':
            try:
                data = json.loads(body)
                result = self.execute_sync(data)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(400, {"error": str(e)})
        elif parsed_path.path == '/api/import-history':
            try:
                data = json.loads(body)
                result = self.execute_import_history(data)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(400, {"error": str(e)})
        elif parsed_path.path == '/api/sync-config':
            try:
                data = json.loads(body)
                SYNC_CONFIG.write_text(json.dumps(data, indent=2))
                self.send_json(200, {"saved": True})
            except Exception as e:
                self.send_json(400, {"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()
    
    def list_history_playlists(self):
        """List available history playlists from USB."""
        node = '/usr/local/bin/node'
        if not Path(node).exists():
            node = 'node'
        try:
            result = subprocess.run([node, str(TOOLS_DIR / 'read_history.js'), '--list'],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                playlists = self.parse_playlist_list(result.stdout)
                self.send_json(200, {"playlists": playlists})
            else:
                self.send_json(400, {"error": result.stderr})
        except Exception as e:
            self.send_json(400, {"error": str(e)})
    
    def parse_playlist_list(self, output: str) -> list:
        """Parse output from read_history.js --list."""
        playlists = []
        for line in output.split('\n'):
            line = line.strip()
            if line and line.startswith('['):
                match = re.match(r'\[(\d+)\]\s+(.*)', line)
                if match:
                    playlists.append(match.group(2))
        return playlists
    
    def execute_import_history(self, config):
        """Execute import history command."""
        playlist_name = config.get('playlist')
        traktor_name = config.get('traktor_name')
        
        if not playlist_name or not traktor_name:
            return {"success": False, "error": "Missing playlist_name or traktor_name"}
        
        args = [
            '--playlist', playlist_name,
            '--name', traktor_name
        ]
        
        cmd = [sys.executable, str(TOOLS_DIR / 'pdb_to_traktor.py')] + args
        print(f"[{datetime.now().isoformat()}] Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:] if result.stdout else "",
                "stderr": result.stderr[-1000:] if result.stderr else ""
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout (>1 hour)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def execute_sync(self, config):
        """Execute sync command."""
        args = []
        
        # Operation
        if config.get('target') == 'rekordbox':
            args.append('--to-rekordbox')
        elif config.get('target') == 'usb':
            args.append('--to-usb')
        
        # Selection
        if config.get('selection') == 'all':
            args.append('--all')
        elif config.get('selection') == 'playlists' and config.get('playlists'):
            args.extend(['--playlists'] + config['playlists'])
        elif config.get('selection') == 'select':
            args.append('--select')
        else:
            args.append('--all')
        
        # USB options
        if config.get('usb_path'):
            args.extend(['--usb', config['usb_path']])
        if config.get('sync_mode'):
            args.append('--sync')
        if config.get('dry_run'):
            args.append('--dry-run')
        if config.get('fetch_nas'):
            args.append('--fetch-nas')
        
        # Run
        cmd = [sys.executable, str(SYNC_MASTER)] + args
        print(f"[{datetime.now().isoformat()}] Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:] if result.stdout else "",  # Last 1KB
                "stderr": result.stderr[-1000:] if result.stderr else ""
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout (>1 hour)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def send_json(self, code, data):
        """Send JSON response."""
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        """Suppress default logs."""
        pass

    def get_playlist_tree_json(self):
        """Build playlist tree from Rekordbox master.db and send as JSON."""
        try:
            import sqlcipher3
        except ImportError:
            self.send_json(500, {"error": "sqlcipher3 module not available"})
            return

        if not MASTER_DB.exists():
            self.send_json(404, {"error": "master.db not found"})
            return

        try:
            con = sqlcipher3.connect(str(MASTER_DB), flags=sqlcipher3.SQLITE_OPEN_READONLY)
            con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")
            con.execute("PRAGMA cipher='sqlcipher'")
            con.execute("PRAGMA legacy=4")  # CRITICAL

            def build_tree(parent_id):
                rows = con.execute(
                    "SELECT ID, Name, Attribute FROM djmdPlaylist "
                    "WHERE ParentID=? ORDER BY Seq",
                    (parent_id,)
                ).fetchall()
                nodes = []
                for row_id, name, attr in rows:
                    if attr == 1:  # folder
                        children = build_tree(row_id)
                        total_tracks = sum(
                            n["track_count"] if n["type"] == "playlist"
                            else n.get("total_tracks", 0)
                            for n in children
                        )
                        nodes.append({
                            "id": row_id, "name": name, "type": "folder",
                            "children": children, "total_tracks": total_tracks
                        })
                    else:  # playlist
                        count = con.execute(
                            "SELECT COUNT(*) FROM djmdSongPlaylist WHERE PlaylistID=?",
                            (row_id,)
                        ).fetchone()[0]
                        nodes.append({
                            "id": row_id, "name": name, "type": "playlist",
                            "track_count": count
                        })
                return nodes

            tree = build_tree('root')
            con.close()
            self.send_json(200, tree)
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def detect_usb(self):
        """Check if a Pioneer USB drive is connected."""
        try:
            for vol in Path("/Volumes").iterdir():
                if (vol / "PIONEER").is_dir() or (vol / ".PIONEER").is_dir():
                    return str(vol)
        except OSError:
            pass
        return None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sync Master — Traktor ↔ Rekordbox/USB</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f1419;
            color: #e8e8e8;
            padding: 40px 20px;
        }
        .container { max-width: 700px; margin: 0 auto; }
        h1 { font-size: 32px; margin-bottom: 10px; color: #00bcd4; }
        .subtitle { color: #888; margin-bottom: 40px; }
        
        .panel {
            background: #1a1f26;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 30px;
            margin-bottom: 20px;
        }
        
        .section { margin-bottom: 30px; }
        .section-title {
            font-size: 14px;
            font-weight: 600;
            color: #00bcd4;
            text-transform: uppercase;
            margin-bottom: 15px;
            letter-spacing: 1px;
        }
        
        .option-group { display: flex; flex-direction: column; gap: 12px; }
        
        label {
            display: flex;
            align-items: center;
            padding: 12px;
            background: #232a33;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        label:hover { background: #2a3140; }
        
        input[type="radio"], input[type="checkbox"] {
            margin-right: 12px;
            cursor: pointer;
        }
        
        input[type="text"], select {
            width: 100%;
            padding: 12px;
            background: #232a33;
            border: 1px solid #444;
            border-radius: 6px;
            color: #e8e8e8;
            font-family: inherit;
            font-size: 14px;
        }
        
        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: #00bcd4;
            box-shadow: 0 0 0 3px rgba(0, 188, 212, 0.1);
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            background: none;
            padding: 0;
            cursor: default;
        }
        
        .buttons {
            display: flex;
            gap: 12px;
            margin-top: 30px;
        }
        
        button {
            flex: 1;
            padding: 14px;
            font-size: 16px;
            font-weight: 600;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .btn-primary {
            background: #00bcd4;
            color: #000;
        }
        .btn-primary:hover { background: #00d8e8; transform: translateY(-2px); }
        .btn-primary:active { transform: translateY(0); }
        
        .btn-secondary {
            background: #333;
            color: #fff;
        }
        .btn-secondary:hover { background: #444; }
        
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 6px;
            font-size: 14px;
            display: none;
        }
        
        .status.success {
            display: block;
            background: #1b5e20;
            color: #4caf50;
            border: 1px solid #4caf50;
        }
        
        .status.error {
            display: block;
            background: #b71c1c;
            color: #ff5252;
            border: 1px solid #ff5252;
        }
        
        .status.loading {
            display: block;
            background: #1a237e;
            color: #42a5f5;
            border: 1px solid #42a5f5;
        }
        
        .progress { margin-top: 10px; }
        .progress-bar {
            width: 100%;
            height: 4px;
            background: rgba(255,255,255,0.1);
            border-radius: 2px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: #00bcd4;
            animation: progress 2s infinite;
        }
        @keyframes progress {
            0% { width: 0%; }
            50% { width: 100%; }
            100% { width: 0%; }
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            border-bottom: 1px solid #333;
        }
        
        .tab-button {
            padding: 12px 20px;
            background: none;
            border: none;
            color: #888;
            cursor: pointer;
            font-weight: 600;
            border-bottom: 2px solid transparent;
            margin-bottom: -1px;
            transition: all 0.2s;
        }
        
        .tab-button.active {
            color: #00bcd4;
            border-bottom-color: #00bcd4;
        }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .tree-folder-row {
            display: flex; align-items: center; gap: 6px;
            padding: 4px 2px; user-select: none;
        }
        .tree-folder-row:hover { background: rgba(79,195,247,0.05); border-radius: 4px; }
        .tree-children { padding-left: 20px; }
        .tree-children.collapsed { display: none; }
        .tree-playlist {
            padding: 4px 2px; display: flex; align-items: center; gap: 6px;
        }
        .tree-playlist label {
            flex: 1; cursor: pointer; display: inline; padding: 0;
            background: none; border-radius: 0; font-weight: normal;
        }
        .tree-playlist label:hover { background: none; }
        .tree-count { color: #888; font-size: 0.85em; }
        .pin-btn {
            cursor: pointer; opacity: 0.3; font-size: 0.9em;
            transition: opacity 0.2s;
        }
        .pin-btn:hover { opacity: 0.7; }
        .pin-btn.pinned { opacity: 1; }
        .pinned-highlight {
            background: rgba(79,195,247,0.1); border-radius: 4px; padding: 2px 4px;
        }
        .folder-arrow { display: inline-block; width: 16px; cursor: pointer; flex-shrink: 0; }
        .folder-name { font-weight: bold; cursor: pointer; flex: 1; }
        .folder-name:hover { color: #4fc3f7; }
        .tree-folder-cb { cursor: pointer; flex-shrink: 0; }
        .usb-status {
            padding: 8px 12px; border-radius: 8px; margin-bottom: 12px;
            font-size: 0.9em; display: flex; align-items: center; gap: 8px;
            flex-wrap: wrap;
        }
        .usb-connected { background: rgba(76,175,80,0.15); color: #81c784; }
        .usb-disconnected { background: rgba(244,67,54,0.15); color: #e57373; }
        .auto-sync-btn {
            margin-left: auto; padding: 4px 14px; background: #00bcd4;
            color: #000; border: none; border-radius: 4px; cursor: pointer;
            font-weight: 600; font-size: 0.85em; text-transform: none;
            letter-spacing: 0; flex: none;
        }
        .auto-sync-btn:hover { background: #00d8e8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎚️ Sync Master</h1>
        <p class="subtitle">Traktor ↔ Rekordbox / USB Sync</p>
        
        <div class="tabs">
            <button class="tab-button active" onclick="switchTab('sync-tab', this)">📦 Library Sync</button>
            <button class="tab-button" onclick="switchTab('history-tab', this)">📜 Import History</button>
        </div>
        
        <!-- SYNC TAB -->
        <div class="tab-content active" id="sync-tab">
            <div class="panel">
                <!-- USB STATUS -->
                <div id="usb-status" class="usb-status usb-disconnected">
                    💾 Checking USB...
                </div>
                
                <!-- TARGET -->
                <div class="section">
                    <div class="section-title">🎯 Where to sync?</div>
                    <div class="option-group">
                        <label>
                            <input type="radio" name="target" value="rekordbox" checked>
                            Rekordbox (master.db)
                        </label>
                        <label>
                            <input type="radio" name="target" value="usb">
                            Pioneer USB (CDJ-compatible)
                        </label>
                    </div>
                </div>
                
                <!-- SELECTION -->
                <div class="section">
                    <div class="section-title">📋 What to sync?</div>
                    <div class="option-group">
                        <label>
                            <input type="radio" name="selection" value="all" checked>
                            Entire library
                        </label>
                        <label>
                            <input type="radio" name="selection" value="playlists">
                            Pick playlists
                        </label>
                    </div>
                    <div id="playlist-tree" style="display:none; max-height:400px; overflow-y:auto; margin-top:10px; padding:8px; border:1px solid #333; border-radius:8px; background:#1a1a1a;">
                        <div style="text-align:center; color:#888;">Loading playlists...</div>
                    </div>
                </div>
                
                <!-- USB OPTIONS -->
                <div class="section" id="usb-options" style="display:none;">
                    <div class="section-title">⚙️ USB Options</div>
                    <div class="option-group">
                        <label>
                            <input type="checkbox" id="sync-mode">
                            Incremental sync (only new/changed)
                        </label>
                        <label>
                            <input type="checkbox" id="dry-run">
                            Preview only (don't write)
                        </label>
                        <label>
                            <input type="checkbox" id="fetch-nas">
                            <span id="fetch-nas-label">🌐 Fetch missing tracks from NAS</span>
                        </label>
                    </div>
                </div>
                
                <!-- BUTTONS -->
                <div class="buttons">
                    <button class="btn-primary" onclick="startSync()">Start Sync</button>
                    <button class="btn-secondary" onclick="resetForm()">Reset</button>
                </div>
                
                <!-- STATUS -->
                <div class="status" id="status"></div>
            </div>
        </div>
        
        <!-- HISTORY TAB -->
        <div class="tab-content" id="history-tab">
            <div class="panel">
                <div class="section">
                    <div class="section-title">📜 Import History Playlist</div>
                    
                    <div class="form-group">
                        <label>Select a history playlist from USB:</label>
                        <select id="history-playlist">
                            <option value="">Loading playlists...</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label>Give it a name in Traktor:</label>
                        <input type="text" id="history-name" value="04 - History / Live Events / " placeholder="e.g., 04 - History / Live Events / My Set">
                    </div>
                    
                    <div class="form-group">
                        <label style="font-size: 12px; color: #888;">💡 Tip: Use path format for folders, e.g., "04 - History / Live Events / My Set"</label>
                    </div>
                </div>
                
                <!-- BUTTONS -->
                <div class="buttons">
                    <button class="btn-primary" onclick="importHistory()">Import to Traktor</button>
                    <button class="btn-secondary" onclick="resetHistoryForm()">Reset</button>
                </div>
                
                <!-- STATUS -->
                <div class="status" id="history-status"></div>
            </div>
        </div>
    </div>
    
    <script>
        // ── TAB SWITCHING ────────────────────────────────────────────────
        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
            
            if (tabId === 'history-tab') {
                loadHistoryPlaylists();
            }
        }
        
        // ── HELPERS ──────────────────────────────────────────────────────
        function escapeHtml(str) {
            var d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        }
        
        // ── SYNC TAB ─────────────────────────────────────────────────────
        var targetRadios = document.querySelectorAll('input[name="target"]');
        var selectionRadios = document.querySelectorAll('input[name="selection"]');
        var usbOptions = document.getElementById('usb-options');
        var playlistTree = document.getElementById('playlist-tree');
        
        targetRadios.forEach(function(r) {
            r.addEventListener('change', function() {
                usbOptions.style.display = r.value === 'usb' ? 'block' : 'none';
            });
        });
        
        selectionRadios.forEach(function(r) {
            r.addEventListener('change', function() {
                var sel = document.querySelector('input[name="selection"]:checked').value;
                playlistTree.style.display = sel === 'playlists' ? 'block' : 'none';
                if (sel === 'playlists' && !playlistTree.dataset.loaded) {
                    loadPlaylists();
                }
            });
        });
        
        // Check NAS availability on load
        fetch('/api/nas-status')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var cb = document.getElementById('fetch-nas');
                var label = document.getElementById('fetch-nas-label');
                if (!data.available) {
                    cb.disabled = true;
                    label.style.opacity = '0.5';
                    label.title = data.db_found
                        ? 'traktor-ml server not running (start it + SSH tunnel)'
                        : 'traktor-ml database not found';
                    label.textContent = '🌐 Fetch from NAS (unavailable)';
                }
            })
            .catch(function() {});
        
        // ── PLAYLIST TREE ────────────────────────────────────────────────
        var pinnedPlaylists = new Set();
        var allPlaylistData = [];
        
        function loadPlaylists() {
            playlistTree.innerHTML = '<div style="text-align:center; color:#888;">Loading playlists...</div>';
            
            Promise.all([
                fetch('/api/playlists').then(function(r) { return r.json(); }),
                fetch('/api/sync-config').then(function(r) { return r.json(); }).catch(function() { return {pinned_playlists: []}; })
            ]).then(function(results) {
                var tree = results[0];
                var config = results[1];
                allPlaylistData = tree;
                pinnedPlaylists = new Set(config.pinned_playlists || []);
                playlistTree.innerHTML = '';
                playlistTree.dataset.loaded = 'true';
                renderTree(tree, playlistTree);
                updateUsbAutoSyncButton();
            }).catch(function(e) {
                playlistTree.innerHTML = '<div style="color:#e57373;">Error: ' + escapeHtml(e.message || String(e)) + '</div>';
            });
        }
        
        function renderTree(nodes, container) {
            nodes.forEach(function(node) {
                if (node.type === 'folder') {
                    var isPinned = pinnedPlaylists.has(node.id);
                    var folderDiv = document.createElement('div');
                    folderDiv.className = 'tree-folder-item';

                    var header = document.createElement('div');
                    header.className = 'tree-folder-row' + (isPinned ? ' pinned-highlight' : '');

                    // ▶ Arrow — only toggles expand/collapse
                    var arrow = document.createElement('span');
                    arrow.className = 'folder-arrow';
                    arrow.textContent = '▶';

                    // Checkbox for folder selection
                    var cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.className = 'tree-folder-cb';
                    cb.value = node.name;
                    cb.dataset.id = node.id;
                    cb.dataset.type = 'folder';
                    if (isPinned) cb.checked = true;

                    // 📁 Label — only toggles expand/collapse
                    var lbl = document.createElement('span');
                    lbl.className = 'folder-name';
                    lbl.textContent = '📁 ' + node.name;

                    var count = document.createElement('span');
                    count.className = 'tree-count';
                    count.textContent = '(' + (node.total_tracks || 0) + ')';

                    var pin = document.createElement('span');
                    pin.className = 'pin-btn' + (isPinned ? ' pinned' : '');
                    pin.title = 'Pin for auto-sync';
                    pin.textContent = '📌';

                    header.appendChild(arrow);
                    header.appendChild(cb);
                    header.appendChild(lbl);
                    header.appendChild(count);
                    header.appendChild(pin);

                    var children = document.createElement('div');
                    children.className = 'tree-children collapsed';
                    renderTree(node.children || [], children);

                    folderDiv.appendChild(header);
                    folderDiv.appendChild(children);
                    container.appendChild(folderDiv);

                    // Arrow click → toggle expand/collapse only
                    arrow.addEventListener('click', function() {
                        children.classList.toggle('collapsed');
                        arrow.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
                    });
                    // Label click → toggle expand/collapse only
                    lbl.addEventListener('click', function() {
                        children.classList.toggle('collapsed');
                        arrow.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
                    });
                    // Folder checkbox → propagate to all children; update ancestors
                    cb.addEventListener('change', function() {
                        setSubtreeChecked(children, cb.checked);
                        updateAncestorFolderStates(cb);
                    });
                    // Pin button
                    (function(pinEl, nodeId, cbEl, rowEl) {
                        pinEl.addEventListener('click', function() {
                            togglePin(pinEl, nodeId, cbEl, rowEl);
                        });
                    })(pin, node.id, cb, header);

                } else {
                    var div = document.createElement('div');
                    var isPinned = pinnedPlaylists.has(node.id);
                    div.className = 'tree-playlist' + (isPinned ? ' pinned-highlight' : '');

                    var cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.value = node.name;
                    cb.dataset.id = node.id;
                    if (isPinned) cb.checked = true;
                    cb.addEventListener('change', function() {
                        updateAncestorFolderStates(cb);
                    });

                    var lbl = document.createElement('label');
                    lbl.textContent = node.name;
                    lbl.addEventListener('click', function(evt) {
                        evt.preventDefault();
                        cb.checked = !cb.checked;
                        updateAncestorFolderStates(cb);
                    });

                    var count = document.createElement('span');
                    count.className = 'tree-count';
                    count.textContent = '(' + node.track_count + ')';

                    var pin = document.createElement('span');
                    pin.className = 'pin-btn' + (isPinned ? ' pinned' : '');
                    pin.title = 'Pin for auto-sync';
                    pin.textContent = '📌';
                    (function(pinEl, nodeId, cbEl, rowDiv) {
                        pinEl.addEventListener('click', function() {
                            togglePin(pinEl, nodeId, cbEl, rowDiv);
                        });
                    })(pin, node.id, cb, div);

                    div.appendChild(cb);
                    div.appendChild(lbl);
                    div.appendChild(count);
                    div.appendChild(pin);
                    container.appendChild(div);
                }
            });
        }
        
        function toggleFolder(header) {
            var children = header.nextElementSibling;
            var arrow = header.querySelector('.folder-arrow');
            children.classList.toggle('collapsed');
            arrow.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
        }

        // ── SUBTREE HELPERS ──────────────────────────────────────────────
        // Check/uncheck every checkbox inside a .tree-children container.
        function setSubtreeChecked(container, checked) {
            container.querySelectorAll('input[type="checkbox"]').forEach(function(c) {
                c.checked = checked;
                c.indeterminate = false;
            });
        }

        // After any checkbox change, walk UP through .tree-children containers
        // and set each ancestor folder checkbox to checked / indeterminate / unchecked.
        function updateAncestorFolderStates(startCb) {
            var el = startCb.closest('.tree-children');
            while (el) {
                var folderRow = el.previousElementSibling;
                if (!folderRow || !folderRow.classList.contains('tree-folder-row')) break;
                var folderCb = folderRow.querySelector('input[type="checkbox"][data-type="folder"]');
                if (!folderCb) break;

                // Collect DIRECT child checkboxes only (playlists + sub-folder roots)
                var childCbs = Array.from(el.querySelectorAll(
                    ':scope > .tree-playlist > input[type="checkbox"], ' +
                    ':scope > .tree-folder-item > .tree-folder-row > input[type="checkbox"][data-type="folder"]'
                ));

                var total       = childCbs.length;
                var checkedCnt  = childCbs.filter(function(c) { return c.checked && !c.indeterminate; }).length;
                var indetermCnt = childCbs.filter(function(c) { return c.indeterminate; }).length;

                if (total === 0 || (checkedCnt === 0 && indetermCnt === 0)) {
                    folderCb.checked = false;
                    folderCb.indeterminate = false;
                } else if (checkedCnt === total) {
                    folderCb.checked = true;
                    folderCb.indeterminate = false;
                } else {
                    folderCb.checked = false;
                    folderCb.indeterminate = true;
                }

                // Climb to the next ancestor level
                el = folderRow.closest('.tree-children');
            }
        }
        
        function togglePin(el, id, cb, row) {
            if (pinnedPlaylists.has(id)) {
                pinnedPlaylists.delete(id);
                el.classList.remove('pinned');
                row.classList.remove('pinned-highlight');
            } else {
                pinnedPlaylists.add(id);
                el.classList.add('pinned');
                row.classList.add('pinned-highlight');
                cb.checked = true;
            }
            updateAncestorFolderStates(cb);
            savePinnedConfig();
            updateUsbAutoSyncButton();
        }
        
        function savePinnedConfig() {
            fetch('/api/sync-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pinned_playlists: Array.from(pinnedPlaylists) })
            }).catch(function() {});
        }
        
        // Returns the minimal flat list of names for the pinned-IDs set.
        // Pinned FOLDER  → push folder name (backend resolves recursively).
        // Pinned PLAYLIST → push playlist name only if no ancestor folder is also pinned.
        function findPlaylistNames(nodes, ids) {
            var names = [];
            function walk(ns, ancestorFolderPinned) {
                for (var i = 0; i < ns.length; i++) {
                    var node = ns[i];
                    if (node.type === 'folder') {
                        if (ids.has(node.id)) {
                            names.push(node.name);   // whole folder → single entry
                        } else {
                            walk(node.children || [], false);
                        }
                    } else {
                        // playlist — only add if its own ID is pinned
                        // (ancestor folder pinned is already handled above)
                        if (ids.has(node.id) && !ancestorFolderPinned) {
                            names.push(node.name);
                        }
                    }
                }
            }
            walk(nodes, false);
            return names;
        }

        // Returns the minimal flat list of names from the CHECKED checkboxes in
        // the tree UI.  A checked folder adds its name and skips its children
        // (avoids redundancy, e.g. both "04 - History" AND "- AS").
        function getCheckedSelectionNames() {
            var names = [];
            function walkEl(container) {
                Array.from(container.children).forEach(function(child) {
                    if (child.classList.contains('tree-folder-item')) {
                        var folderRow = child.querySelector(':scope > .tree-folder-row');
                        var folderCb  = folderRow
                            ? folderRow.querySelector('input[type="checkbox"][data-type="folder"]')
                            : null;
                        if (folderCb && folderCb.checked && !folderCb.indeterminate) {
                            // Whole folder checked → one entry, skip children
                            names.push(folderCb.value);
                        } else {
                            // Partial / unchecked folder → recurse into children
                            var childrenContainer = child.querySelector(':scope > .tree-children');
                            if (childrenContainer) walkEl(childrenContainer);
                        }
                    } else if (child.classList.contains('tree-playlist')) {
                        var cb = child.querySelector('input[type="checkbox"]');
                        if (cb && cb.checked) names.push(cb.value);
                    }
                });
            }
            walkEl(document.getElementById('playlist-tree'));
            return names;
        }
        
        // ── USB STATUS ───────────────────────────────────────────────────
        var lastUsbPath = null;
        
        function checkUsbStatus() {
            fetch('/api/usb-status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    lastUsbPath = data.connected ? data.path : null;
                    var el = document.getElementById('usb-status');
                    if (data.connected) {
                        el.className = 'usb-status usb-connected';
                        el.innerHTML = '💾 USB connected: <strong>' + escapeHtml(data.path) + '</strong>';
                    } else {
                        el.className = 'usb-status usb-disconnected';
                        el.innerHTML = '💾 No Pioneer USB detected';
                    }
                    updateUsbAutoSyncButton();
                })
                .catch(function() {});
        }
        
        function updateUsbAutoSyncButton() {
            var el = document.getElementById('usb-status');
            var existing = document.getElementById('auto-sync-btn');
            if (existing) existing.remove();
            
            if (lastUsbPath && pinnedPlaylists.size > 0) {
                var btn = document.createElement('button');
                btn.id = 'auto-sync-btn';
                btn.className = 'auto-sync-btn';
                btn.textContent = '⚡ Auto-sync pinned';
                btn.addEventListener('click', autoSyncPinned);
                el.appendChild(btn);
            }
        }
        
        function autoSyncPinned() {
            var doSync = function(names) {
                if (names.length === 0) {
                    alert('No pinned playlists found. Load and pin playlists first.');
                    return;
                }
                var status = document.getElementById('status');
                status.className = 'status loading';
                status.innerHTML = '<div class="progress"><div class="progress-bar"><div class="progress-fill"></div></div></div>Auto-syncing ' + names.length + ' pinned playlist(s) to USB...';
                
                fetch('/api/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        target: 'usb',
                        selection: 'playlists',
                        playlists: names,
                        sync_mode: true,
                        dry_run: false,
                        fetch_nas: false
                    })
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        status.className = 'status success';
                        status.innerHTML = '✅ Auto-sync completed!<br><small>' + escapeHtml(data.stdout || '') + '</small>';
                    } else {
                        status.className = 'status error';
                        status.innerHTML = '❌ Auto-sync failed:<br><small>' + escapeHtml(data.error || data.stderr || '') + '</small>';
                    }
                })
                .catch(function(e) {
                    status.className = 'status error';
                    status.innerHTML = '❌ Error: ' + escapeHtml(e.message);
                });
            };
            
            if (allPlaylistData.length > 0) {
                doSync(findPlaylistNames(allPlaylistData, pinnedPlaylists));
            } else {
                fetch('/api/playlists')
                    .then(function(r) { return r.json(); })
                    .then(function(tree) {
                        allPlaylistData = tree;
                        doSync(findPlaylistNames(tree, pinnedPlaylists));
                    })
                    .catch(function(e) {
                        alert('Failed to load playlists: ' + (e.message || String(e)));
                    });
            }
        }
        
        setInterval(checkUsbStatus, 5000);
        checkUsbStatus();
        
        // Load pinned config on start (for auto-sync button even before tree is opened)
        fetch('/api/sync-config')
            .then(function(r) { return r.json(); })
            .then(function(config) {
                pinnedPlaylists = new Set(config.pinned_playlists || []);
                updateUsbAutoSyncButton();
            })
            .catch(function() {});
        
        // ── SYNC ─────────────────────────────────────────────────────────
        function startSync() {
            var target = document.querySelector('input[name="target"]:checked').value;
            var selection = document.querySelector('input[name="selection"]:checked').value;
            var syncMode = document.getElementById('sync-mode').checked;
            var dryRun = document.getElementById('dry-run').checked;
            var fetchNas = document.getElementById('fetch-nas').checked;
            
            var config = { target: target, selection: selection, sync_mode: syncMode, dry_run: dryRun, fetch_nas: fetchNas };
            
            if (selection === 'playlists') {
                var names = getCheckedSelectionNames();
                if (names.length === 0) {
                    alert('Please select at least one playlist or folder');
                    return;
                }
                config.playlists = names;
            }
            
            var status = document.getElementById('status');
            status.className = 'status loading';
            status.innerHTML = '<div class="progress"><div class="progress-bar"><div class="progress-fill"></div></div></div>Syncing...';
            
            fetch('/api/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    status.className = 'status success';
                    status.innerHTML = '✅ Sync completed successfully!<br><small>' + escapeHtml(data.stdout || '') + '</small>';
                } else {
                    status.className = 'status error';
                    status.innerHTML = '❌ Sync failed:<br><small>' + escapeHtml(data.error || data.stderr || '') + '</small>';
                }
            })
            .catch(function(e) {
                status.className = 'status error';
                status.innerHTML = '❌ Error: ' + escapeHtml(e.message);
            });
        }
        
        function resetForm() {
            document.querySelector('input[name="target"][value="rekordbox"]').checked = true;
            document.querySelector('input[name="selection"][value="all"]').checked = true;
            document.getElementById('sync-mode').checked = false;
            document.getElementById('dry-run').checked = false;
            document.getElementById('fetch-nas').checked = false;
            document.getElementById('status').className = 'status';
            document.getElementById('status').innerHTML = '';
            usbOptions.style.display = 'none';
            playlistTree.style.display = 'none';
        }
        
        // ── HISTORY TAB ──────────────────────────────────────────────────
        function loadHistoryPlaylists() {
            var select = document.getElementById('history-playlist');
            select.innerHTML = '<option value="">Loading...</option>';
            
            fetch('/api/history-playlists')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.playlists && data.playlists.length > 0) {
                        select.innerHTML = '<option value="">Choose a playlist...</option>' +
                            data.playlists.map(function(p) {
                                return '<option value="' + escapeHtml(p) + '">' + escapeHtml(p) + '</option>';
                            }).join('');
                    } else {
                        select.innerHTML = '<option value="">No playlists found (USB connected?)</option>';
                    }
                })
                .catch(function(e) {
                    select.innerHTML = '<option value="">Error loading playlists</option>';
                });
        }
        
        function importHistory() {
            var playlist = document.getElementById('history-playlist').value;
            var traktorName = document.getElementById('history-name').value.trim();
            
            if (!playlist) {
                alert('Please select a history playlist');
                return;
            }
            if (!traktorName) {
                alert('Please enter a name for the Traktor playlist');
                return;
            }
            
            var config = { playlist: playlist, traktor_name: traktorName };
            var status = document.getElementById('history-status');
            status.className = 'status loading';
            status.innerHTML = '<div class="progress"><div class="progress-bar"><div class="progress-fill"></div></div></div>Importing...';
            
            fetch('/api/import-history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    status.className = 'status success';
                    status.innerHTML = '✅ Playlist imported successfully!<br><small>Open Traktor to see the new playlist.</small>';
                    resetHistoryForm();
                } else {
                    status.className = 'status error';
                    status.innerHTML = '❌ Import failed:<br><small>' + escapeHtml(data.error || data.stderr || '') + '</small>';
                }
            })
            .catch(function(e) {
                status.className = 'status error';
                status.innerHTML = '❌ Error: ' + escapeHtml(e.message);
            });
        }
        
        function resetHistoryForm() {
            document.getElementById('history-playlist').value = '';
            document.getElementById('history-name').value = '';
            document.getElementById('history-status').className = 'status';
            document.getElementById('history-status').innerHTML = '';
        }
    </script>
</body>
</html>
"""

class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True

def main():
    port = 8080
    server = ReusableHTTPServer(('localhost', port), SyncHandler)
    
    print(f"🌐 Sync Master web UI")
    print(f"   Server: http://localhost:{port}")
    print(f"   Press Ctrl+C to stop\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped")

if __name__ == '__main__':
    main()
