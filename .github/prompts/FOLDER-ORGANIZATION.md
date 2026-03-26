# Prompts Directory Organization Guide

This directory contains planning documents, issue templates, and context for features and tasks.

## Folder Structure

```
.github/prompts/
├── issue-[NUMBER]-[TITLE]/           # One folder per feature/issue
│   ├── prompt.md                     # Original request (user context, verbatim)
│   ├── plan.md                       # Implementation plan & architecture
│   ├── agents.md                     # Agent parallelization strategy
│   ├── acceptance-criteria.md        # Testable completion checklist
│   ├── generated-issue.md            # GitHub issue template (if delegating to AI)
│   └── notes.md                      # Implementation notes, decisions, blockers
│
├── issue-template.md                 # Master template — do not move
├── AGENT-PARALLELIZATION-GUIDE.md    # Parallelization patterns guide
├── FOLDER-ORGANIZATION.md            # This file
└── NEW-ISSUE-QUICK-START.md          # Quick start reference
```

## Creating a New Issue Folder

### Step 1: Create the folder
```bash
mkdir -p ".github/prompts/issue-NNN-descriptive-title"
```

### Step 2: Create planning files
```bash
cd ".github/prompts/issue-NNN-descriptive-title"
touch prompt.md plan.md agents.md acceptance-criteria.md notes.md
```

### Step 3: Fill in each file

**prompt.md** — The original user request, verbatim:
```markdown
# Issue Context

[Paste the original requirement here]

## Goal
[What should be accomplished]
```

**plan.md** — Your implementation strategy:
```markdown
# Implementation Plan

## Approach
[High-level architecture / approach]

## Changes Required
- Database: [schema changes]
- Backend: [service/route changes]
- Frontend: [UI changes]
- Tests: [test coverage needed]
```

**agents.md** — Parallelization strategy:
See `.github/skills/agents-md-spec.md` for format, or use SMART-DISPATCH to auto-generate.

**acceptance-criteria.md** — Definition of done:
```markdown
# Acceptance Criteria

- [ ] Feature works as described
- [ ] Tests pass: `[test command]`
- [ ] No regressions
- [ ] Documentation updated
```

### Step 4: Execute

Option A — Manual dispatch:
```
Claude: Use the backend agent to [task from agents.md]
```

Option B — Automated orchestration:
```
Claude: Orchestrate .github/prompts/issue-NNN-title/agents.md
```

### Step 5: Archive when complete

```bash
# Option A: Add _DONE suffix
mv ".github/prompts/issue-NNN-title" ".github/prompts/issue-NNN-title_DONE"

# Option B: Move design to docs
mv ".github/prompts/issue-NNN-title/plan.md" "docs/implemented/[feature]-design.md"
```

Update `docs/implemented/README.md` with the commit SHA and PR number.

## Best Practices

- **Use descriptive names:** `issue-142-user-notifications` (not `feature-1`)
- **Keep everything in one place:** Don't scatter planning files
- **Always create `agents.md`:** Even for simple features — it documents intent
- **Archive completed work:** Move finalized designs to `docs/implemented/`
- **Link back:** Reference the GitHub issue number, commit SHA, and PR number

## Example Structure

```
.github/prompts/issue-256-checklist-feature/
├── prompt.md           # "Add checklist templates + event checklists"
├── plan.md             # Models, service layer, UI architecture
├── agents.md           # Phase 1 (migration→backend), Phase 2 (frontend+tests)
├── acceptance-criteria.md
└── notes.md            # "Using JSON for task storage, not separate rows"
```
