# API Response Rules

## Standard Response Envelope

All JSON API responses must follow the standard envelope format:

```json
// Success
{"success": true, "data": {...}}
{"success": true, "data": [...]}

// Created
{"success": true, "data": {"id": 123}, "message": "Created"}

// Deleted
{"success": true, "message": "Deleted"}

// Error
{"success": false, "error": "Human-readable message"}
{"success": false, "error": "Validation failed", "details": {...}}
```

<!-- CUSTOMIZE: Adjust to match your project's exact response format -->

## HTTP Status Codes

| Scenario | Status | Response |
|----------|--------|----------|
| Success (GET, PATCH) | 200 | `{"success": true, "data": ...}` |
| Created (POST) | 201 | `{"success": true, "data": ...}` |
| No content (DELETE) | 204 | (empty body) or `{"success": true}` |
| Bad request | 400 | `{"success": false, "error": "..."}` |
| Unauthorized | 401 | `{"success": false, "error": "Authentication required"}` |
| Forbidden | 403 | `{"success": false, "error": "Access denied"}` |
| Not found | 404 | `{"success": false, "error": "Not found"}` |
| Validation error | 422 | `{"success": false, "error": "...", "details": {...}}` |
| Server error | 500 | `{"success": false, "error": "Internal server error"}` |

## Response Helpers

Use helper functions rather than raw response construction:

```python
# ✅ Use helpers
return success_response(data=result)
return error_response("Not found", 404)
return created_response(data={"id": new_obj.id})
return deleted_response()
return paginated_response(items, page=1, total=100, per_page=20)

# ❌ Do not construct manually
return jsonify({"success": True, "data": result}), 200
```

<!-- CUSTOMIZE: Replace with your project's helper function names -->

## Pagination Format

List endpoints that can return large datasets must support pagination:

```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 100,
    "pages": 5,
    "has_next": true,
    "has_prev": false
  }
}
```

Query parameters: `?page=1&per_page=20&sort=created_at&order=desc`

## Error Details Format

Validation errors should include field-level details:

```json
{
  "success": false,
  "error": "Validation failed",
  "details": {
    "email": ["Not a valid email address"],
    "password": ["Must be at least 8 characters"]
  }
}
```

## JavaScript Client Unwrapping

All frontend JS must unwrap the envelope:

```javascript
// ✅ Correct
const result = await response.json();
const items = result.data;  // unwrap

// ❌ Wrong — data IS the envelope, not the payload
const items = await response.json();
items.forEach(...);  // CRASH: items is {success: true, data: [...]}
```
