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

**agents.md** — Parallelization strategy ⭐ **CRITICAL**
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
- [ ] Tests pass: `[TEST_COMMAND]`
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

### If Sequential (backend THEN frontend):
1. Dispatch **backend agent** with complete context
2. Wait for completion
3. Dispatch **frontend agent** (can now reference backend routes)
4. Wait for completion
5. Collect results → commit

### If Parallel (backend + frontend simultaneously):
1. Dispatch **backend agent**
2. Dispatch **frontend agent** simultaneously
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

**See:** `.github/skills/agents-md-spec.md` for detailed agent dispatch format

---

## Step 5: When Completed

1. **Archive the planning folder:**
   ```bash
   # Option A: rename with _DONE suffix
   mv ".github/prompts/issue-[NUMBER]-[TITLE]" \
      ".github/prompts/issue-[NUMBER]-[TITLE]_DONE"

   # Option B: move to docs
   mv ".github/prompts/issue-[NUMBER]-[TITLE]/plan.md" \
      "docs/implemented/[FEATURE]-design.md"
   ```

2. **Update `docs/implemented/README.md`:**
   ```markdown
   | `[FEATURE]-design.md` | ✅ Implemented | `[COMMIT-SHA]` |
   ```

3. **Commit everything:**
   ```bash
   git add -A
   git commit -m "feat: [FEATURE] - full description

   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
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
- Parallelize work that has tight coupling
- Let multiple agents edit the same file
- Dispatch without complete context
- Forget to move completed docs to `docs/implemented/`

---

## Example Workflow

<!-- CUSTOMIZE: Replace with an example feature from your project -->

```
USER REQUEST
  ↓
CREATE: .github/prompts/issue-256-notifications/
  ├─ prompt.md (original requirement)
  ├─ plan.md (architecture: models, services, UI)
  ├─ agents.md (parallelization: Phase 1 sequential, Phase 2 parallel)
  ├─ acceptance-criteria.md (testable completion)
  └─ notes.md (decisions, constraints)
  ↓
EXECUTE PHASE 1 (sequential):
  ├─ Task migration agent → NotificationTemplate + Notification models
  └─ Wait for completion
  ↓
EXECUTE PHASE 2 (parallel):
  ├─ Task backend agent → notification_service.py + routes
  ├─ Task frontend agent → notification UI + templates
  ├─ Task test-writer agent → service + route tests
  └─ Task mobile-api agent → GET /api/notifications endpoint
  ↓
Wait for all Phase 2 agents to complete
  ↓
VERIFY & COLLECT:
  ├─ Check git diff for conflicts
  ├─ Run tests: [TEST_COMMAND]
  └─ Create atomic commit
  ↓
ARCHIVE:
  ├─ Rename: issue-256-notifications → issue-256-notifications_DONE
  ├─ Move design doc → docs/implemented/notifications-design.md
  └─ Update docs/implemented/README.md
  ↓
COMMIT & CLOSE ISSUE
```

---

## Why This Matters

**Before parallelization:** Sequential execution = slow
- Migration (1h) → Backend (2h) → Frontend (2h) → Tests (1h) = **6 hours**

**With parallelization:** Independent tasks run together
- Phase 1: Migration (1h) + Backend (2h) = 2h (sequential, blocking)
- Phase 2: Frontend (2h) + Tests (1h) simultaneously = 2h (parallel)
- **Total: 4 hours** (33% faster)

**With maximum parallelization:** More independence
- Phase 1: Migration (1h) = 1h
- Phase 2: Backend (2h) = 2h
- Phase 3: Frontend (2h) + Tests (1h) + Mobile API (1h) = 2h (3-way parallel)
- **Total: 5 hours** (but agents are used more efficiently)

The key is **identifying what can truly run in parallel** — documented in `agents.md`.

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `agents-md-spec.md` | agents.md format specification |
| `SMART-DISPATCH.md` | Auto-generate agents.md from plan.md |
| `QUALITY-GATES.md` | Phase quality checkpoints |
| `AUTO-DETECT-WORKFLOW.md` | Request type detection |
| `REQUIREMENTS-INTAKE.md` | Raw requirements → auto-dispatch |
| `issue-planning.md` | Issue folder structure + GitHub issue format |
| `pr-preview.md` | PR preview deployment for manual testing |
| `.github/agents/task-orchestrator.md` | Automated dispatch |
| `.github/prompts/issue-template.md` | GitHub issue format |
