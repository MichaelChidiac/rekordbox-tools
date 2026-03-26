# Planning & Execution Guide — Complete Workflow

This document ties together all the planning, organization, and parallelization guidelines.

## Quick Start: Planning a New Feature

### Step 1: Create Issue Folder
```bash
mkdir -p ".github/prompts/issue-[NUMBER]-[TITLE]"
cd ".github/prompts/issue-[NUMBER]-[TITLE]"
```

### Step 2: Create Planning Files
```bash
touch prompt.md plan.md agents.md acceptance-criteria.md notes.md
```

### Step 3: Fill Out Each File

**prompt.md** — Copy the original requirement
```markdown
# Issue Context

[User's original request verbatim]

## Goal
[What should be accomplished]
```

**plan.md** — Implementation strategy
```markdown
# Implementation Plan

## Approach
[High-level architecture]

## Changes Required
- Database: ...
- Backend: ...
- Frontend: ...
- Tests: ...
```

**agents.md** — Parallelization strategy ⭐ CRITICAL
```markdown
# Agent Dispatch Plan

## Phase 1: Backend (sequential start)
- [ ] migration agent — schema changes
- [ ] backend agent — services + routes

## Phase 2: UI + Tests (parallel, depends on Phase 1)
- [ ] frontend agent — templates + JS
- [ ] test-writer agent — unit + integration tests
```

See: `.github/skills/agents-md-spec.md` for full format

**acceptance-criteria.md** — What "done" looks like
```markdown
# Acceptance Criteria

- [ ] Feature works as described
- [ ] Tests pass: `[test command]`
- [ ] No regressions
- [ ] Documentation updated
- [ ] Code review approved
```

**notes.md** — Implementation decisions & blockers
```markdown
# Implementation Notes

## Decisions
- Decision 1: rationale

## Blockers
- Blocker 1: impact
```

---

## Step 4: Execute Based on agents.md

### If Sequential (A THEN B):
1. Dispatch **first agent** with complete context
2. Wait for completion
3. Dispatch **second agent**
4. Wait for completion
5. Collect results → commit

### If Parallel (A + B simultaneously):
1. Dispatch **agent A**
2. Dispatch **agent B** simultaneously
3. Wait for BOTH to complete
4. Verify no conflicts (git diff)
5. Collect results → commit

### If Highly Parallel (3+ independent agents):
1. Dispatch all agents simultaneously
2. Monitor SQL `todos` table for progress
3. Wait for all to complete
4. Verify no conflicts
5. Merge into atomic commits

### Using task-orchestrator (automated):
```
Claude: Use the task-orchestrator agent to orchestrate
        .github/prompts/issue-NNN-title/agents.md
```

---

## Step 5: When Completed

1. **Archive the planning folder:**
   ```bash
   # Option A: rename with _DONE suffix
   mv ".github/prompts/issue-NNN-title" \
      ".github/prompts/issue-NNN-title_DONE"
   
   # Option B: move to docs
   mv ".github/prompts/issue-NNN-title/plan.md" \
      "docs/implemented/[feature]-design.md"
   ```

2. **Update `docs/implemented/README.md`:**
   ```markdown
   | `[feature]-design.md` | ✅ Implemented | `[COMMIT-SHA]` |
   ```

3. **Commit everything:**
   ```bash
   git add -A
   git commit -m "feat: [feature] - description"
   ```

---

## Key Rules

✅ **DO:**
- Create `agents.md` for EVERY planning task
- Break work into independent chunks
- Dispatch parallel agents whenever possible
- Document dependencies clearly
- Use SQL `todos` table to track progress

❌ **DON'T:**
- Skip the `agents.md` file
- Parallelize work with tight coupling
- Let multiple agents edit the same file
- Dispatch without complete context
- Forget to archive completed planning docs

---

## Why This Matters

**Sequential (no parallelization):**
- Migration (1h) → Backend (2h) → Frontend (2h) → Tests (1h) = **6 hours**

**With Phase 2 parallelization:**
- Phase 1: Migration + Backend = 3 hours (sequential, blocking)
- Phase 2: Frontend + Tests + Mobile simultaneously = 2 hours (parallel)
- **Total: 5 hours** (17% faster)

**Maximum parallelization:**
- Phase 1: Migration alone = 1 hour
- Phase 2: Backend alone = 2 hours
- Phase 3: Frontend + Tests + Mobile simultaneously = 2 hours
- **Total: 5 hours** but agents are used more efficiently

The key is **identifying what can truly run in parallel** — documented in `agents.md`.

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `agents-md-spec.md` | agents.md format specification |
| `SMART-DISPATCH.md` | Auto-generate agents.md from plan.md |
| `QUALITY-GATES.md` | Phase quality checkpoints |
| `AUTO-DETECT-WORKFLOW.md` | Request type detection |
| `.github/agents/task-orchestrator.md` | Automated dispatch |
| `.github/prompts/issue-template.md` | GitHub issue format |
| `.github/prompts/AGENT-PARALLELIZATION-GUIDE.md` | Parallelization patterns |
