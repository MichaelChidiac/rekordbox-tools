# Testing Rules

## Fixtures — Centralized, Never Duplicated

**All fixtures live in one centralized file (e.g., `tests/conftest.py`).**
Never define a fixture in an individual test file.

```python
# ✅ CORRECT — define in conftest.py
@pytest.fixture
def sample_user(app):
    with app.app_context():
        user = User(email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id  # return ID, not object

# ❌ WRONG — local fixture in test file
@pytest.fixture
def my_user():  # duplicates conftest
    ...
```

**Fixtures return IDs, not objects** — query within `app_context()` when you need the object:

```python
def test_something(app, sample_user):
    with app.app_context():
        user = db.session.get(User, sample_user)
        assert user.email == "test@example.com"
```

## Test Structure

Group tests by feature in classes:

```python
class TestItemAPI:
    def test_create_success(self, client, admin_client):
        response = admin_client.post('/items', json={"name": "Test"})
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "Test"

    def test_create_requires_auth(self, client):
        response = client.post('/items', json={"name": "Test"})
        assert response.status_code in (302, 401)

    def test_create_requires_permission(self, regular_client):
        response = regular_client.post('/admin/items', json={})
        assert response.status_code in (302, 403)

    def test_get_not_found(self, admin_client):
        response = admin_client.get('/items/99999')
        assert response.status_code == 404

    def test_create_invalid_input(self, admin_client):
        response = admin_client.post('/items', json={})  # missing required fields
        assert response.status_code == 422
```

**Every feature needs at minimum:**
1. Happy path (success case)
2. Unauthenticated → 401/302
3. Wrong role → 403/302
4. Not found → 404
5. Invalid input → 400/422

## Running Tests

```bash
# ✅ During development — run only affected file
[test_command] tests/test_[feature].py -x --tb=short -q

# ✅ Run single test
[test_command] tests/test_[feature].py::TestClass::test_method -x

# ⚠️ Full suite — final validation only (slow)
[test_command] tests/
```

<!-- CUSTOMIZE: Replace [test_command] with pytest, jest, rspec, etc. -->

**NEVER run the full test suite during iterative development.** Run the specific file you're changing.

## Coverage

<!-- CUSTOMIZE: Set your project's coverage threshold -->

- Minimum: 70% overall coverage
- Target: 85% for new code
- Block merge if below 70%

```bash
[test_command] tests/ --cov=src --cov-report=term-missing
```

## API Response Testing

Test the response envelope, not just the status code:

```python
def test_api_response_format(self, client, sample_item):
    response = client.get(f'/api/items/{sample_item}')
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True    # envelope
    assert "id" in data["data"]       # payload
```

## DB Access in Tests

Use the same query pattern as application code:

```python
# ✅ Correct
item = db.session.get(Item, sample_item_id)

# ❌ Deprecated (if your ORM has moved past this)
item = Item.query.get(sample_item_id)
```

## What Not to Do

- ❌ Define fixtures in test files (centralized only)
- ❌ Test implementation details — test behavior and outputs
- ❌ Write tests that hit real external services (use mocks)
- ❌ Depend on test execution order
- ❌ Skip testing after a change "just this once"
- ❌ Ignore test failures — they are signals, not obstacles
