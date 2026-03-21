# SMART-DISPATCH.md

## Intelligent Task Parallelization & Phase Detection

**Purpose:** Automatically analyze feature complexity, task dependencies, and timing to recommend optimal parallelization strategy — then auto-generate agents.md without user effort.

**Applies to:** Both Claude Code and Copilot Coding Agent

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
└─ Team size (how many agents can work in parallel?)
```

**Complexity Scoring:**

| Complexity | Description | Auto Parallelization |
|------------|-------------|---------------------|
| 1-2 | Single file, single concern | Sequential only (1 agent) |
| 3-4 | One module, 1-2 concerns | Sequential phases (agent A → B → C) |
| 5-6 | Multiple modules, 3-4 concerns | Hybrid (Phase 1 seq, Phase 2 parallel 2-3 agents) |
| 7-8 | Major feature, 4-5 concerns, migrations | Heavy parallelization (Phase 1 seq, Phase 2 parallel 3-4, Phase 3 async) |
| 9-10 | System redesign, multiple modules, breaking changes | Maximum parallelization with rollback planning |

**Example Analysis:**

<!-- CUSTOMIZE: Replace with a feature from your project -->

```
Feature: User Notification System (Complexity: 7)

Scope Analysis:
✓ Concerns: Database (new table), API (new endpoints), Frontend (notification UI),
            Tests (coverage), Mobile (API extension) = 5 concerns
✓ Critical path: Migration must complete before Backend can proceed (blocks everything)
✓ Risk: Medium (new table, but backward compatible)
✓ Breaking changes: None

Auto-Recommendation:
  Phase 1 (Sequential): migration → backend
    Reason: Migration must be done before backend can reference new columns

  Phase 2 (Parallel): frontend + test-writer + mobile-api
    Reason: Frontend doesn't depend on anything except backend
            Test-writer can write tests in parallel with frontend dev
            Mobile-api extends existing endpoints (no blocking)

  Phase 3 (Optional): refactor if coverage < 85%
```

---

### Step 2: Detect Task Dependencies

**Dependency Rules:**

```python
dependencies = {
    'migration': [],           # Never depends on anything
    'backend': ['migration'],  # Always depends on migration
    'frontend': ['backend'],   # Needs API before UI
    'test-writer': ['backend', 'frontend'],  # Tests both
    'mobile-api': ['backend'], # Extends backend
    'refactor': [],            # Depends on which module
    'pattern-enforcer': ['backend', 'frontend'],
    'code-review': ['*'],      # Everything else
}

# Critical path (longest chain)
critical_path = migration (15m) → backend (42m) → frontend (28m) = 85 min sequential
```

**Build Dependency Graph:**

```
Migration (15 min)
    ↓
Backend (42 min)
    ↓
├─→ Frontend (28 min) ──┐
├─→ Test-Writer (31 min)┤─→ Merge (5 min)
└─→ Mobile-API (19 min) ┘

Phase 1: Migration + Backend (sequential) = 57 min
Phase 2: Frontend + Test-Writer + Mobile-API (parallel) = 31 min (max of 28, 31, 19)
Phase 3: Optional refactor (if needed) = 15 min
Total Parallel: 57 + 31 + 15 = 103 min
Total Sequential: 57 + 28 + 31 + 19 + 15 = 150 min
Savings: 47 min (31% faster)
```

---

### Step 3: Estimate Timing

Each task has typical duration based on complexity:

<!-- CUSTOMIZE: Adjust these timing defaults for your project's actual agent performance -->

```python
TASK_TIMING = {
    'migration': {
        'simple': 10,     # Add 1-2 columns
        'medium': 20,     # Add table, foreign keys
        'complex': 45,    # Major schema refactor
    },
    'backend': {
        'simple': 20,     # CRUD endpoints only
        'medium': 45,     # Service layer + logic
        'complex': 90,    # Complex business logic, multiple services
    },
    'frontend': {
        'simple': 15,     # Single template, basic JS
        'medium': 40,     # Dashboard, forms, validation
        'complex': 75,    # Complex UI state, animations, responsive
    },
    'test-writer': {
        'simple': 20,     # 5-10 test cases
        'medium': 35,     # 20-30 test cases, fixtures
        'complex': 60,    # 50+ test cases, complex mocks
    },
    'mobile-api': {
        'simple': 15,     # Extend existing endpoint
        'medium': 30,     # New mobile endpoint + mobile auth
        'complex': 50,    # Complex mobile-specific logic
    },
    'refactor': {
        'simple': 20,     # Small module (< 200 lines)
        'medium': 45,     # Medium module (200-600 lines)
        'complex': 90,    # Large module (600+ lines, many concerns)
    },
}

