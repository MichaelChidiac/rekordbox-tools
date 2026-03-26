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
- The entire target file — read it fully before proposing any split
- `.github/copilot-instructions.md` — module registration patterns, imports

---

## Current Mission: Service Layer Extraction (Adapt for Your Project)

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

**Example extraction:**
```python
# Before — logic in route
@router.post('/items/{item_id}/process')
def process_item(item_id):
    item = db.get(Item, item_id)
    item.status = 'processed'
    item.processed_at = datetime.utcnow()
    db.commit()
    return success_response(data={"status": "processed"})

# After — logic in service
@router.post('/items/{item_id}/process')
def process_item(item_id):
    result = item_service.process(item_id)
    if result is None:
        return error_response("Not found", 404)
    return success_response(data=result)
```

---

## Mandatory Extraction Sequence

**Apply this sequence for every extraction, without exception:**

```
1. READ the entire target file from top to bottom
2. MAP logical groupings — do not touch any code yet
3. EXTRACT one group at a time, smallest first
4. RUN tests for that feature: [test command] tests/test_[feature].py -x
5. If tests pass → commit, then proceed to next group
6. If tests FAIL → stop, revert, diagnose. Do not proceed.
```

Never extract two groups in the same commit. One extraction = one commit = one test run.

---

## Absolute Rules

- **Zero behavior changes.** If a route returned 200 before, it returns 200 after.
- **Zero URL changes.** All existing URL patterns must continue to resolve.
- **Zero public interface changes.** Function names used externally must not be renamed.
- **Zero test modifications.** If a test breaks after your refactor, the refactor broke something — do not update the test. Revert and investigate.
- **No imports left behind.** After moving a function, remove dead imports.
- **No logic added.** If you notice a bug while refactoring, write it up as a separate issue. Fix it in a separate PR.

---

## Module Registration

<!-- CUSTOMIZE: Replace with your project's module registration pattern -->

After any split, verify module registration is correct:

```python
# Verify the module is properly imported and registered
from .new_module import NewModule
```

Run documentation generation after any split to confirm the module appears in API docs with all routes intact.

---

## Test Commands After Each Extraction

<!-- CUSTOMIZE: Replace with your project's test commands -->

```bash
# Run tests for the specific feature you refactored
[TEST_COMMAND] tests/test_[feature].py -x --tb=short -q

# Verify no service logic remains in the route
git diff --stat
```

After extraction, verify the route handler has no direct DB writes:
- No `db.session.add()` or equivalent
- No `db.session.commit()` or equivalent
- No model attribute assignments (`item.field = value`)

These should all live in the service layer now.
