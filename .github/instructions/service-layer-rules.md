# Service Layer Rules (Strict Enforcement)

> These rules apply to all service modules and route handlers.

---

## Architecture

```
Request → Route Handler → Service Function → Database
                ↓                    ↓
         Validates input      Business logic
         Auth checks          DB queries
         Returns response     Returns data
```

**Route handlers** are thin dispatchers:
1. Check authentication (via decorators)
2. Extract and validate input (via validation schemas)
3. Call a service function
4. Return a response (via response helpers)

**Service functions** contain business logic:
1. Perform database queries
2. Apply business rules and validation
3. Trigger side effects (emails, notifications, events)
4. Return plain Python objects (dicts, model instances, lists)

---

## What Goes in Services

✅ **Business logic** — calculations, decisions, state transitions
✅ **Database queries** — reads and writes
✅ **Cross-model operations** — operations involving multiple models
✅ **External service calls** — email, notifications, APIs
✅ **Complex validation** — business rules beyond basic type checking

## What Goes in Routes

✅ **Authentication check** — is the user logged in?
✅ **Authorization check** — does the user have permission?
✅ **Input parsing** — extract and validate request data
✅ **Call service** — one function call to the service layer
✅ **Return response** — format and return the result

---

## Service Function Rules

### Do

```python
# ✅ Services receive plain Python parameters
def create_item(name: str, category: str, owner_id: int) -> Item:
    """Create a new item."""
    item = Item(name=name, category=category, owner_id=owner_id)
    db.session.add(item)
    db.session.commit()
    return item

# ✅ Services return plain objects
def get_dashboard_stats() -> dict:
    """Compute dashboard statistics."""
    return {
        "total_items": Item.query.count(),
        "active_items": Item.query.filter(Item.is_active == True).count(),
    }
```

### Don't

```python
# ❌ Services must NOT import request/session/HTTP objects
from [your_framework] import request, session  # FORBIDDEN in services

# ❌ Services must NOT return HTTP responses
def bad_service():
    return json_response({"data": ...}), 200  # WRONG — route's job

# ❌ Services must NOT handle HTTP concerns
def bad_service():
    if not request.form.get('name'):  # WRONG — validation is route's job
        abort(400)
```

---

## Route Handler Pattern

<!-- CUSTOMIZE: Replace decorators and response helpers with your framework's equivalents -->

```python
@bp.route('/api/items', methods=['POST'])
@login_required
@validate_request(CreateItemSchema)
def create_item(validated_data):
    """Create a new item."""
    try:
        item = item_service.create_item(**validated_data)
        return created_response(data={"id": item.id, "name": item.name})
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        return error_response(str(e), 500)
```

---

## Error Handling in Services

Services raise exceptions or return None; routes handle the HTTP response:

```python
# Service — raises or returns None
def delete_item(item_id: int, user_id: int) -> bool:
    item = db.session.get(Item, item_id)
    if item is None:
        return False
    if item.owner_id != user_id:
        raise PermissionError("Cannot delete another user's item")
    db.session.delete(item)
    db.session.commit()
    return True

# Route — converts to HTTP
@bp.route('/api/items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id: int):
    """Delete an item."""
    try:
        deleted = item_service.delete_item(item_id, current_user.id)
    except PermissionError as e:
        return error_response(str(e), 403)
    if not deleted:
        return error_response("Not found", 404)
    return deleted_response()
```

---

## Service File Organization

<!-- CUSTOMIZE: Replace with your project's service file names -->

```
services/
├── __init__.py
├── auth_service.py       # Login, registration, password reset
├── user_service.py       # User CRUD, profile management
├── item_service.py       # Item CRUD and business rules
└── [feature]_service.py  # One service per domain
```

---

## Testing Services

Services are testable **without** the HTTP test client:

```python
def test_create_item(app):
    """Test item creation via service layer."""
    with app.app_context():
        item = item_service.create_item(
            name="Test Item",
            category="General",
            owner_id=1
        )
        assert item.id is not None
        assert item.name == "Test Item"
```

This is faster and more focused than testing via HTTP routes.

---

## When to Create a Service

- **Create a service** when route handlers exceed ~50 lines of business logic
- **Create a service** when the same logic is called from multiple routes
- **Don't create a service** for trivial CRUD with no business rules
- **Don't create a service** for one-off admin operations