# Auto-estimate based on plan.md descriptions
def estimate_timing(task_description: str, agent: str) -> int:
    complexity = analyze_complexity(task_description)  # simple/medium/complex
    return TASK_TIMING[agent][complexity]
```

**Example:**

```
Plan excerpt:
  Task 1: "Add notification columns to User model"
  Auto-estimate: migration/simple (single table add) = 15 min

  Task 2: "Create /api/notifications endpoint with filtering"
  Auto-estimate: backend/medium (service layer + query logic) = 45 min

  Task 3: "Build notification dropdown with real-time updates"
  Auto-estimate: frontend/medium (UI + JS interactions) = 40 min
```

---

### Step 4: Auto-Generate agents.md

**Template Generation:**

```python
def generate_agents_md(plan_dict) -> str:
    """
    Input: Parsed plan.md
    Output: agents.md Markdown
    """

    analysis = analyze_feature(plan_dict)

    agents_md = f"""
# Parallelization Strategy

**Feature:** {plan_dict['title']}
**Complexity:** {analysis['complexity']}/10
**Estimated Duration:** {analysis['sequential_time']} min sequential → {analysis['parallel_time']} min parallel
**Savings:** {analysis['savings_min']} min ({analysis['savings_pct']}%)
**Critical Path:** {analysis['critical_path']}

## Phases

### Phase 1: Foundation (Sequential)

**Reason:** Migration must complete before Backend can reference new schema.

```yaml
agents:
  - migration:
      est_time_min: {analysis['migration_time']}
      description: {plan_dict['tasks']['migration']}

  - backend:
      est_time_min: {analysis['backend_time']}
      depends_on: [migration]
      description: {plan_dict['tasks']['backend']}
```

### Phase 2: Parallel Development

**Reason:** Frontend, tests, and mobile API have no blocking dependencies.

```yaml
agents:
  - frontend:
      est_time_min: {analysis['frontend_time']}
      depends_on: [backend]
      description: {plan_dict['tasks']['frontend']}

  - test-writer:
      est_time_min: {analysis['tests_time']}
      depends_on: [backend]
      description: {plan_dict['tasks']['tests']}

  - mobile-api:
      est_time_min: {analysis['mobile_time']}
      depends_on: [backend]
      description: {plan_dict['tasks']['mobile']}
```

### Phase 3: Optional Quality (Conditional)

**Condition:** If test coverage < threshold

```yaml
agents:
  - refactor:
      est_time_min: {analysis['refactor_time']}
      depends_on: [test-writer]
      optional: true
      condition: "coverage < 85%"
```

## Timeline

**Sequential (no parallelization):**
{' → '.join([f'{a}({t}m)' for a, t in analysis['sequential_timeline']])}
= {analysis['sequential_time']} minutes total

**Parallel (with Phase 2 async):**
Phase 1: {analysis['phase1_time']} min
Phase 2: {analysis['phase2_time']} min (parallel, not cumulative)
Phase 3: {analysis['phase3_time']} min (if needed)
= {analysis['parallel_time']} minutes total

**Time saved: {analysis['savings_min']} min ({analysis['savings_pct']}% faster)**
"""

    return agents_md
