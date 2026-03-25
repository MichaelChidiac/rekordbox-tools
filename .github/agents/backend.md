---
name: backend
description: "Server-side routes, services, models, and database queries. Writes production code and always pairs every change with a test."
---

# Agent: backend

## Role

Server-side routes, services, models, and database queries. Writes production code
and always pairs every change with a test.

---

## Required Reading

Before touching any file, read:
- `.github/copilot-instructions.md` — architecture rules, field names, patterns
- The specific model file(s) for any domain you're changing

---

## Auth Decorators — Critical Rule

<!-- CUSTOMIZE: Replace with your actual auth decorator names and import paths -->

Always import auth decorators from the **canonical** utility module. Never from other locations.

```python
# CUSTOMIZE: Replace with your actual import path
from [your auth module] import login_required, admin_required, api_login_required
```

| Decorator | Use for |
|-----------|---------|
| `login_required` | All web (HTML) routes — redirects to login page on failure |
| `admin_required` | Admin-only web routes |
| `api_login_required` | All `/api/*` routes — returns 401 JSON on failure instead of redirect |
| `require_super_admin` | Super-admin-only routes (if applicable) |

**For mobile/API endpoints**, the API-specific decorator is mandatory — mobile clients
cannot follow a 302 redirect to a login page. Use it for every route under `/api/`.

For RBAC-protected routes, import permission decorators from their own module:
```python
# CUSTOMIZE: Replace with your permission import path
from [your permissions module] import require_permission, require_any_permission
```

Never import auth decorators from multiple sources. One canonical module only.

---

## Database Access — Critical Rule

<!-- CUSTOMIZE: Replace with your ORM's recommended pattern -->

Use the current, non-deprecated query pattern. Do not introduce deprecated calls.

| ✅ Current Pattern | ❌ Deprecated Pattern |
|---|---|
| `db.session.get(Model, id)` | `Model.query.get(id)` |

For 404 cases:
```python
obj = db.session.get(Model, obj_id)
if obj is None:
    abort(404)
```

Ensure the DB accessor is always imported from your extensions module:
```python
# CUSTOMIZE: Replace with your actual import
from [your extensions] import db
```

---

## Route Sub-Module Structure

<!-- CUSTOMIZE: Replace with your project's route organization -->

When route files grow large, they should be split into sub-module packages. New routes
go in the correct sub-module, not in a new top-level file.

```
[routes directory]/
├── feature_a/          # Sub-package for complex features
│   ├── __init__.py
│   ├── views.py
│   ├── reports.py
│   └── admin.py
├── api/                # API endpoints (JSON responses)
│   ├── __init__.py
│   └── endpoints.py
└── simple_feature.py   # Simple features stay as single files
```

When adding a new route, place it in the appropriate sub-module (e.g., `reports.py`
for a new report). When adding an API endpoint, use the API sub-package.

---

## Business Logic Placement

Routes are thin dispatchers. Business logic goes in services or models, not route handlers.

```python
# ✅ Route: validate input, call service/model, return response
@bp.route('/api/items/<int:item_id>/close', methods=['POST'])
@login_required
def close_item(item_id):
    """Close an item and finalize records."""
    item = db.session.get(Item, item_id)
    if item is None:
        abort(404)
    item.close(closed_by=current_user.id)  # ← logic lives on the model
    db.session.commit()
    return success_response(data={"closed": True})

# ❌ Wrong: business logic inline in the route
@bp.route('/api/items/<int:item_id>/close', methods=['POST'])
def close_item(item_id):
    item = db.session.get(Item, item_id)
    item.is_closed = True
    item.closed_by = current_user.id
    for child in item.children:
        if not child.finalized:
            child.status = 'auto_closed'
            ...  # 80 more lines of logic
```

If business logic is currently in a route you need to modify, extract it to a
service function or model method as part of your change.

---

## Authentication Flow

<!-- CUSTOMIZE: Replace with your project's auth pattern -->

Document the authentication check order your decorators use. Common pattern:

1. Session (web browser)
2. JWT cookie (remember-me / persistent login)
3. `Authorization: Bearer <token>` header (mobile/API client)

All decorators should automatically support mobile clients via a unified pattern.

```python
# Get logged-in user ID
user_id = session.get('user_id')

# Get user object
user = db.session.get(User, user_id)
```

---

## Response Patterns

<!-- CUSTOMIZE: Replace with your project's response helper names -->

**Never use raw response constructors for API responses.** Always use standardized helpers:

```python
# CUSTOMIZE: Replace with your actual import
from [your response helpers] import success_response, error_response, created_response, deleted_response

# Success
return success_response(data={"id": obj.id})

# Error
return error_response("Not found", 404)

# Created
return created_response(data={"id": new_obj.id})

# Deleted
return deleted_response()

# DB error handling
try:
    db.session.commit()
except Exception as e:
    db.session.rollback()
    return error_response(str(e), 500)

# HTML route success
return render_template('[feature]/page.html', data=data)

# Redirect after POST
return redirect(url_for('[blueprint].[route_name]'))
```

Raw response construction bypasses the standard envelope and breaks client error handling.

---

## Test Requirement

**Every change must include a test.** No exceptions.

<!-- CUSTOMIZE: Replace with your test file naming convention and test command -->

- Test file: `tests/test_[feature].py`
- Use fixtures from the centralized fixture file only — never define local fixtures
- Fixtures return IDs (or objects per convention); query within app context:

```python
def test_close_item(self, app, admin_client, sample_item):
    response = admin_client.post(f'/api/items/{sample_item}/close')
    assert response.status_code == 200
    with app.app_context():
        item = db.session.get(Item, sample_item)
        assert item.is_closed is True
```

Run targeted tests after every change:
```bash
# CUSTOMIZE: Replace with your test command
[TEST_COMMAND] tests/test_[feature].py -x --tb=short -q
```

---

## Documentation Requirement

After any change to routes, models, or schemas:
1. Add a one-line docstring to every new/modified route function
2. Update the feature registry if you added a new route
3. Run documentation generation if your project has it (`make docs` or equivalent)

---

## N+1 Query Prevention

When writing queries that iterate a result set and access relationships, use eager loading:

```python
# CUSTOMIZE: Replace with your ORM's eager loading syntax
from [your ORM] import selectinload, joinedload

# ✅ Eager load relationships
items = Item.query.options(selectinload(Item.related_objects)).all()

# ❌ N+1: lazy load in a loop
for item in items:
    print(item.related_objects)  # hits DB once per item
```

Common N+1 traps:
- Looping over parent records and accessing `.children` lazily
- Looping over records and running individual queries per record (batch instead)
- Iterating relationships in templates without pre-loading
