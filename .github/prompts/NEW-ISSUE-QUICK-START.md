# New Issue Quick Start — rekordbox-tools

Paste this reference when creating a new feature/issue folder.

## 30-Second Checklist

```bash
# 1. Create folder
mkdir -p ".github/prompts/issue-NNN-[title]"

# 2. Create files
touch ".github/prompts/issue-NNN-[title]"/{prompt,plan,agents,acceptance-criteria,notes}.md

# 3. Fill in prompt.md (original request)
# 4. Fill in plan.md (flag high-risk files: collection.nml, master.db, exportLibrary.db)
# 5. Generate agents.md (ask AI to use SMART-DISPATCH)
# 6. Fill in acceptance-criteria.md

# 7. Dispatch
# Claude: Orchestrate .github/prompts/issue-NNN-[title]/agents.md
```

---

## agents.md Template for rekordbox-tools (copy-paste)

```markdown
# Agent Dispatch Plan

## Phase 1: Schema (if fingerprints.db changes needed)

- [ ] **migration agent** — Add [column/table] to fingerprints.db
  - Files: find_duplicates.py (schema init) or new migration script
  - Depends on: (none)
  - Blocks: scripts agent
  - Est time: 15 min

## Phase 2: Script Implementation

- [ ] **scripts agent** — [Feature] in [script].py
  - Files: [script].py
  - Depends on: migration agent (if schema changed)
  - Blocks: test-writer, pattern-enforcer
  - Est time: 30–60 min

## Phase 3: Tests + Quality (parallel)

- [ ] **test-writer agent** — pytest for [feature]
  - Files: tests/test_[feature].py
  - Depends on: scripts agent
  - Est time: 30 min

- [ ] **pattern-enforcer agent** — Verify [script].py compliance
  - Files: [script].py
  - Depends on: scripts agent
  - Est time: 15 min
```

---

## Acceptance Criteria Template for rekordbox-tools (copy-paste)

```markdown
# Acceptance Criteria: [Feature Name]

## Functional
- [ ] [Core behavior works as described]
- [ ] [Edge case handled]

## Safety
- [ ] --dry-run shows correct preview without modifying files
- [ ] Backup created before any master.db write (if applicable)
- [ ] collection.nml not modified directly (if NML write involved)

## Technical
- [ ] Tests pass: `python3.11 -m pytest tests/ -x`
- [ ] No regressions on existing CLI flags
- [ ] Syntax check: `python3.11 -m py_compile [script].py`
- [ ] SQLCipher: all 3 PRAGMAs set including legacy=4 (if SQLCipher used)
- [ ] masterPlaylists6.xml synced if playlists changed in master.db

## Human Validation
- [ ] Run --dry-run and verify output looks correct
- [ ] Close Traktor/Rekordbox and run the actual operation
- [ ] Verify result in Rekordbox or Traktor UI
```

---

## GitHub Issue Template for rekordbox-tools (copy-paste)

```markdown
## Summary
[One sentence]

## Context
- Script(s) affected: [list]
- High-risk files: collection.nml / master.db / exportLibrary.db (if any)
- Constraints:
  - Do not modify collection.nml directly (backup + write copy)
  - Close Traktor before testing NML reads
  - Close Rekordbox before testing master.db writes

## Acceptance Criteria
- [ ] [Core behavior works]
- [ ] --dry-run shows correct preview
- [ ] Backup created before master.db write (if applicable)
- [ ] Tests pass: `python3.11 -m pytest tests/ -x`
- [ ] No regressions on existing CLI flags
- [ ] `python3.11 -m py_compile [script].py` exits 0

## Implementation Notes
1. Safety safeguard: [what backup/dry-run is needed]
2. [Step-by-step approach]

## Out of Scope
- [Not covered by this issue]
```

---

## Quick Dispatch Phrases

```
"Plan [feature] using PLANNING-WORKFLOW-GUIDE"
"Generate agents.md from my plan using SMART-DISPATCH"
"Orchestrate .github/prompts/issue-NNN-title/agents.md"
"Use the scripts agent to [specific task]"
"Use the test-writer agent for [feature] coverage"
"Use the pattern-enforcer to verify [script].py"
"What's the status of issue-NNN?"
```