```

---

### Step 5: Risk Assessment

Auto-detect risky patterns:

```python
def assess_risk(plan_dict) -> dict:
    """Identify patterns that suggest sequential-only or rollback planning."""

    risks = {
        'breaking_changes': False,
        'data_migration': False,
        'auth_changes': False,
        'api_version': False,
    }

    if any('breaking' in task.lower() for task in plan_dict['tasks'].values()):
        risks['breaking_changes'] = True

    if any('migration' in task.lower() for task in plan_dict['tasks'].values()):
        risks['data_migration'] = True

    if any('auth' in task.lower() for task in plan_dict['tasks'].values()):
        risks['auth_changes'] = True

    if risks['breaking_changes'] or risks['auth_changes']:
        return {
            'level': 'HIGH',
            'recommendation': 'Sequential-only (Phase 1 + Phase 2 serial)',
            'rollback': 'Required',
            'testing': 'Critical path + full regression',
        }
    elif risks['data_migration']:
        return {
            'level': 'MEDIUM',
            'recommendation': 'Phase 1 seq, Phase 2 parallel with migration safeguards',
            'rollback': 'Optional (data-safe)',
            'testing': 'Migration + business logic',
        }
    else:
        return {
            'level': 'LOW',
            'recommendation': 'Full parallelization approved',
            'rollback': 'Optional',
            'testing': 'Standard',
        }
```

| Risk Level | Indicators | Recommendation |
|------------|-----------|----------------|
| **HIGH** | Breaking API changes, auth changes, data transformations | Sequential-only, rollback plan required |
| **MEDIUM** | Schema additions, new required fields | Phase 1 sequential, Phase 2 parallel with safeguards |
| **LOW** | Additive changes, new tables, no changes to existing | Full parallelization approved |

---

## Parallelization Decision Tree

```
Feature Scope
    ↓
┌─────────────────────────────────────┐
│ Is it ONLY backend changes?         │
├─────────────────────────────────────┤
│ YES → Sequential only (migration → backend)
│ NO  → Continue
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Does backend have breaking changes? │
├─────────────────────────────────────┤
│ YES → Sequential only (risk mitigation)
│ NO  → Continue
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Does it need frontend + tests?      │
├─────────────────────────────────────┤
│ YES → Phase 2 parallelization OK
│ NO  → Sequential phases
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Does it need mobile-api?            │
├─────────────────────────────────────┤
│ YES → 3-way parallelization (frontend + tests + mobile)
│ NO  → 2-way parallelization (frontend + tests)
└─────────────────────────────────────┘
    ↓
RESULT: Recommended Phase configuration
(+ estimated timing + risk level)
```

---

## Usage: Automatic agents.md Generation

**When to auto-generate:**

After you create plan.md and want agents.md instantly:

```
User: "Can you generate agents.md from my plan?"

Claude:
✅ Analyzing plan.md...

Feature: [Feature Name]
Complexity: 7/10
Concerns: DB (migration), API (backend), UI (frontend), Tests, Mobile

Analysis:
  • Critical path: migration (15m) → backend (42m) → frontend (28m)
  • Parallelizable: frontend + tests + mobile can run simultaneously
  • Risk level: LOW (no breaking changes, data migration is backward-compatible)
  • Savings: 47 min (sequential 150m → parallel 103m = 31% faster)

Generated agents.md:
  Phase 1 (Sequential):
    ✓ migration (15 min)
    ✓ backend (42 min)

  Phase 2 (Parallel):
    ✓ frontend (28 min)
    ✓ test-writer (31 min)
    ✓ mobile-api (19 min)

  Phase 3 (Optional):
    ✓ refactor (if coverage < 85%)

