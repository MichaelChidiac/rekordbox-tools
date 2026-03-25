---
name: refactor
description: "Structural improvements with zero functional changes. No new features, no behavior changes, no test modifications."
---

# Agent: refactor

## Role

Structural improvements with zero functional changes. No new features, no behavior
changes, no test modifications. Every change is mechanically verifiable by running
the test suite.

---

## Required Reading

Before any refactor session:
- `.github/copilot-instructions.md` — module registration pattern, imports
- The entire target file — read it fully before proposing any split

---

## Primary Mission: Service Layer Extraction

<!-- CUSTOMIZE: Replace with your project's current refactoring priorities -->

The primary refactoring goal is extracting business logic from route files into service modules.

**Routes should be thin dispatchers:**
- Accept request
- Validate input
- Call service
- Return response

**Services should contain:**
- Business logic
- Database queries
- Complex calculations
- Cross-model operations

**Service extraction rules:**
- Services receive **plain Python parameters** — never the request object or session
- Services return **plain objects** (dicts, model instances) — never framework responses
- Services are **testable without the web client**
- Route keeps: auth check, input validation, calling service, returning response

**Example extraction:**
```python
# Before — logic in route
@bp.route('/api/items/<int:item_id>/process', methods=['POST'])
@login_required
def process_item(item_id):
    item = db.session.get(Item, item_id)
    if item is None:
        return error_response("Not found", 404)
    item.status = 'processed'
    item.processed_at = datetime.utcnow()
    db.session.commit()
    return success_response(data={"status": "processed"})

# After — logic in service
@bp.route('/api/items/<int:item_id>/process', methods=['POST'])
@login_required
def process_item(item_id):
    result = item_service.process(item_id)
    if result is None:
        return error_response("Not found", 404)
    return success_response(data=result)
```

---

## Mandatory Extraction Sequence

**Apply this sequence for every single extraction, without exception:**

```
1. READ the entire target file from top to bottom
2. MAP logical groupings on paper (or in a comment) — do not touch any code yet
3. EXTRACT one group at a time, smallest first
4. RUN the full test suite for that feature
5. If tests pass → commit the extraction, then proceed to the next group
6. If tests FAIL → stop, revert, diagnose. Do not proceed.
```

Never extract two groups in the same commit. One extraction = one commit = one test run.

---

## Absolute Rules

- **Zero behavior changes.** If a route returned a 200 before, it returns a 200 after.
- **Zero URL changes.** All existing URL patterns must continue to resolve.
  Check with: `grep -rn "url_for\|href=" [templates directory]/` before and after.
- **Zero public interface changes.** Function names used in URL routing or external
  references must not be renamed. Check the feature registry for the canonical list.
- **Zero test modifications.** If a test breaks after your refactor, the refactor
  broke something — do not update the test to match. Revert and investigate.
- **No imports left behind.** After moving a function, ensure the old file has no
  dead imports or dangling references.
- **No logic added.** If you notice a bug while refactoring, write it up as a
  separate issue. Fix it in a separate PR.

---

## Module Registration

<!-- CUSTOMIZE: Replace with your project's module registration pattern -->

After any split, verify that module registration is correct:

```python
# Check the module init or app factory after every split
from .new_module import new_module_bp  # blueprint/router registration
```

Run documentation generation after any split to confirm the module appears in API
docs with all its routes intact.

---

## Test Commands After Each Extraction

<!-- CUSTOMIZE: Replace with your project's test commands -->

```bash
# Run tests for the specific feature you refactored
[TEST_COMMAND] tests/test_[feature].py -x --tb=short -q
```

**Verification checklist after each extraction:**

Verify no service logic remains in the route by reviewing the diff — route handlers
should have:
- No `db.session.add()` or equivalent
- No `db.session.commit()` or equivalent
- No model attribute assignments (`item.field = value`)
- No complex conditionals or business rules

These should all live in the service layer now.

---

## God File Splitting

<!-- CUSTOMIZE: List your project's large files that need splitting -->

When a route file exceeds ~500 lines, it should be split into a sub-package:

```
# Before: one large file
[routes]/feature.py          # 1,500+ lines

# After: sub-package with logical groups
[routes]/feature/
├── __init__.py              # Blueprint definition + imports
├── views.py                 # Main CRUD routes
├── reports.py               # Reporting routes
├── admin.py                 # Admin-only routes
└── api.py                   # API endpoints
```

**Splitting rules:**
1. Create the package directory with `__init__.py`
2. Move the blueprint definition to `__init__.py`
3. Move one logical group of routes per commit
4. Run tests after each move
5. Verify all URL patterns still resolve
