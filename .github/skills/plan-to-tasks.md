# Plan-to-Tasks Skill

> Reusable skill for decomposing design documents or plans into actionable, agent-ready task files.

## What It Does

Transforms a design plan into a structured set of task files that:
- Can be assigned to AI agents (Copilot/Claude) one by one
- Have clear dependencies and execution order
- Contain acceptance criteria (testable)
- Include real, copy-pasteable code snippets
- Map 1:1 to sections of the design document

## When to Use

**Call this skill whenever you need to break down:**
- A design document into implementation tasks
- An epic into story-sized work items
- A feature plan into specific, assignable tasks
- A large refactor into smaller, independent chunks

**Trigger phrases:**
- "Break this into tasks"
- "Create task files from this plan"
- "Generate Copilot issues from this design"
- "Decompose this into actionable items"
- "Plan-to-tasks skill"

## How to Invoke

```
Claude: Read my design doc and turn it into a task breakdown.

Design doc: [paste design-my-feature.md here]

Use the plan-to-tasks skill to create task files.
```

Or reference existing design docs:

```
Claude: Apply the plan-to-tasks skill to docs/design-my-feature.md
```

## Execution Process

### Step 1: Read & Analyze

- [ ] Read the design document completely
- [ ] Identify every discrete unit of work
- [ ] List all files that will be created/modified
- [ ] Note all dependencies and blocking relationships

### Step 2: Group into Phases

Organize work into logical phases based on dependencies:

**Phase 1 - Foundation (blocking):**
- Database models, migrations
- Service layer, business logic
- Backend routes/endpoints
- No UI; can run in parallel with nothing

**Phase 2 - Core UI (depends on Phase 1):**
- HTML templates, layout
- JavaScript / interactive components
- CSS / styling
- Initial test suite

**Phase 3 - Enhancement (depends on Phase 2):**
- Charts, visualizations
- Exports (PDF, CSV)
- Advanced interactions
- Performance optimizations

**Phase 4+ - Polish & Advanced:**
- Integration with 3rd-party APIs
- Mobile API versions
- Admin tools, bulk operations
- Documentation

### Step 3: Create Task Files

For each work unit, create one `.md` file following the GitHub issue template structure.

**Required sections:**
1. **Summary** (one sentence)
   - Format: "Create [X] to [achieve Y]"
   - Example: "Create dashboard_service to calculate KPI metrics"

2. **Context** (brief bullets)
   <!-- CUSTOMIZE: Replace example file paths with your project's paths -->
   - Relevant files: `[services directory]/dashboard_service.py`, `[models directory]/event.py`
   - Related design doc: Reference the specific section
   - Depends on: Task 01, Task 03 (if applicable)
   - Constraints: "Must not break existing routes"

3. **Acceptance Criteria** (checkboxes)
   - [ ] Specific, testable assertions
   - [ ] Reference file names and function names
   - [ ] Include test command: `[TEST_COMMAND] tests/test_dashboard_service.py -v`

4. **Implementation Notes** (step-by-step)
   - Copy-pasteable code snippets (not pseudocode)
   - Real file paths and project conventions
   - References to `.github/copilot-instructions.md` patterns
   - Database schema if applicable

5. **Human Validation** (for UI tasks)
   - [ ] Visit `/path/to/feature` in browser
   - [ ] Verify specific user flows
   - [ ] Check mobile responsiveness (if applicable)

6. **Out of Scope** (prevent scope creep)
   - Explicitly list what this task does NOT include
   - Point to other tasks that handle related work

### Step 4: Naming Convention

Save task files with sequential numbers and slugs:

```
.github/prompts/my-feature/
├── 01-database-models.md      # Task 1 of N
├── 02-service-layer.md        # Task 2 of N
├── 03-routes.md               # Task 3 of N
├── 04-main-template.md        # Task 4 of N
├── 05-sidebar-navigation.md   # Task 5 of N
├── 06-javascript.md           # Task 6 of N
├── 07-tests.md                # Task 7 of N
├── 08-mobile-api.md           # Task 8 of N
└── 09-documentation.md        # Task 9 of N
```

**Naming rules:**
- Two-digit prefix: `01-`, `02-`, etc. (preserves sort order)
- Lowercase slug: descriptive, hyphenated
- Matches feature name: all files in the same `my-feature/` folder

### Step 5: Dependency Mapping

In each task's **Context** section, document dependencies:

