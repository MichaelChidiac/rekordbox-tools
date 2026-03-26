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
  frontend + mobile-api (different files)
  frontend + test-writer (different concerns)
  pattern-enforcer (isolated to one pattern)
```

## Parallelization Patterns

### Pattern 1: Backend + Frontend (Classic)

**Scenario:** New feature requires service logic and UI.

```
Phase 1: Backend Infrastructure
└─ backend agent: Create service + routes
   └─ Blocks: frontend (waiting for route definitions)

Phase 2: Frontend + Tests (parallel, depends on Phase 1)
├─ frontend agent: Create templates + JS interactions
└─ test-writer agent: Write service + route tests
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
Phase 1: Shared Service
└─ backend agent: Create shared service
   └─ Blocks: mobile, frontend, tests

Phase 2: All consumers (parallel)
├─ mobile-api agent: Add /api/[feature] endpoint
├─ frontend agent: Add web UI
└─ test-writer agent: Write tests for all
```

### Pattern 3: Schema + Everything

**Scenario:** New feature requires DB schema changes.

```
Phase 1: Schema
└─ migration agent: Add new table/columns
   └─ Blocks: backend

Phase 2: Backend
└─ backend agent: Use new schema in service layer
   └─ Blocks: frontend + tests

Phase 3: UI + Tests (parallel)
├─ frontend agent: Build UI
└─ test-writer agent: Write tests
```

### Pattern 4: Bulk Pattern Enforcement

**Scenario:** Replace a deprecated pattern throughout codebase.

```
Split work by directory:
├─ pattern-enforcer (routes/)      ─┐
├─ pattern-enforcer (services/)     ├─ all simultaneously
└─ pattern-enforcer (models/)      ─┘
Each is independent, can run together.
```

## Decision Tree: When to Parallelize

```
Do I have multiple independent tasks?
│
├─ YES: Do they touch the same file?
│       ├─ YES → Sequence them (one agent per file)
│       └─ NO → Parallelize! Dispatch simultaneously
│
└─ NO: Execute single agent sequentially
```

## When NOT to Parallelize

❌ **Schema conflicts:** Two migrations touching the same table
❌ **Tight coupling:** Service A depends on Service B being complete
❌ **Same file edits:** Two agents editing the same file
❌ **Order-dependent:** Initialization that must happen in sequence

## Agent Coordination

When dispatching multiple agents simultaneously:

1. **Set SQL status to "in_progress"** for all tasks
2. **Provide complete context** in each prompt (agents are stateless)
3. **Reference the shared architecture** in each prompt
4. **Collect results** when all agents complete
5. **Verify no conflicts** (git diff)
6. **Update SQL status to "done"**

## Parallelization Checklist

- [ ] Break the feature into independent tasks
- [ ] Identify which tasks can run simultaneously
- [ ] Map each task to a specialized agent
- [ ] Create `agents.md` documenting the plan
- [ ] Dispatch agents with complete context
- [ ] Monitor progress in SQL `todos` table
- [ ] Collect results when all complete
- [ ] Merge into atomic commit(s)
