# Quick Start Guide

> Full details in [README.md](README.md). This guide covers the most common tasks.

---

## First-time setup

```bash
pip3.11 install sqlcipher3 pyrekordbox questionary numpy tqdm
brew install chromaprint
cd ~/projects/rekordbox-tools && npm install rekordbox-parser
```

---

## I want to export music to a USB stick

**Plug in your USB, then:**

```bash
cd ~/projects/rekordbox-tools
python3.11 traktor_to_usb.py --select
```

A checkbox menu appears — pick the folders/playlists you want, hit **Enter**, and it copies everything (audio, waveforms, cue points). Works on CDJ-3000, XDJ-RX3, XDJ-XZ.

---

## I have a USB I always keep my full library on

**First time** (takes a while — copies all audio):
```bash
python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB
```

**Every time after** (only syncs what changed — fast):
```bash
python3.11 traktor_to_usb.py --all --usb /Volumes/MYUSB --sync
```

---

## I updated my Traktor library and want Rekordbox to reflect it

```bash
python3.11 traktor_to_rekordbox.py        # 1. convert Traktor → XML
python3.11 rebuild_rekordbox_playlists.py # 2. push into Rekordbox
# 3. Restart Rekordbox
```

> ⚠️ Close Traktor before step 1, close Rekordbox before step 2.

---

## I played a gig and want the history in Traktor

```bash
# See what history playlists are on the USB
node read_history.js --list

# Import one into Traktor
python3.11 pdb_to_traktor.py --playlist "HISTORY 008" --name "2026-03-14 Gig"
# Restart Traktor — new playlist appears automatically
```

---

## I want to check a USB is properly exported

```bash
node validate_usb.js        # checks all connected Pioneer USBs
```

---

## I want to find duplicate tracks in my library

```bash
# First run — fingerprints everything (~5 min), then shows report
python3.11 find_duplicates.py

# After that, re-run the report instantly (uses cache)
python3.11 find_duplicates.py --report-only

# Save report to a file
python3.11 find_duplicates.py --report-only --out duplicates.txt
```

The report shows three sections:
- **Exact duplicates** — same recording, different files → safe to delete the lower-quality one
- **Near duplicates** — same track, different format (e.g. WAV + MP3) → check before deleting
- **Metadata matches** — same Title + Artist → may be different versions, review manually

Each group marks a ✅ KEEP and ❌ REMOVE recommendation based on format quality and file size.

---

## Something looks wrong

| Symptom | Fix |
|---|---|
| Playlists missing in Rekordbox | Run `rebuild_rekordbox_playlists.py`, restart Rekordbox |
| USB export looks wrong | Run `node validate_usb.js /Volumes/MYUSB` |
| "No Pioneer USB detected" | Check `/Volumes/` — USB must have a `/PIONEER/` folder |
| Traktor NML not found | Close Traktor first, then re-run |
| `file is not a database` error | Make sure you're using `python3.11` (not `python3`) |
