# Agent Parallelization Strategy

## Overview

Most features can be decomposed into independent tasks that multiple specialized agents
can execute **simultaneously**. This dramatically accelerates development.

## Core Principle

**Break work into independent chunks → Dispatch agents in parallel → Collect results**

Each agent works on its own file(s) without blocking others. Dependencies flow one direction only.

## Agent Types & Domains

| Agent | Domain | Typical Tasks | Typical Dependencies |
|-------|--------|---------------|---------------------|
| **backend** | Routes, models, services | Route handlers, business logic, DB queries | migration (if schema changed) |
| **frontend** | Templates, CSS, JS | Markup, interactivity, styling | backend routes ready |
| **test-writer** | Tests | Unit tests, integration tests | code under test ready |
| **migration** | Schema | Schema changes, data migrations | None (usually first) |
| **mobile-api** | Mobile endpoints | API routes, token auth | backend services ready |
| **refactor** | Structure | Module splits, service extraction | Nothing running in parallel |
| **pattern-enforcer** | Consistency | Bulk fixes across many files | Isolatable to one pattern |

## Dependency Graph Rules

```
ALWAYS SEQUENTIAL (blocking):
  migration → backend → frontend/mobile-api → test-writer

CAN BE PARALLEL (no blocking):
  backend + migration (independent schema)
  frontend + mobile-api (different files)
  frontend + test-writer (different concerns)
  pattern-enforcer (isolated to one pattern)
```

## Parallelization Patterns

### Pattern 1: Backend + Frontend (Classic)

**Scenario:** New feature requires service logic and UI.

```
┌─ Phase 1: Backend Infrastructure
│  └─ backend agent
│     └─ Create service + routes
│        └─ Blocks: frontend waiting for route definitions
│
└─ Phase 2: Frontend + Tests (parallel, depends on Phase 1)
   ├─ frontend agent
   │  └─ Create templates + JS interactions
   │
   └─ test-writer agent
      └─ Write service + route tests
```

**Dispatch:**
```
1. Task backend → wait for completion
2. Task frontend + Task test-writer simultaneously
3. Collect results
```

### Pattern 2: Full Stack with Mobile (3-way parallel)

**Scenario:** Same feature exposed via web UI AND mobile API.

```
┌─ Phase 1: Shared Service
│  └─ backend agent
│     └─ Create shared service
│        └─ Blocks: mobile, frontend, tests
│
└─ Phase 2: All consumers (parallel)
   ├─ mobile-api agent
   │  └─ Add /api/[feature] endpoint
   │
   ├─ frontend agent
   │  └─ Add web UI
   │
   └─ test-writer agent
      └─ Write tests for all endpoints
```

**Dispatch:**
```
1. Task backend → wait for completion
2. Task mobile-api + Task frontend + Task test-writer simultaneously
3. Collect results
```

### Pattern 3: Schema + Everything

**Scenario:** New feature requires DB schema changes.

```
┌─ Phase 1: Migration (creates schema)
│  └─ migration agent
│     └─ Add new tables/columns
│        └─ Blocks: backend code that uses those columns
│
└─ Phase 2: Backend (depends on Phase 1)
   └─ backend agent
      └─ Use new schema in service layer
         └─ Blocks: frontend + tests
```

**Dispatch:**
```
1. Task migration → wait for completion
2. Task backend → wait for completion
3. Task frontend + Task test-writer simultaneously
4. Collect results
```

### Pattern 4: Bulk Pattern Enforcement (Independent)

**Scenario:** Replace a deprecated pattern throughout codebase.

```
Split work by directory:
├─ pattern-enforcer (routes/)      ─┐
├─ pattern-enforcer (services/)     ├─ all simultaneously
└─ pattern-enforcer (models/)      ─┘
Each is independent, can run together.
```

**Dispatch:**
```
1. Task pattern-enforcer (routes)
2. Task pattern-enforcer (services)
3. Task pattern-enforcer (models)
   (all three simultaneously)
4. Collect + merge results
```

## Decision Tree: When to Parallelize

```
START: Do I have multiple independent tasks?
│
├─ YES: Do they touch the same file?
│       ├─ YES → Sequence them (one agent per file to avoid conflicts)
│       └─ NO → Parallelize! Dispatch simultaneously
│
└─ NO: Execute single agent sequentially
```

## When NOT to Parallelize

❌ **Schema conflicts:** Two migrations touching the same table
❌ **Tight coupling:** Service A depends on Service B being fully implemented first
❌ **Same file edits:** Two agents trying to edit the same file
❌ **Order-dependent logic:** Initialization steps that must happen in sequence

## Agent Coordination

When dispatching multiple agents simultaneously:

1. **Set SQL status to "in_progress"** for all tasks
   ```sql
   UPDATE todos SET status = 'in_progress' WHERE id IN ('backend-feature', 'frontend-feature');
   ```

2. **Provide complete context** in the prompt — agents are stateless
   - Reference the other agent's work
   - Link to the same architecture doc
   - Mention file paths clearly

3. **Collect results** when all agents complete
   - Use `read_agent()` to fetch outputs
   - Verify no conflicts (git diff)
   - Merge as one atomic commit if possible

4. **Update SQL status to "done"**
   ```sql
   UPDATE todos SET status = 'done' WHERE id IN ('backend-feature', 'frontend-feature');
   ```

## Example Prompt for Parallel Backend Task

```markdown
# Backend: [Feature] Service

**Context:** Part of a 3-parallel-agent task. See .github/prompts/issue-NNN-title/agents.md

**Parallel Agents:** frontend (template UI), mobile-api (read endpoint), test-writer (tests)

**Blocks:** All downstream agents wait for this to complete

**What to build:**
1. Create [services directory]/[feature]_service.py
   - create_item(name, data): returns ItemID
   - get_items(filters): returns list
   - update_item(id, data): returns updated item
   - delete_item(id): returns bool

2. Add routes in [routes directory]/[feature].py
   - POST /api/[feature] — create
   - GET /api/[feature] — list
   - PATCH /api/[feature]/<id> — update
   - DELETE /api/[feature]/<id> — delete

3. Add tests to tests/test_[feature]_service.py

**Files to create/modify:**
- [services directory]/[feature]_service.py (NEW)
- [routes directory]/[feature].py (NEW or EXTEND)
- tests/test_[feature]_service.py (NEW)

**Dependencies:**
- Migration DONE: New tables/columns exist
- See: [models directory]/[feature].py for schema

**What frontend will build on top of this:**
- Templates that call the API endpoints
- See: templates/[feature]/ (will be created simultaneously)
```

## Parallelization Checklist

- [ ] Break down the feature into independent tasks
- [ ] Identify which tasks can run simultaneously
- [ ] Map each task to a specialized agent
- [ ] Create `agents.md` documenting the plan
- [ ] Dispatch agents with complete context
- [ ] Monitor progress in SQL `todos` table
- [ ] Collect results when all complete
- [ ] Merge into atomic commit(s)