Ready to dispatch? Say "yes" and I'll invoke task-orchestrator.
```

---

## Quality Gates per Phase

Smart dispatch auto-selects quality gates based on complexity:

```python
def select_gates(complexity: int, risk: str) -> list:
    """Auto-select which gates to enforce based on risk."""

    gates = {
        'schema_valid': complexity >= 5,      # Only if DB changes
        'type_safe': complexity >= 6,
        'coverage_85pct': complexity >= 7,
        'e2e_critical': risk == 'HIGH',
        'security_scan': risk == 'HIGH',
    }

    return [gate for gate, enabled in gates.items() if enabled]
```

| Complexity | Gates Enforced |
|------------|---------------|
| 1-4 | Basic: tests pass, no syntax errors |
| 5-6 | + Type checking, docstrings |
| 7-8 | + Coverage ≥ 85%, E2E critical paths |
| 9-10 | + Security scan, rollback test |

See `.github/skills/QUALITY-GATES.md` for gate details.

---

## Reporting Smart Decisions

Auto-generate summary for PR:

```markdown
## Smart Dispatch Analysis

**Feature:** [Feature Name]
**Complexity:** 7/10 | **Risk:** LOW | **Agents:** 5 | **Phases:** 3

### Parallelization Strategy

**Sequential → Parallel Analysis:**
- Critical Path: migration (15m) → backend (42m) = **57 min to unblock**
- Parallel Tasks: frontend (28m) + tests (31m) + mobile (19m) = **31 min in parallel**
- Optional: refactor (if coverage < 85%)

**Estimated Timing:**
| Approach | Duration | Notes |
|----------|----------|-------|
| Sequential | 150 min | All agents wait sequentially |
| Parallel | 103 min | Phase 2 all-async |
| **Savings** | **47 min (31%)** | ✅ Recommended |

### Quality Gates (Auto-Selected)
- [x] Schema valid (migration)
- [x] Type safety (complex services)
- [x] 85% coverage (large feature)
- [x] Critical path E2E tests
- [ ] Security scan (low risk)

### Risk Assessment
- Breaking changes: None ✅
- Data migration: Backward-compatible ✅
- Auth changes: None ✅
- **Overall:** LOW RISK — Full parallelization approved

**Next Step:** Dispatch to task-orchestrator for execution.
```

---

## Smart Timing Refinement

As agents execute, refine timing estimates:

```sql
-- Store actual timing vs estimated
INSERT INTO agent_timings (agent_name, feature_id, estimated_min, actual_min, complexity)
VALUES ('backend', 'notification-system', 45, 47, 'medium');

-- Improve future estimates from historical data
UPDATE timing_model
SET avg_actual = (estimated + 0.2 * (avg_actual - estimated))
WHERE agent = 'backend' AND complexity = 'medium';
```

**Tracking Accuracy:**

```
Over time, smart dispatch learns:
- backend/medium tasks average 48 min (vs 45 estimate)
- frontend/complex tasks have high variance (35-65 min)
- test-writer typically takes 10% longer than estimated
- migration is predictable ±2 min

Refine estimates accordingly for future features.
```

---

## Continuous Improvement

Smart dispatch learns over time:

```python
class SmartDispatchModel:
    def __init__(self):
        self.timings = {}  # Historical data
        self.accuracy = {}  # Error tracking

    def record_completion(self, agent, task, estimated, actual, complexity):
        key = f'{agent}/{complexity}'
        self.timings[key].append(actual)
        error = abs(actual - estimated) / estimated
        self.accuracy[key].append(error)

    def predict_timing(self, agent, description) -> int:
        """Better estimate based on history."""
        complexity = analyze_complexity(description)
        key = f'{agent}/{complexity}'

        if key in self.timings and len(self.timings[key]) > 5:
            return avg(self.timings[key][-5:])
        else:
            return TASK_TIMING[agent][complexity]
```

---

## Integration Checklist

- [ ] Call from plan-to-tasks skill (auto-generate agents.md)
- [ ] Update CLAUDE.md / copilot-instructions.md with "Smart Parallelization" section
- [ ] Add test cases for decision tree
- [ ] Track agent timings in SQL todos table
- [ ] Visualize critical path in PR summaries
