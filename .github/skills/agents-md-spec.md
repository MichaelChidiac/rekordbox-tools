# agents.md Specification

This document defines the structured format for `agents.md` files that describe
how to parallelize feature work across multiple specialized agents.

## Format

Create an `agents.md` file in your issue folder (`.github/prompts/issue-NNN-title/agents.md`)
with the following structure:

```markdown
# Agent Dispatch Plan

## Phase 1: Foundation (sequence blocking)

- [ ] **migration agent** — Add [feature] schema
  - Description: Create schema migration for [feature]
  - Files: migrations/versions/[filename]
  - Depends on: (none)
  - Blocks: backend agent (needs new schema)
  - Est time: 15 min

- [ ] **backend agent** — [Feature]Service + routes
  - Description: Create service layer and REST endpoints for [feature]
  - Files: [services directory]/feature_service.py, [routes directory]/feature.py
  - Depends on: migration agent
  - Blocks: frontend agent (needs routes), test-writer (needs services)
  - Est time: 45 min

## Phase 2: UI + Tests (parallel)

- [ ] **frontend agent** — [Feature] UI + interactions
  - Description: Create templates and interactive [feature] dashboard
  - Files: templates/feature/, static/js/feature/
  - Depends on: backend agent (routes must exist)
  - Blocks: none (independent)
  - Est time: 30 min

- [ ] **test-writer agent** — Test suite
  - Description: Unit tests for [Feature]Service, integration tests for routes
  - Files: tests/test_feature_service.py, tests/test_feature_routes.py
  - Depends on: backend agent (code to test)
  - Blocks: none (independent)
  - Est time: 30 min

- [ ] **mobile-api agent** — Mobile endpoint (optional)
  - Description: Add GET /api/[feature] for mobile
  - Files: [routes directory]/api/feature.py
  - Depends on: backend agent (service exists)
  - Blocks: none (independent)
  - Est time: 20 min

## Phase 3: Polish (conditional)

- [ ] **refactor agent** — Optimize large template (optional)
  - Description: Split template if > 500 lines
  - Files: templates/feature/
  - Depends on: frontend agent (UI must exist)
  - Blocks: none
  - Est time: 20 min
```

## YAML Alternative (for parsing)

If you prefer machine-readable format (for automation), use YAML:

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
          - "[services directory]/feature_service.py"
          - "[routes directory]/feature.py"
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
        task: "[Feature] UI + interactions"
        files:
          - templates/feature/
          - static/js/feature/
        depends_on:
          - backend
        blocks: []
        est_time_min: 30

      - agent: test_writer
        task: "Test suite"
        files:
          - tests/test_feature_service.py
          - tests/test_feature_routes.py
        depends_on:
          - backend
        blocks: []
        est_time_min: 30

      - agent: mobile_api
        task: "Mobile endpoint"
        files:
          - "[routes directory]/api/feature.py"
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
| `blocks` | list | ✅ | Which agents are waiting for this one (empty if none) |
| `est_time_min` | int | Optional | Estimated time in minutes |
| `optional` | bool | Optional | If true, can be skipped (default: false) |
| `condition` | string | Optional | Condition under which this agent runs |

## Validation Rules

Before dispatching:

- [ ] **No cycles:** Each agent lists its dependencies in `depends_on`. Build dependency graph; abort if cycle detected.
- [ ] **Correctness:** Every agent in `blocks` must list this agent in `depends_on`.
- [ ] **Phasing:** Phase N agents can depend on Phase N-1 agents (not Phase N agents).
- [ ] **Single start:** Exactly one agent has `depends_on: []` (the first).
- [ ] **Parallelizable:** Agents with same `depends_on` and no cross-blocks can run simultaneously.

## Example: Valid Dispatch Plan

```
Phase 1 (sequential):
  1. migration (depends: none) → wait
  2. backend (depends: migration) → wait

Phase 2 (parallel):
  3. frontend (depends: backend) ──┐
  4. test-writer (depends: backend) ├─→ wait for both
  5. mobile-api (depends: backend) ─┘
```

**Dependency graph:**
```
migration → backend → ├─ frontend
                      ├─ test-writer
                      └─ mobile-api
```

## SQL Todos Integration

The task-orchestrator agent will:

1. **Create todos** for each agent task:
   ```sql
   INSERT INTO todos (id, title, description, status) VALUES
     ('phase1-migration', 'Migration: add feature columns', '...', 'pending'),
     ('phase1-backend', 'Backend: FeatureService + routes', '...', 'pending');
   ```

2. **Create dependencies:**
   ```sql
   INSERT INTO todo_deps (todo_id, depends_on) VALUES
     ('phase1-backend', 'phase1-migration');
   ```

3. **Update as phases complete:**
   ```sql
   UPDATE todos SET status = 'in_progress' WHERE id = 'phase1-migration';
   -- agent runs --
   UPDATE todos SET status = 'done' WHERE id = 'phase1-migration';
   ```

4. **Report final status:**
   ```sql
   SELECT COUNT(*) FROM todos WHERE status = 'done' AND id LIKE 'phase%';
   -- Output: "5/5 tasks complete"
   ```

## References

- Task orchestrator agent: `.github/agents/task-orchestrator.md`
- Parallelization patterns: `.github/skills/SMART-DISPATCH.md`
- Planning workflow: `.github/skills/PLANNING-WORKFLOW-GUIDE.md`
- Quality gates: `.github/skills/QUALITY-GATES.md`
