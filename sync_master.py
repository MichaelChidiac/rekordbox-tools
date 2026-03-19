#!/usr/bin/env python3.11
"""
sync_master.py
==============
Master sync tool — one command for all Traktor ↔ Rekordbox/USB operations.

Quick Start
-----------
  # Sync entire Traktor library to Rekordbox:
  python3.11 sync_master.py --to-rekordbox --all

  # Interactive: pick playlists to sync to USB:
  python3.11 sync_master.py --to-usb --select

  # Sync all to USB:
  python3.11 sync_master.py --to-usb --all

  # Incremental sync (only new/changed tracks):
  python3.11 sync_master.py --to-usb --all --sync

Operations
----------
  --to-rekordbox    Sync Traktor collection to Rekordbox (master.db)
  --to-usb          Export to Pioneer USB (CDJ-compatible)

Selection
---------
  --all             Sync entire library
  --select          Interactive checkbox UI (pick folders/playlists)
  --playlists NAME  Sync specific playlist(s) by name

USB Options
-----------
  --usb PATH        USB mount point (auto-detected if omitted)
  --sync            Incremental: only new/changed tracks (fast re-sync)
  --dry-run         Preview what would be synced without writing

Examples
--------
  # Sync entire library to Rekordbox:
  python3.11 sync_master.py --to-rekordbox --all

  # Pick playlists for USB export:
  python3.11 sync_master.py --to-usb --select /Volumes/MYUSB

  # Sync all to USB with incremental mode:
  python3.11 sync_master.py --to-usb --all --sync

  # Preview changes without writing:
  python3.11 sync_master.py --to-usb --all --dry-run
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Tool locations
TOOLS_DIR = Path(__file__).parent
TRAKTOR_TO_REKORDBOX = TOOLS_DIR / "traktor_to_rekordbox.py"
REBUILD_REKORDBOX = TOOLS_DIR / "rebuild_rekordbox_playlists.py"
TRAKTOR_TO_USB = TOOLS_DIR / "traktor_to_usb.py"

def run_tool(tool_path, args, description):
    """Run a Python tool with given arguments."""
    print(f"\n{'='*78}")
    print(f"  {description}")
    print(f"{'='*78}\n")
    
    cmd = [sys.executable, str(tool_path)] + args
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Operation failed with code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"❌ Tool not found: {tool_path}")
        return False

def sync_to_rekordbox(all_lib=False, playlists=None, dry_run=False):
    """Sync Traktor collection to Rekordbox."""
    print("\n📋 Step 1: Convert Traktor NML → Rekordbox XML")
    args = []
    if all_lib or not playlists:
        args.append("--all")
    if dry_run:
        args.append("--dry-run")
    
    if not run_tool(TRAKTOR_TO_REKORDBOX, args, "Converting Traktor to Rekordbox format"):
        return False
    
    print("\n📋 Step 2: Rebuild Rekordbox playlists")
    args = []
    if dry_run:
        args.append("--dry-run")
    
    if not run_tool(REBUILD_REKORDBOX, args, "Rebuilding Rekordbox playlists"):
        return False
    
    print("\n✅ Rekordbox sync complete!")
    return True

def sync_to_usb(all_lib=False, select=False, playlists=None, usb_path=None, 
                sync_mode=False, dry_run=False):
    """Sync to USB (CDJ-compatible export)."""
    args = []
    
    if all_lib:
        args.append("--all")
    elif select:
        args.append("--select")
    elif playlists:
        args.extend(["--playlists"] + playlists)
    else:
        args.append("--select")  # Default to interactive
    
    if usb_path:
        args.extend(["--usb", usb_path])
    
    if sync_mode:
        args.append("--sync")
    
    if dry_run:
        args.append("--dry-run")
    
    if not run_tool(TRAKTOR_TO_USB, args, "Exporting to USB (CDJ-compatible)"):
        return False
    
    print("\n✅ USB export complete!")
    return True

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Operation (required)
    op = ap.add_mutually_exclusive_group(required=True)
    op.add_argument('--to-rekordbox', action='store_true',
                    help='Sync Traktor collection to Rekordbox')
    op.add_argument('--to-usb', action='store_true',
                    help='Export to Pioneer USB (CDJ-compatible)')
    
    # Selection mode
    sel = ap.add_mutually_exclusive_group()
    sel.add_argument('--all', action='store_true',
                     help='Sync entire library')
    sel.add_argument('--select', action='store_true',
                     help='Interactive mode: pick playlists')
    sel.add_argument('--playlists', nargs='+', metavar='NAME',
                     help='Specific playlist names')
    
    # Options
    ap.add_argument('--usb', metavar='PATH',
                    help='USB mount point (auto-detected if omitted)')
    ap.add_argument('--sync', action='store_true',
                    help='Incremental sync (only new/changed tracks)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Preview without writing')
    
    args = ap.parse_args()
    
    # Default to --all if no selection specified
    if not args.all and not args.select and not args.playlists:
        args.all = True
    
    # Execute
    success = False
    if args.to_rekordbox:
        success = sync_to_rekordbox(
            all_lib=args.all,
            playlists=args.playlists,
            dry_run=args.dry_run
        )
    elif args.to_usb:
        success = sync_to_usb(
            all_lib=args.all,
            select=args.select,
            playlists=args.playlists,
            usb_path=args.usb,
            sync_mode=args.sync,
            dry_run=args.dry_run
        )
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
