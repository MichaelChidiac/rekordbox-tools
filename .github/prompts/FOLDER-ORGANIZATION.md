# Prompts Directory Organization Guide

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
│   ├── generated-issue.md                 # GitHub issue template (if delegating to AI)
│   └── notes.md                           # Implementation notes, decisions, blockers
│
├── issue-template.md                      # (Master template — do not move/edit)
├── current-task.md                        # (Active task context — updated per session)
├── FOLDER-ORGANIZATION.md                 # (This file)
├── AGENT-PARALLELIZATION-GUIDE.md         # (Guide for parallel agent execution)
└── NEW-ISSUE-QUICK-START.md               # (Quick reference for new folders)
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

   ## Approach
   [High-level architecture / approach]

   ## Changes Required
   - Database: [schema changes]
   - Backend: [service/route changes]
   - Frontend: [UI changes]
   - Tests: [test coverage needed]
   ```

   **agents.md** — Document agent parallelization strategy:
   See `.github/skills/agents-md-spec.md` for format, or use SMART-DISPATCH to auto-generate.

   **acceptance-criteria.md** — Define testable criteria:
   ```markdown
   # Acceptance Criteria

   - [ ] Feature works as described
   - [ ] Tests pass: `[test command]`
   - [ ] No regressions
   - [ ] Documentation updated
   ```

4. **Execute the plan:**

   Option A — Manual dispatch:
   ```
   Use the backend agent to [task from agents.md]
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

   Update `docs/implemented/README.md` with the commit SHA and PR number.

<!-- CUSTOMIZE: Remove or replace the example below with one from your project -->

## Existing Files

| File | Purpose | Maintain? |
|------|---------|-----------|
| `issue-template.md` | Master template for GitHub issues | ✅ Yes — do not move |
| `current-task.md` | Context for active session work | ✅ Yes — update per session |

## Best Practices

- **Use descriptive folder names:** `issue-142-user-notifications` (not `feature-1`)
- **Keep everything in one place:** Don't scatter planning files across multiple directories
- **Always create `agents.md`:** Even for simple features — it documents intent and parallelization strategy (see AGENT-PARALLELIZATION-GUIDE.md)
- **Archive completed work:** Move finalized designs to `docs/implemented/`
- **Link back:** In prompts folders, always reference the GitHub issue number, commit SHA, and PR number once implemented
- **Reuse structure:** When creating a new feature, follow this folder template

## Example Structure

```
.github/prompts/issue-256-checklist-feature/
├── prompt.md           # "Add checklist templates + event checklists"
├── plan.md             # Models, service layer, UI architecture
├── agents.md           # Phase 1 (migration→backend), Phase 2 (frontend+tests)
├── acceptance-criteria.md
└── notes.md            # "Using JSON for task storage, not separate rows"

AFTER COMPLETION:
docs/implemented/
├── design-checklist-feature.md    # Finalized design (moved from prompts)
├── related-commits.txt            # f99bc74, 140d557
└── README.md                      # Master index
```
