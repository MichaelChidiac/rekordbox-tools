# agents.md Specification

This document defines the structured format for `agents.md` files that describe
how to parallelize feature work across multiple specialized agents.

## Format

Create an `agents.md` file in your issue folder (`.github/prompts/issue-NNN-title/agents.md`)
with the following structure:

```markdown
# Agent Dispatch Plan

## Phase 1: Foundation (sequential)

- [ ] **migration agent** — Add [feature] schema
  - Description: Create schema migration
  - Files: migrations/versions/[filename]
  - Depends on: (none)
  - Blocks: backend agent
  - Est time: 15 min

- [ ] **backend agent** — [Feature]Service + routes
  - Description: Create service layer and REST endpoints
  - Files: src/services/feature_service.py, src/routes/feature.py
  - Depends on: migration agent
  - Blocks: frontend agent, test-writer
  - Est time: 45 min

## Phase 2: UI + Tests (parallel)

- [ ] **frontend agent** — [Feature] UI
  - Description: Create templates and interactive UI
  - Files: templates/feature/, static/js/feature/
  - Depends on: backend agent
  - Blocks: none
  - Est time: 30 min

- [ ] **test-writer agent** — Test suite
  - Description: Unit tests for service, integration tests for routes
  - Files: tests/test_feature_service.py, tests/test_feature_routes.py
  - Depends on: backend agent
  - Blocks: none
  - Est time: 30 min

- [ ] **mobile-api agent** — Mobile endpoint (optional)
  - Description: Add GET /api/[feature] for mobile
  - Files: src/routes/api/feature.py
  - Depends on: backend agent
  - Blocks: none
  - Est time: 20 min

## Phase 3: Polish (conditional)

- [ ] **refactor agent** — Optimize if needed (optional)
  - Depends on: frontend agent
  - Blocks: none
  - Est time: 20 min
  - Condition: only if template > 500 lines
```

## YAML Alternative (for parsing)

```yaml
phases:
  phase_1:
    name: "Foundation (sequential)"
    agents:
      - agent: migration
        task: "Add [feature] schema"
        files:
          - migrations/versions/feature_migration.py
        depends_on: []
        blocks:
          - backend
        est_time_min: 15

      - agent: backend
        task: "[Feature]Service + routes"
        files:
          - src/services/feature_service.py
          - src/routes/feature.py
        depends_on:
          - migration
        blocks:
          - frontend
          - test_writer
        est_time_min: 45

  phase_2:
    name: "UI + Tests (parallel)"
    agents:
      - agent: frontend
        task: "[Feature] UI"
        depends_on:
          - backend
        blocks: []
        est_time_min: 30

      - agent: test_writer
        task: "Test suite"
        depends_on:
          - backend
        blocks: []
        est_time_min: 30

      - agent: mobile_api
        task: "Mobile endpoint"
        depends_on:
          - backend
        blocks: []
        est_time_min: 20
        optional: true
```

## Required Fields

| Field | Type | Required? | Description |
|-------|------|-----------|-------------|
| `agent` | string | ✅ | Agent name: `backend`, `frontend`, `test-writer`, `migration`, `mobile-api`, `refactor`, `pattern-enforcer` |
| `task` | string | ✅ | One-liner: what this agent does |
| `description` | string | ✅ | Brief explanation |
| `files` | list | ✅ | Files created/modified |
| `depends_on` | list | ✅ | Which agents must complete first (empty if none) |
| `blocks` | list | ✅ | Which agents are waiting for this one |
| `est_time_min` | int | Optional | Estimated time in minutes |
| `optional` | bool | Optional | If true, can be skipped (default: false) |
| `condition` | string | Optional | Condition under which this agent runs |

## Validation Rules

Before dispatching:

- [ ] **No cycles:** Build dependency graph; abort if cycle detected.
- [ ] **Correctness:** Every agent in `blocks` must list this agent in `depends_on`.
- [ ] **Phasing:** Phase N agents can depend on Phase N-1 agents, not Phase N agents.
- [ ] **Parallelizable:** Agents with same `depends_on` and no cross-blocks can run simultaneously.

## Example: Valid Dispatch Plan

```
Phase 1 (sequential):
  1. migration (depends: none) → wait
  2. backend (depends: migration) → wait

Phase 2 (parallel):
  3. frontend (depends: backend) ──┐
  4. test-writer (depends: backend)├─→ wait for all
  5. mobile-api (depends: backend) ┘
```

**Dependency graph:**
```
migration → backend → ├─ frontend
                      ├─ test-writer
                      └─ mobile-api
```

## SQL Todos Integration

The task-orchestrator will:

1. **Create todos** for each agent task
2. **Create dependencies** in the `todo_deps` table
3. **Update status** as phases complete: `pending` → `in_progress` → `done`
4. **Report** final status with timing

## References

- Task orchestrator agent: `.github/agents/task-orchestrator.md`
- Parallelization patterns: `.github/prompts/AGENT-PARALLELIZATION-GUIDE.md`
- Planning workflow: `.github/skills/PLANNING-WORKFLOW-GUIDE.md`
