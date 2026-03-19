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
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

TOOLS_DIR = Path(__file__).parent
SYNC_MASTER = TOOLS_DIR / "sync_master.py"

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
        else:
            self.send_response(404)
            self.end_headers()
    
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
        elif config.get('selection') == 'select':
            args.append('--select')
        elif config.get('playlists'):
            args.extend(['--playlists'] + config['playlists'])
        else:
            args.append('--all')
        
        # USB options
        if config.get('usb_path'):
            args.extend(['--usb', config['usb_path']])
        if config.get('sync_mode'):
            args.append('--sync')
        if config.get('dry_run'):
            args.append('--dry-run')
        
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
        .container { max-width: 600px; margin: 0 auto; }
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
    </style>
</head>
<body>
    <div class="container">
        <h1>🎚️ Sync Master</h1>
        <p class="subtitle">Traktor ↔ Rekordbox / USB Sync</p>
        
        <div class="panel">
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
                        <input type="radio" name="selection" value="select">
                        Pick playlists (interactive)
                    </label>
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
    
    <script>
        const targetRadios = document.querySelectorAll('input[name="target"]');
        const usbOptions = document.getElementById('usb-options');
        
        targetRadios.forEach(r => {
            r.addEventListener('change', () => {
                usbOptions.style.display = r.value === 'usb' ? 'block' : 'none';
            });
        });
        
        function startSync() {
            const target = document.querySelector('input[name="target"]:checked').value;
            const selection = document.querySelector('input[name="selection"]:checked').value;
            const syncMode = document.getElementById('sync-mode').checked;
            const dryRun = document.getElementById('dry-run').checked;
            
            const config = { target, selection, sync_mode: syncMode, dry_run: dryRun };
            
            const status = document.getElementById('status');
            status.className = 'status loading';
            status.innerHTML = '<div class="progress"><div class="progress-fill"></div></div>Syncing...';
            
            fetch('/api/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    status.className = 'status success';
                    status.innerHTML = '✅ Sync completed successfully!<br><small>' + (data.stdout || '') + '</small>';
                } else {
                    status.className = 'status error';
                    status.innerHTML = '❌ Sync failed:<br><small>' + (data.error || data.stderr || '') + '</small>';
                }
            })
            .catch(e => {
                status.className = 'status error';
                status.innerHTML = '❌ Error: ' + e.message;
            });
        }
        
        function resetForm() {
            document.querySelector('input[name="target"][value="rekordbox"]').checked = true;
            document.querySelector('input[name="selection"][value="all"]').checked = true;
            document.getElementById('sync-mode').checked = false;
            document.getElementById('dry-run').checked = false;
            document.getElementById('status').innerHTML = '';
            usbOptions.style.display = 'none';
        }
    </script>
</body>
</html>
"""

def main():
    port = 8080
    server = HTTPServer(('localhost', port), SyncHandler)
    
    print(f"🌐 Sync Master web UI")
    print(f"   Server: http://localhost:{port}")
    print(f"   Press Ctrl+C to stop\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped")

if __name__ == '__main__':
    main()
