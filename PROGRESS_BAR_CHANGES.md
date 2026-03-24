# Progress Bar & Cancel Support - UI Enhancements

## Summary

Added real-time progress tracking and cancellation support to the web UI (`sync_web.py`). Users now see a proper progress bar with percentage and can cancel long-running sync operations.

## Changes Made

### 1. Backend (Python)

**New imports:**
- `threading` — Run sync operations in background threads
- `signal`, `time` — For process management

**New global state:**
```python
ACTIVE_SYNCS = {}      # Dict tracking all active sync operations
SYNC_LOCK = threading.Lock()  # Thread-safe access to ACTIVE_SYNCS
```

**New endpoints:**

- `/api/sync-progress?id=<sync_id>` (GET)
  - Returns current progress: `{running, percent, label, details}`
  - Client polls this every 500ms during sync

- `/api/cancel-sync` (POST)
  - Accepts `{id: sync_id}`
  - Terminates the running subprocess

**Updated `execute_sync()` method:**
- Now runs sync in a background thread instead of blocking
- Returns immediately with sync_id for progress polling
- Parses output in real-time looking for progress patterns like "123/456 tracks"
- Updates ACTIVE_SYNCS dict with:
  - `percent`: Progress percentage (0-100)
  - `label`: Current operation label
  - `details`: "X/Y tracks processed"
  - `running`: Boolean flag
  - `process`: Reference to subprocess (for cancellation)
  - `cancelled`: Set to True if user cancels

### 2. Frontend (HTML/CSS/JavaScript)

**New CSS:**
```css
.btn-cancel { background: #d32f2f; color: #fff; }
#progress-container { /* Progress bar display */ }
#progress-bar { /* Animated bar filling 0-100% */ }
```

**New HTML elements:**
- `#progress-container` — Shows during sync with real progress bar
- `#progress-bar` — Animated bar (width = percent)
- `#progress-percent` — Shows "42%" etc
- `#progress-label` — "Syncing tracks..." etc
- `#progress-details` — "123/456 tracks processed"
- `#cancel-btn` — Red cancel button (hidden during idle)

**Updated JavaScript:**

- `currentSyncId` — Stores current sync operation ID
- `progressUpdateInterval` — Handle for progress polling interval

- `startSync()` — Now:
  - Generates unique sync ID
  - Shows progress UI instead of animated indeterminate bar
  - Disables Sync button, shows Cancel button
  - Calls `startProgressPolling()` to fetch progress every 500ms
  - Hides progress UI when sync completes

- `startProgressPolling()` — New function
  - Polls `/api/sync-progress` every 500ms
  - Updates progress bar width, percentage, label, details

- `stopProgressPolling()` — New function
  - Stops polling interval
  - Clears currentSyncId

- `cancelSync()` — New function
  - POSTs to `/api/cancel-sync` with current sync_id
  - Hides progress UI
  - Shows "⏹ Sync cancelled" message

### 3. Progress Pattern Detection

The backend looks for progress in output using regex:
```python
match = re.search(r'(\d+)/(\d+)', line)
```

For best results, sync scripts should output lines like:
```
Synced 123 of 456 tracks...
Processed 456/1200 files
```

Any line with the pattern `NUMBER/NUMBER` will be detected as progress.

## Usage

1. Open `http://localhost:8080` in browser
2. Click "Sync to USB" — progress bar appears
3. See real-time progress percentage and track count
4. Click "⏹ Cancel" to stop the operation anytime
5. After completion, bar shows 100% and shows success/error message

## Backward Compatibility

- If sync scripts don't output progress patterns, the bar stays at 0%
- Cancel button only appears during actual sync
- All existing functionality preserved

## Files Modified

- `/Users/chidiacm/projects/rekordbox-tools/sync_web.py` — All changes

## Testing

Start the server:
```bash
cd ~/projects/rekordbox-tools
python3.11 sync_web.py
```

Open `http://localhost:8080` and run any sync operation.
