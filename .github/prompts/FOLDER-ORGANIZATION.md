# Prompts Directory Organization Guide — rekordbox-tools

This directory contains planning documents, issue templates, and prompt context for features and tasks.

## Folder Structure

For each new issue or feature being planned, create an organized folder:

```
.github/prompts/
├── issue-[NUMBER]-[TITLE]/                # New issue/feature folder
│   ├── prompt.md                          # Original request (user context, verbatim)
│   ├── plan.md                            # Implementation plan & architecture
│   ├── agents.md                          # Agent parallelization strategy
│   ├── acceptance-criteria.md             # Testable completion checklist
│   └── notes.md                           # Implementation notes, decisions, blockers
│
├── AGENT-PARALLELIZATION-GUIDE.md         # Guide for parallel agent execution
├── FOLDER-ORGANIZATION.md                 # (This file)
└── NEW-ISSUE-QUICK-START.md               # Quick reference for new folders
```

## Workflow

### Creating a New Issue Folder

1. **When planning** a new feature/task:
   ```bash
   mkdir -p ".github/prompts/issue-NNN-descriptive-title"
   ```

2. **Create the planning files:**
   ```bash
   cd ".github/prompts/issue-NNN-descriptive-title"
   touch prompt.md plan.md agents.md acceptance-criteria.md notes.md
   ```

3. **Fill in each file:**

   **prompt.md** — Copy the original user request verbatim:
   ```markdown
   # Issue Context

   [Paste the original requirement here]

   ## Goal
   [What should be accomplished]
   ```

   **plan.md** — Write the implementation strategy:
   ```markdown
   # Implementation Plan

   ## High-Risk Files Touched
   - [ ] collection.nml — [yes/no] — if yes: backup + write copy only
   - [ ] master.db — [yes/no] — if yes: backup before write + dry-run first
   - [ ] exportLibrary.db — [yes/no] — if yes: dry-run first
   - [ ] masterPlaylists6.xml — [yes/no] — if yes: sync with DB changes

   ## Approach
   [High-level strategy]

   ## Changes Required
   - Scripts: [which scripts change]
   - Database: [fingerprints.db changes, master.db read/write]
   - CLI: [new flags]
   - Tests: [what to test]
   ```

   **agents.md** — Document agent parallelization strategy:
   See `.github/skills/agents-md-spec.md` for format, or use SMART-DISPATCH to auto-generate.

   **acceptance-criteria.md** — Define testable criteria:
   ```markdown
   # Acceptance Criteria

   - [ ] Feature works as described
   - [ ] --dry-run shows correct preview without modifying files
   - [ ] Backup created before any master.db write
   - [ ] Tests pass: `python3.11 -m pytest tests/ -x`
   - [ ] No regressions on existing CLI flags
   - [ ] python3.11 -m py_compile [script].py exits 0
   ```

4. **Execute the plan:**

   Option A — Manual dispatch:
   ```
   Use the scripts agent to [task from agents.md]
   ```

   Option B — Automated orchestration:
   ```
   Orchestrate .github/prompts/issue-NNN-title/agents.md
   ```

5. **When completed:**
   ```bash
   # Option A: Add _DONE suffix
   mv ".github/prompts/issue-NNN-title" ".github/prompts/issue-NNN-title_DONE"

   # Option B: Move design to docs
   mv ".github/prompts/issue-NNN-title/plan.md" "docs/implemented/[feature]-design.md"
   ```

## Best Practices

- **Use descriptive folder names:** `issue-12-usb-history-import` (not `feature-1`)
- **Always flag high-risk files:** `collection.nml`, `master.db`, `exportLibrary.db`
- **Always create `agents.md`:** Even for simple features — documents intent
- **Archive completed work:** Rename with `_DONE` suffix or move to `docs/implemented/`
- **Link back:** Reference the GitHub issue number, commit SHA, and PR number once implemented

## Example Structure

```
.github/prompts/issue-12-usb-history-import/
├── prompt.md           # "Import USB HISTORY playlist into Traktor NML"
├── plan.md             # High-risk: collection.nml (backup + write copy), NML parser
├── agents.md           # Phase 1 (scripts), Phase 2 (test-writer + pattern-enforcer)
├── acceptance-criteria.md
└── notes.md            # "pdb_to_traktor.py already has backup logic — reuse it"

AFTER COMPLETION:
docs/implemented/
├── design-usb-history-import.md   # Finalized design
└── README.md                      # Master index
```
