# plan-to-tasks.md — Plan Decomposition Skill

## Purpose

Convert a design document or plan into a concrete, parallelized set of agent tasks
with `agents.md` ready for the task-orchestrator.

## When to Use

- You have a plan.md with architecture and task descriptions
- You want to identify which parts can run in parallel
- You need a structured agents.md for the orchestrator

**Trigger phrases:**
- "Break this plan into tasks"
- "Decompose plan.md into agents.md"
- "Create the parallelization plan for this feature"

---

## Step 1: Parse the Plan

Read plan.md and extract:
- [ ] Feature title and description
- [ ] Required changes (schema/DB, backend, frontend, tests, mobile)
- [ ] Constraints (what must be done first, what can run in parallel)
- [ ] Complexity estimate (1-10)

**Output:**
```
Parsed Plan:
  Title: [Feature Name]
  Complexity: [X]/10
  
  Tasks identified:
  - [ ] DB schema change (migration agent)
  - [ ] Service layer + routes (backend agent)
  - [ ] Templates + JS (frontend agent)
  - [ ] Tests (test-writer agent)
  - [ ] Mobile API (mobile-api agent) [optional]
  - [ ] Structural improvements (refactor agent) [optional]
```

---

## Step 2: Build Dependency Graph

For each task, determine:
- What must complete before this can start?
- What is waiting for this to complete?

**Standard rules:**
```
migration → backend → frontend
                   → test-writer
                   → mobile-api
```

**Exception rules:**
- If a task only changes config/docs: no dependencies
- If a task creates new independent modules: may not need migration
- If a refactor is purely structural: independent

---

## Step 3: Group Into Phases

```
Phase 1 (Sequential):
  Everything that is in the critical path
  Rule: migration must always be in Phase 1 if it exists

Phase 2 (Parallel):
  Everything that depends only on Phase 1 completion
  Rule: frontend + test-writer + mobile-api can all be in Phase 2

Phase 3 (Optional/Conditional):
  Quality improvements, refactoring, polish
  Rule: conditional on Phase 2 results (e.g., if coverage < threshold)
```

---

## Step 4: Estimate Timing

Apply timing estimates from `.github/skills/SMART-DISPATCH.md`:
- Score each task as simple/medium/complex
- Look up timing from the table
- Calculate sequential total and parallel total
- Compute savings

---

## Step 5: Generate agents.md

Write the complete agents.md file following `.github/skills/agents-md-spec.md`:

```markdown
# Agent Dispatch Plan

**Feature:** [Title]
**Complexity:** [X]/10
**Sequential time:** [N] min | **Parallel time:** [M] min | **Savings:** [S] min ([P]% faster)

## Phase 1: Foundation (sequential)

- [ ] **migration agent** — [task description]
  - Files: [list]
  - Depends on: (none)
  - Blocks: backend agent
  - Est time: [N] min

- [ ] **backend agent** — [task description]
  - Files: [list]
  - Depends on: migration agent
  - Blocks: frontend agent, test-writer, mobile-api
  - Est time: [N] min

## Phase 2: [Parallel description] (parallel)

- [ ] **frontend agent** — [task description]
  - Files: [list]
  - Depends on: backend agent
  - Blocks: none
  - Est time: [N] min

- [ ] **test-writer agent** — [task description]
  - Files: [list]
  - Depends on: backend agent
  - Blocks: none
  - Est time: [N] min
```

---

## Step 6: Quality Check

Before finalizing agents.md:

- [ ] Every agent has `depends_on` and `blocks` filled in
- [ ] No circular dependencies
- [ ] File paths are specific (not just "somewhere in src/")
- [ ] Time estimates are realistic
- [ ] Optional agents are marked `optional: true`
- [ ] Phase labels accurately describe the parallelization

---

## Step 7: Present for Approval

Show the generated agents.md and timing analysis:

```
📊 Plan Analysis Complete

Feature: [Name]
Complexity: [X]/10

Phases:
  Phase 1 (Sequential): [N agents, M min total]
  Phase 2 (Parallel): [N agents, M min total]

Timeline:
  Sequential: [X] min
  Parallel:   [Y] min
  Savings:    [Z] min ([P]% faster)

Risk: [LOW/MEDIUM/HIGH]
  - [Risk detail if any]

Generated agents.md saved to:
  .github/prompts/issue-NNN-[title]/agents.md

Ready to dispatch? Say "yes" to invoke task-orchestrator.
```

---

## Output: Acceptance Criteria Template

Also generate `acceptance-criteria.md`:

```markdown
# Acceptance Criteria: [Feature Name]

## Functional
- [ ] [Core feature behavior works]
- [ ] [Edge case handled]

## Technical
- [ ] Tests pass: `[test command]`
- [ ] No regressions in existing tests
- [ ] Coverage: [threshold]%+

## Quality
- [ ] All new routes have docstrings
- [ ] No new lint errors
- [ ] Migration valid (upgrade + downgrade tested)

## Human Validation (if UI changes)
- [ ] [Page/flow to test manually]
- [ ] Mobile layout verified
- [ ] Role-specific access verified
```
