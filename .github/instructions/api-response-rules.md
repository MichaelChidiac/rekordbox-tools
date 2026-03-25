# API Response Rules (Strict Enforcement)

> These rules apply to ALL JSON API responses in your route handlers.

---

## Required: Use Response Helpers

<!-- CUSTOMIZE: Replace helper names with your project's actual function names -->

**NEVER** construct JSON responses manually. Always use response helper functions:

```python
# ✅ CORRECT — use helpers
return success_response(data={"id": item.id})
return error_response("Item not found", 404)
return created_response(data={"id": new_item.id})
return deleted_response()

# ❌ WRONG — manual construction (use helpers instead)
return json_response({"success": True, "data": {...}}), 200
return json_response({"error": "Not found"}), 404
return json_response({"status": "success"}), 200
```

---

## HTTP Status Code Rules

| Action | Status Code | Helper |
|--------|-------------|--------|
| GET success | 200 | `success_response(data=...)` |
| PUT/PATCH update | 200 | `success_response(data=..., message="Updated")` |
| POST create | **201** | `created_response(data=...)` |
| DELETE | **204** | `deleted_response()` |
| Validation error | 400 | `error_response("message", 400)` |
| Not authenticated | 401 | `error_response("Not authenticated", 401)` |
| Not authorized | 403 | `error_response("Not authorized", 403)` |
| Not found | 404 | `error_response("Resource not found", 404)` |
| Conflict/duplicate | 409 | `error_response("Already exists", 409)` |
| Server error | 500 | `error_response(str(e), 500)` |

<!-- CUSTOMIZE: Adjust helper names and add/remove status codes for your project -->

---

## Response Envelope

All JSON responses follow this shape:

```json
// Success
{
  "success": true,
  "data": { ... },          // optional
  "message": "Created"      // optional
}

// Error
{
  "success": false,
  "error": "Human-readable message",
  "details": { ... }        // optional (validation errors, etc.)
}

// Paginated list
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20,
    "pages": 5
  }
}
```

<!-- CUSTOMIZE: Adjust envelope shape to match your project's convention -->

---

## Pagination Format

List endpoints that can return large datasets must support pagination:

Query parameters: `?page=1&per_page=20&sort=created_at&order=desc`

```python
# ✅ Use pagination helper
return paginated_response(items, page=1, total=100, per_page=20)
```

---

## Error Messages

- Error strings MUST be human-readable (not stack traces in production)
- Use `str(e)` only in 500 responses, and only in development
- Validation errors: use `error_response("Validation failed", 400, details=errors)`
- Be specific: "Item not found" not just "Not found"

### Validation Error Details

Include field-level details for validation errors:

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

---

## When This Applies

- All routes that return JSON responses
- All routes with API authentication decorators
- All routes under `/api/` URL prefix
- AJAX handlers that return JSON (even if the route also has HTML rendering)

**Exception:** HTML form routes that return rendered templates or redirects are
NOT covered by these rules — they follow standard framework patterns.

---

## JavaScript Client Unwrapping

All frontend JS must unwrap the envelope:

```javascript
// ✅ Correct — unwrap the envelope
const result = await response.json();
const items = result.data;

// ❌ Wrong — data IS the envelope, not the payload
const items = await response.json();
items.forEach(...);  // CRASH: items is {success: true, data: [...]}
```
