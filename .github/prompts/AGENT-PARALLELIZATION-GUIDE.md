# Agent Parallelization Strategy — rekordbox-tools

## Overview

Most rekordbox-tools features can be decomposed into independent tasks that multiple specialized agents can execute **simultaneously**. This dramatically accelerates development.

## Core Principle

**Break work into independent chunks → Dispatch agents in parallel → Collect results**

Each agent works on its own file(s) without blocking others. Dependencies flow one direction only.

## Agent Types & Domains

| Agent | Domain | Typical Tasks | Typical Dependencies |
|-------|--------|---------------|---------------------|
| **scripts** | Python scripts | SQLCipher queries, XML transforms, USB export | migration (if schema changed) |
| **test-writer** | Tests | pytest unit tests | scripts agent (code under test ready) |
| **migration** | Schema | fingerprints.db changes | None (usually first) |
| **refactor** | Structure | Extract shared utils, split large scripts | Nothing running in parallel |
| **pattern-enforcer** | Consistency | Fix PRAGMA violations, missing --dry-run, etc. | Isolatable to one script |

**Note:** There is no frontend/mobile-api/backend split in rekordbox-tools. All work is Python scripts or Node.js utilities.

## Dependency Graph Rules

```
ALWAYS SEQUENTIAL (blocking):
  migration → scripts agent → test-writer

CAN BE PARALLEL (no blocking):
  scripts agent + pattern-enforcer (different files)
  test-writer + pattern-enforcer (different concerns)
  multiple pattern-enforcer instances (different scripts)
```

## Parallelization Patterns

### Pattern 1: Script + Tests (Classic)

**Scenario:** New script feature with unit tests.

```
┌─ Phase 1: Script Implementation
│  └─ scripts agent
│     └─ Implement [feature] in [script].py
│        └─ Blocks: test-writer waiting for implementation
│
└─ Phase 2: Tests + Pattern Check (parallel)
   ├─ test-writer agent
   │  └─ Write pytest tests for [feature]
   │
   └─ pattern-enforcer agent
      └─ Verify [script].py follows all patterns
```

**Dispatch:**
```
1. Task scripts agent → wait for completion
2. Task test-writer + Task pattern-enforcer simultaneously
3. Collect results
```

### Pattern 2: Schema + Script + Tests (3-phase)

**Scenario:** New feature requiring fingerprints.db schema change.

```
┌─ Phase 1: Schema
│  └─ migration agent
│     └─ Add column/table to fingerprints.db
│        └─ Blocks: scripts agent
│
├─ Phase 2: Implementation
│  └─ scripts agent
│     └─ Use new schema in find_duplicates.py
│        └─ Blocks: test-writer
│
└─ Phase 3: Tests + Quality (parallel)
   ├─ test-writer agent
   │  └─ Write tests
   │
   └─ pattern-enforcer agent
      └─ Verify compliance
```

**Dispatch:**
```
1. Task migration agent → wait for completion
2. Task scripts agent → wait for completion
3. Task test-writer + Task pattern-enforcer simultaneously
4. Collect results
```

### Pattern 3: Bulk Pattern Enforcement (Independent)

**Scenario:** Fix missing `PRAGMA legacy=4` across all scripts.

```
Split work by script:
├─ pattern-enforcer (traktor_to_rekordbox.py)       ─┐
├─ pattern-enforcer (rebuild_rekordbox_playlists.py)  ├─ all simultaneously
└─ pattern-enforcer (cleanup_rekordbox_db.py)        ─┘
Each is independent, can run together.
```

**Dispatch:**
```
1. Task pattern-enforcer (traktor_to_rekordbox.py)
2. Task pattern-enforcer (rebuild_rekordbox_playlists.py)
3. Task pattern-enforcer (cleanup_rekordbox_db.py)
   (all three simultaneously)
4. Collect + verify
```

### Pattern 4: Refactor → Tests

**Scenario:** Extract SQLCipher connection to `utils/db.py`, then update tests.

```
1. Task refactor agent → Extract to utils/db.py
2. Task test-writer → Update imports, add utils tests
   (sequential — test-writer needs refactor to be done)
```

## Decision Tree: When to Parallelize

```
START: Do I have multiple independent tasks?
│
├─ YES: Do they touch the same file?
│       ├─ YES → Sequence them
│       └─ NO → Parallelize!
│
└─ NO: Execute single agent sequentially
```

## When NOT to Parallelize

❌ **Same script edits:** Two agents editing the same `.py` file
❌ **Tight coupling:** script agent depends on migration agent completing first
❌ **Order-dependent:** backup utilities must exist before scripts that use them

## Agent Coordination

When dispatching multiple agents simultaneously:

1. **Set SQL status to "in_progress"** for all tasks
   ```sql
   UPDATE todos SET status = 'in_progress' WHERE id IN ('scripts-feature', 'tests-feature');
   ```

2. **Provide complete context** — agents are stateless
   - Reference the other agent's work
   - Link to the same script file
   - Mention file paths clearly

3. **Collect results** when all complete

4. **Update SQL status to "done"**
   ```sql
   UPDATE todos SET status = 'done' WHERE id IN ('scripts-feature', 'tests-feature');
   ```

## Example Prompt for Parallel Scripts Task

```markdown
# Scripts Agent: [Feature]

**Context:** Part of a 2-parallel-agent task.
**Parallel Agents:** test-writer (tests), pattern-enforcer (compliance check)
**Blocks:** Both downstream agents wait for this to complete

**What to build:**
1. In [script].py, add function [function_name]:
   - Parameters: [params]
   - Returns: [return type]
   - Behavior: [description]

2. Add --[flag] CLI argument to argparse

3. Respect --dry-run: print preview, don't modify DB

**Files to modify:**
- [script].py (MODIFY)

**Dependencies:**
- Migration DONE (if applicable)
- SQLCipher connection pattern in .github/instructions/database-rules.md
```

## Parallelization Checklist

- [ ] Break down the feature into independent tasks
- [ ] Identify which tasks can run simultaneously
- [ ] Map each task to a specialized agent
- [ ] Create `agents.md` documenting the plan
- [ ] Dispatch agents with complete context
- [ ] Monitor progress in SQL `todos` table
- [ ] Collect results when all complete
- [ ] Syntax check: `python3.11 -m py_compile *.py`
- [ ] Merge into atomic commit(s)
