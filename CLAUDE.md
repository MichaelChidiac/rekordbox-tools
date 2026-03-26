# rekordbox-tools — Claude/Copilot Entry Point

This file is the entry point for AI coding agents (Claude, GitHub Copilot).

## Code Exploration (jCodemunch MCP)

This project uses the **jCodemunch MCP** server for symbol-level codebase retrieval.
Prefer these tools over Read/Grep/Glob/Bash for code exploration:

| Task | Tool |
|------|------|
| First time in a session | `resolve_repo` → if not indexed, `index_folder` |
| Browse file structure | `get_file_tree` |
| Understand a file | `get_file_outline` |
| Find a function/class | `search_symbols` |
| Full-text search | `search_text` |
| Read a specific symbol | `get_symbol_source` |
| Impact of a change | `get_blast_radius` |

## Framework Submodule

Generic agents/skills/prompts/instructions live in the `copilot-agent-framework/` submodule
(`https://github.com/MichaelChidiac/copilot-agent-framework`).

**To pull the latest framework updates:**
```bash
git submodule update --remote copilot-agent-framework
```
The Claude Code hook auto-detects the SHA change and syncs `.github/` on the next Bash command.

**Protected files** (project-specific, never overwritten by the sync):
- `.github/copilot-instructions.md`
- `.github/agents/backend.md`
- `.github/agents/migration.md`
- `.github/instructions/database-rules.md`
- `.github/instructions/service-layer-rules.md`
- `.github/skills/SYNC-TO-FRAMEWORK.md`

## Project

Python script toolkit for managing DJ libraries across Traktor, Rekordbox, and Pioneer USB drives.

**macOS only.** No web framework, no ORM, no server.

## Quick Reference

| File | AI Instructions |
|------|----------------|
| `.github/copilot-instructions.md` | **Full project context** — read this first |
| `.github/instructions/database-rules.md` | SQLCipher + sqlite3 patterns |
| `.github/instructions/service-layer-rules.md` | Script structure rules |
| `.github/instructions/api-response-rules.md` | Console output rules |
| `.github/agents/backend.md` | Scripts agent (Python, SQLCipher, XML) |
| `.github/agents/test-writer.md` | Test writer agent |
| `.github/agents/migration.md` | DB schema agent |
| `.github/agents/refactor.md` | Refactor agent |
| `.github/agents/pattern-enforcer.md` | Pattern enforcement |
| `.github/agents/planner.md` | Feature planning |
| `.github/agents/task-orchestrator.md` | Orchestrate parallel agents |

## ⚠️ Critical Safety Rules (memorize these)

1. **NEVER modify `collection.nml` directly** — always create timestamped backup + write to copy
2. **Always `--dry-run`** before applying to `master.db` or USB drives
3. **Always backup `master.db`** before any write (`backup_master_db()`)
4. **Close Traktor** before reading `collection.nml`
5. **Close Rekordbox** before writing to `master.db`
6. **Never hardcode the SQLCipher key** — use `SQLCIPHER_KEY` constant

## SQLCipher Pattern (always set all 3 PRAGMAs)

```python
con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")
con.execute("PRAGMA cipher='sqlcipher'")
con.execute("PRAGMA legacy=4")  # CRITICAL — without this: "file is not a database"
```

## Common Commands

```bash
# Syntax check all scripts
python3.11 -m py_compile traktor_to_rekordbox.py rebuild_rekordbox_playlists.py \
  cleanup_rekordbox_db.py traktor_to_usb.py sync_master.py pdb_to_traktor.py find_duplicates.py

# Run tests (when they exist)
python3.11 -m pytest tests/ -x --tb=short -q

# Dry-run any write script before applying
python3.11 rebuild_rekordbox_playlists.py --dry-run
python3.11 cleanup_rekordbox_db.py --dry-run
python3.11 traktor_to_usb.py --dry-run

# Install dependencies
pip3.11 install sqlcipher3 pyrekordbox questionary numpy tqdm
brew install chromaprint
npm install  # for read_history.js, validate_usb.js
```

## Scripts

| Script | Purpose |
|--------|---------|
| `traktor_to_rekordbox.py` | Convert Traktor NML → Rekordbox XML |
| `rebuild_rekordbox_playlists.py` | Wipe + rebuild all playlists in master.db |
| `cleanup_rekordbox_db.py` | Incremental sync — add missing playlists/tracks |
| `traktor_to_usb.py` | Export library directly to Pioneer USB |
| `sync_master.py` | Master CLI — orchestrates all operations |
| `pdb_to_traktor.py` | Import USB HISTORY into Traktor NML |
| `find_duplicates.py` | Detect duplicate tracks (Chromaprint) |
| `read_history.js` | Read HISTORY playlists from Pioneer USB (Node.js) |
| `validate_usb.js` | Validate Pioneer USB structure (Node.js) |

## Key File Paths

| File | Path |
|------|------|
| Rekordbox main DB | `~/Library/Pioneer/rekordbox/master.db` |
| Rekordbox playlist manifest | `~/Library/Pioneer/rekordbox/masterPlaylists6.xml` |
| Traktor collection | `~/Documents/Native Instruments/Traktor 3.11.1/collection.nml` |
| Fingerprint cache | `fingerprints.db` (project root, plain sqlite3) |
