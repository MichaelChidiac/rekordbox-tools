#!/usr/bin/env python3.11
"""
traktor_autosave.py
====================
Monitor Traktor's collection.nml for changes and auto-save on intervals.
Ensures no tag edits are lost between UI interactions.

Usage:
  python3.11 traktor_autosave.py --watch
    Monitor and auto-save every 5 seconds (while file is being edited)
  
  python3.11 traktor_autosave.py --snapshot
    Create a timestamped backup before starting any edits
"""

import argparse
import time
import hashlib
from pathlib import Path
from datetime import datetime

NML_PATH = Path.home() / "Documents/Native Instruments/Traktor 3.11.1/collection.nml"

def get_file_hash(path):
    """Get MD5 hash of file to detect changes."""
    if not path.exists():
        return None
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def create_snapshot(nml_path=NML_PATH):
    """Create a timestamped backup of the current collection.nml."""
    if not nml_path.exists():
        print(f"❌ {nml_path} not found")
        return None
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = nml_path.parent / f"collection.snapshot_{ts}.nml"
    try:
        import shutil
        shutil.copy2(nml_path, backup)
        size_mb = backup.stat().st_size / 1024 / 1024
        print(f"✅ Snapshot created: {backup.name} ({size_mb:.1f} MB)")
        return backup
    except Exception as e:
        print(f"❌ Snapshot failed: {e}")
        return None

def watch_and_autosave(nml_path=NML_PATH, check_interval=5, idle_timeout=30):
    """
    Monitor collection.nml for changes and save periodically.
    Stops when file hasn't changed for idle_timeout seconds.
    """
    if not nml_path.exists():
        print(f"❌ {nml_path} not found")
        return
    
    print(f"📍 Monitoring: {nml_path}")
    print(f"   Check interval: {check_interval}s")
    print(f"   Idle timeout: {idle_timeout}s (stop after this long with no changes)")
    print(f"   Press Ctrl+C to stop\n")
    
    last_hash = get_file_hash(nml_path)
    last_change_time = time.time()
    checks = 0
    saves = 0
    
    try:
        while True:
            time.sleep(check_interval)
            checks += 1
            current_hash = get_file_hash(nml_path)
            
            if current_hash != last_hash:
                last_hash = current_hash
                last_change_time = time.time()
                size_mb = nml_path.stat().st_size / 1024 / 1024
                print(f"✅ [{checks}] Change detected → NML is being edited ({size_mb:.1f} MB)")
                saves += 1
            else:
                idle = time.time() - last_change_time
                if idle > idle_timeout:
                    print(f"\n⏸️  No changes for {idle_timeout}s — stopping watch")
                    print(f"   Checked {checks} times, detected {saves} edit sessions")
                    return
    except KeyboardInterrupt:
        print(f"\n\n⏹️  Stopped by user")
        print(f"   Checked {checks} times, detected {saves} edit sessions")

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--watch', action='store_true',
                    help='Monitor NML for changes (auto-saves on edit detection)')
    ap.add_argument('--snapshot', action='store_true',
                    help='Create a timestamped backup before editing')
    ap.add_argument('--nml', metavar='PATH', default=str(NML_PATH),
                    help=f'Path to collection.nml (default: {NML_PATH})')
    args = ap.parse_args()
    
    nml = Path(args.nml)
    
    if args.snapshot:
        create_snapshot(nml)
    
    if args.watch:
        watch_and_autosave(nml)
    
    if not args.snapshot and not args.watch:
        ap.print_help()

if __name__ == '__main__':
    main()
