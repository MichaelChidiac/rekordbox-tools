# SMART-DISPATCH.md

## Intelligent Task Parallelization & Phase Detection

**Purpose:** Automatically analyze feature complexity, task dependencies, and timing to recommend
the optimal parallelization strategy — then auto-generate agents.md without manual effort.

**Status:** Invoked after plan.md is created; auto-generates agents.md.

---

## Smart Analysis Engine

### Step 1: Analyze Feature Scope

```
Input: plan.md (architecture + task descriptions)

Analyze:
├─ Feature complexity (1-10 scale)
├─ Number of distinct concerns (DB, API, UI, Tests, Mobile)
├─ Critical path length (what must finish first)
├─ Risk assessment (breaking changes? migrations needed?)
└─ Number of agents that can work in parallel
```

**Complexity Scoring:**

| Complexity | Description | Auto Parallelization |
|------------|-------------|---------------------|
| 1-2 | Single file, single concern | Sequential only (1 agent) |
| 3-4 | One module, 1-2 concerns | Sequential phases (A → B → C) |
| 5-6 | Multiple modules, 3-4 concerns | Hybrid (Phase 1 seq, Phase 2 parallel 2-3 agents) |
| 7-8 | Major feature, 4-5 concerns, migrations | Heavy parallelization (Phase 1 seq, Phase 2 parallel 3-4) |
| 9-10 | System redesign, breaking changes | Maximum parallelization + rollback planning |

**Example Analysis:**

```
Feature: User Notification System (Complexity: 7)

Scope Analysis:
✓ Concerns: Database (new table), API (new endpoints), Frontend (notification UI),
            Tests (coverage), Mobile (API extension) = 5 concerns
✓ Critical path: Migration must complete before Backend
✓ Risk: Medium (new table, but no changes to existing data)
✓ Breaking changes: None

Auto-Recommendation:
  Phase 1 (Sequential): migration → backend
    Reason: Migration must be done before backend can reference new schema

  Phase 2 (Parallel): frontend + test-writer + mobile-api
    Reason: All depend only on backend (which is done), no cross-dependencies

  Phase 3 (Optional): refactor if coverage < threshold
```

---

### Step 2: Detect Task Dependencies

**Standard Dependency Rules:**

```
dependencies = {
    'migration': [],           # Never depends on anything
    'backend': ['migration'],  # Always depends on migration (if exists)
    'frontend': ['backend'],   # Needs API routes before UI
    'test-writer': ['backend'],# Tests the code (backend must exist)
    'mobile-api': ['backend'], # Extends backend services
    'refactor': [],            # Depends on which module
    'pattern-enforcer': [],    # Independent
}
```

**Build Dependency Graph:**

```
Migration (15 min)
    ↓
Backend (45 min)
    ↓
├─→ Frontend (30 min) ──┐
├─→ Test-Writer (30 min)┤─→ Merge
└─→ Mobile-API (20 min) ┘

Phase 1: Migration + Backend (sequential) = 60 min
Phase 2: Frontend + Test-Writer + Mobile-API (parallel) = 30 min
Total Parallel: 90 min
Total Sequential: 140 min
Savings: 50 min (36% faster)
```

---

### Step 3: Estimate Timing

```
TASK TIMING DEFAULTS (adjust for your project):

migration:
  simple: 10 min   # Add 1-2 columns
  medium: 20 min   # Add table + foreign keys
  complex: 45 min  # Major schema refactor

backend:
  simple: 20 min   # CRUD endpoints only
  medium: 45 min   # Service layer + logic
  complex: 90 min  # Complex business logic, multiple services

frontend:
  simple: 15 min   # Single template, basic JS
  medium: 40 min   # Dashboard, forms, validation
  complex: 75 min  # Complex UI state, animations, responsive

test-writer:
  simple: 20 min   # 5-10 test cases
  medium: 35 min   # 20-30 test cases, fixtures
  complex: 60 min  # 50+ test cases, complex mocks

mobile-api:
  simple: 15 min   # Extend existing endpoint
  medium: 30 min   # New endpoint + auth
  complex: 50 min  # Complex mobile-specific logic

refactor:
  simple: 20 min   # Small module (< 200 lines)
  medium: 45 min   # Medium module (200-600 lines)
  complex: 90 min  # Large module (600+ lines)
```

---

### Step 4: Auto-Generate agents.md

When asked "Can you generate agents.md from my plan?":

```
Claude:
✅ Analyzing plan.md...

Feature: [Feature Name]
Complexity: [X]/10
Concerns: DB, API, UI, Tests, Mobile

Analysis:
  • Critical path: migration (15m) → backend (45m) → frontend (30m)
  • Parallelizable: frontend + tests + mobile can run simultaneously
  • Risk level: [LOW/MEDIUM/HIGH]
  • Savings: [N] min (sequential [X]m → parallel [Y]m = Z% faster)

Generated agents.md:
  Phase 1 (Sequential):
    ✓ migration (15 min)
    ✓ backend (45 min)

  Phase 2 (Parallel):
    ✓ frontend (30 min)
    ✓ test-writer (30 min)
    ✓ mobile-api (20 min)

Ready to dispatch? Say "yes" to invoke task-orchestrator.
```

---

### Step 5: Risk Assessment

Auto-detect risky patterns in plan.md:

| Risk Level | Indicators | Recommendation |
|------------|-----------|----------------|
| **HIGH** | Breaking API changes, auth changes, data migrations | Sequential-only, rollback plan required |
| **MEDIUM** | Schema additions, new required fields | Phase 1 sequential, Phase 2 parallel with safeguards |
| **LOW** | Additive changes, new tables, no changes to existing | Full parallelization approved |

---

## Parallelization Decision Tree

```
Feature Scope
    ↓
Is it ONLY backend changes?
  YES → Sequential only (no parallelization needed)
  NO  → Continue
    ↓
Does backend have breaking changes?
  YES → Sequential only (risk mitigation)
  NO  → Continue
    ↓
Does it need frontend + tests?
  YES → Phase 2 parallelization OK (2-way minimum)
  NO  → Sequential phases
    ↓
Does it need mobile-api?
  YES → 3-way parallelization (frontend + tests + mobile)
  NO  → 2-way parallelization (frontend + tests)
    ↓
RESULT: Recommended Phase configuration
```

---

## Quality Gates per Phase

Smart dispatch auto-selects quality gates based on complexity:

| Complexity | Gates Enforced |
|------------|---------------|
| 1-4 | Basic: tests pass, no syntax errors |
| 5-6 | + Type checking, docstrings |
| 7-8 | + Coverage ≥ 85%, E2E critical paths |
| 9-10 | + Security scan, rollback test |

See `.github/skills/QUALITY-GATES.md` for gate details.

---

## Usage

After writing plan.md:
```
"Can you generate agents.md from my plan?"
"Use SMART-DISPATCH to analyze my plan"
"Auto-generate the parallelization strategy"
```

After agents.md is generated:
```
"Dispatch this"
"Run the orchestrator"
"Go ahead"
```