```markdown
## Context

**Relevant files:** `[services directory]/feature_service.py`, `[models directory]/feature.py`

**Related design:** Section 2.1 "Dashboard KPI Metrics" in design-my-feature.md

**Depends on:**
- Task 01 (models must exist)
- Task 02 (service created)

**Blocks:**
- Task 04 (UI template needs this service)
- Task 07 (tests need service functions)

**Constraints:**
- Must not modify existing function signatures
- Must use service layer pattern (not route handlers)
```

### Step 6: Code Snippets

Make Implementation Notes copy-pasteable:

```python
# ❌ Bad: pseudocode
def calculate_metrics():
    # TODO: get event
    # TODO: sum up metrics
    return metrics

# ✅ Good: real, working code (adapt to your project)
from [your_orm] import func

def get_feature_kpis(feature_id: int) -> dict:
    """Calculate KPI metrics for a feature."""
    record = db.session.get(Feature, feature_id)
    if not record:
        return None

    total = db.session.query(func.count(Related.id)).filter_by(
        feature_id=feature_id
    ).scalar()

    active = db.session.query(func.count(Related.id)).filter(
        Related.feature_id == feature_id,
        Related.is_active.is_(True)
    ).scalar()

    return {
        "total": total,
        "active": active,
        "rate": (active / total * 100) if total > 0 else 0
    }
```

### Step 7: Cross-Reference Design Doc

Every task should cite the specific section of the design document it implements:

```markdown
## Summary

Create feature_service.py to calculate KPI metrics.

**Design reference:** Section 2.1 "Dashboard KPI Metrics" in design-my-feature.md

> "The dashboard displays 4 key metrics: [metric 1], [metric 2],
> [metric 3], and [metric 4]. Each metric updates as data changes."
```

### Step 8: Completeness Check

Before finishing, verify all mapping:

```markdown
## Design-to-Task Mapping

| Section | Task(s) | Status |
|---------|---------|--------|
| 1. Architecture Overview | — | Reference only |
| 2.1 Dashboard KPI Metrics | Task 02, Task 04, Task 07 | ✅ |
| 2.2 Real-time Updates | Task 06 (SSE/WS), Task 08 (mobile) | ✅ |
| 3.1 Widget A | Task 04, Task 05 | ✅ |
| 3.2 Widget B | Task 04, Task 05 | ✅ |
| 4. Mobile API | Task 08 | ✅ |
| 5. Testing | Task 07 | ✅ |
| 6. Documentation | Task 09 | ✅ |
```

## Quality Checklist

Before marking the skill as complete, verify:

- [ ] **Coverage:** Every section of the design doc maps to at least one task
- [ ] **No orphans:** Every task file references the design doc section it implements
- [ ] **Acyclic:** No circular dependencies between tasks (use dependency graph)
- [ ] **Granularity:** Each task is completable in ~30 min (single agent session)
- [ ] **Acceptance criteria:** Specific enough to verify programmatically (not "looks good")
- [ ] **Code snippets:** Real patterns, copy-pasteable, reference actual project files
- [ ] **Scope boundaries:** Out of Scope sections prevent agents from overlapping
- [ ] **Blocking clarity:** Dependency relationships are explicit ("Depends on Task X")
- [ ] **Naming:** Sequential, sortable, descriptive (01-feature.md, 02-feature.md)
- [ ] **README:** Create `.github/prompts/my-feature/README.md` with task overview

## Example Output

**Input:** `docs/design-my-feature.md` (12 sections)

**Output:** `.github/prompts/my-feature/` (9 task files)

```
my-feature/
├── README.md                          # Overview: 9 tasks, 3 phases
├── 01-feature-service.md              # Service layer for KPI calculations
├── 02-feature-model.md                # New table (if needed)
├── 03-feature-route.md                # GET /features/<id>/dashboard
├── 04-feature-template.md             # templates/features/dashboard.html
├── 05-feature-js.md                   # static/js/features/dashboard.js
├── 06-real-time-updates.md            # SSE/WebSocket endpoint for live metrics
├── 07-mobile-api.md                   # GET /api/features/<id>/dashboard (mobile)
└── 08-feature-tests.md                # Comprehensive test suite
```

**Phase dependencies:**
- Phase 1 (blocking): Tasks 01, 02, 03
- Phase 2 (depends on Phase 1): Tasks 04, 05, 06
- Phase 3 (depends on Phase 2): Tasks 07, 08

## References

- GitHub issue template: `.github/prompts/issue-template.md`
- Planning workflow: `.github/skills/PLANNING-WORKFLOW-GUIDE.md`
- Agent parallelization: `.github/skills/agents-md-spec.md`
- Project conventions: `.github/copilot-instructions.md`
