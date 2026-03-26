---
name: mobile-api
description: "Mobile/REST API endpoints, token-based auth, and JSON response formatting. Builds on the unified auth pattern — same routes serve web and mobile."
---

# Agent: mobile-api

## Role

Mobile/REST API endpoints, token-based authentication, and JSON response formatting.
Ensures API endpoints are properly authenticated, consistently formatted, and documented.

---

## Required Reading

- `.github/copilot-instructions.md` — API response format, auth patterns
- The service layer for the feature being exposed — mobile routes are thin wrappers

---

## Authentication Pattern

<!-- CUSTOMIZE: Replace with your project's auth approach -->

Mobile clients use Bearer token authentication (JWT or API key). They cannot follow
session-based redirects.

```python
# ✅ Mobile/API endpoint — returns 401 JSON on auth failure
@router.get('/api/items')
@api_login_required  # ← returns 401 JSON, not 302 redirect
def get_items():
    ...

# ❌ Web endpoint — returns 302 redirect on auth failure
@router.get('/items')
@login_required
def items_page():
    ...
```

**Never use session-based auth decorators on `/api/*` routes.**

---

## Token Lifecycle

<!-- CUSTOMIZE: Replace with your token implementation -->

```
POST /api/auth/login → returns JWT token
Authorization: Bearer <token> → on all subsequent API requests
GET /api/auth/verify → validate token, refresh if needed
POST /api/auth/logout → revoke token
```

---

## Response Format

All API responses use the standard envelope:

```json
// Success
{"success": true, "data": {...}}
{"success": true, "data": [...]}

// Error
{"success": false, "error": "Not found"}
{"success": false, "error": "Validation failed", "details": {...}}
```

<!-- CUSTOMIZE: Adjust to match your project's response format -->

Use response helpers:
```python
from ..utils.api_response import success_response, error_response, paginated_response

return success_response(data=items)
return error_response("Not found", 404)
return paginated_response(items, page=1, total=100)
```

---

## Pagination

All list endpoints must support pagination:

```python
# Query parameters
GET /api/items?page=1&per_page=20&sort=created_at&order=desc

# Response
{
  "success": true,
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 100,
    "pages": 5
  }
}
```

---

## URL Convention

<!-- CUSTOMIZE: Adapt to your URL pattern preferences -->

```
GET    /api/[resource]           — list all
POST   /api/[resource]           — create
GET    /api/[resource]/{id}      — get one
PATCH  /api/[resource]/{id}      — partial update
PUT    /api/[resource]/{id}      — full replace
DELETE /api/[resource]/{id}      — delete

# Nested resources
GET    /api/[parent]/{id}/[child]
POST   /api/[parent]/{id}/[child]
```

---

## Mobile-Specific Response Considerations

Mobile clients often have:
- Limited bandwidth — minimize response payload size
- Offline capability — include timestamps for sync
- Different screen states — include both display and raw values

```python
# Include both human-readable and machine-parseable:
return success_response(data={
    "id": item.id,
    "status": item.status,                # machine: "pending"
    "status_display": item.status_label,  # human: "Waiting for approval"
    "created_at": item.created_at.isoformat(),  # ISO 8601 for sync
    "created_at_display": "2 hours ago",         # human-readable
})
```

---

## Error Handling

All errors must return structured JSON:

```python
@router.errorhandler(404)
def not_found(e):
    return error_response("Resource not found", 404)

@router.errorhandler(422)
def validation_error(e):
    return error_response("Validation failed", 422, details=e.messages)

@router.errorhandler(500)
def server_error(e):
    return error_response("Internal server error", 500)
```

---

## Test Requirement

Every API endpoint needs:

```python
class TestMobileItemsAPI:
    def test_list_with_bearer_token(self, client, auth_token, sample_item):
        response = client.get('/api/items',
            headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_requires_bearer_token(self, client):
        response = client.get('/api/items')
        assert response.status_code == 401

    def test_pagination(self, client, auth_token):
        response = client.get('/api/items?page=1&per_page=5',
            headers={"Authorization": f"Bearer {auth_token}"})
        assert "pagination" in response.json()
```

---

## Documentation

Every API endpoint must have:
1. A docstring describing what it does
2. Parameters documented (query params, body fields)
3. Response schema described
4. Auth requirement noted

```python
@router.get('/api/items/{item_id}')
@api_login_required
def get_item(item_id: int):
    """Get a single item by ID.
    
    Returns the item with all fields.
    Requires Bearer token authentication.
    """
    ...
```
