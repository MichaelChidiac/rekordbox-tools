# Database & Model Rules (Strict Enforcement)

> These rules apply to all models and database queries.

---

## Query Patterns

### Primary Key Lookups

<!-- CUSTOMIZE: Replace with your ORM's recommended primary key lookup pattern -->

```python
# ✅ CORRECT — use the current, non-deprecated pattern
obj = db.session.get(Model, obj_id)
if obj is None:
    abort(404)

# ❌ DEPRECATED — avoid if your ORM has a newer pattern
obj = Model.query.get(obj_id)
obj = Model.query.get_or_404(obj_id)
```

### Filtered Queries

```python
# ✅ CORRECT
items = Item.query.filter_by(is_active=True).all()
item = Item.query.filter_by(slug=slug).first()

# ✅ ALSO CORRECT — for complex filters
from sqlalchemy import and_
items = Item.query.filter(
    and_(Item.category == cat, Item.is_active == True)
).all()
```

<!-- CUSTOMIZE: Replace with your ORM's query syntax -->

---

## Foreign Key Columns

**ALL foreign key columns MUST have `index=True`:**

```python
# ✅ CORRECT — indexed for query performance
user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

# ❌ WRONG — missing index (slow joins and lookups)
user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
```

Name foreign key columns with `_id` suffix matching the referenced table.

---

## Relationships

### Cascade Deletes

Parent-child relationships MUST have cascade delete:

```python
# ✅ CORRECT — orphans cleaned up on parent delete
comments = db.relationship('Comment', backref='post', cascade='all, delete-orphan')

# ❌ WRONG — orphaned rows on parent delete
comments = db.relationship('Comment', backref='post')
```

### Eager Loading

Relationships accessed >80% of the time SHOULD use eager loading:

```python
# ✅ For frequently-accessed relationships
items = db.relationship('OrderItem', backref='order', lazy='selectin', cascade='all, delete-orphan')

# ✅ For rarely-accessed relationships (default lazy loading is fine)
audit_log = db.relationship('AuditEntry', backref='user')
```

### N+1 Prevention

When looping over results that access relationships:

```python
# ✅ CORRECT — eager load with query option
items = Order.query.options(selectinload(Order.items)).all()

# ✅ ALSO CORRECT — batch pre-fetch
records = {r.order_id: r for r in Payment.query.filter(
    Payment.order_id.in_(order_ids)
).all()}

# ❌ WRONG — N+1 query in loop
for order in Order.query.all():
    for item in order.items:  # lazy load per order!
        ...
```

---

## Error Handling

```python
# ✅ CORRECT — explicit rollback
try:
    db.session.add(new_record)
    db.session.commit()
except Exception as e:
    db.session.rollback()
    return error_response(str(e), 500)

# ❌ WRONG — no rollback (leaves session in broken state)
try:
    db.session.commit()
except:
    return "Error", 500
```

---

## Migration Rules

- Always use your migration tool for schema changes (never raw `ALTER TABLE`)
- Review generated migrations before applying
- Always write both `upgrade()` and `downgrade()`
- Test upgrade + downgrade + upgrade cycle locally before committing
- Never drop a column without a plan (make nullable first in a previous migration)
- Migration messages should describe what changed: `"add index to notification.user_id"`
- Add indexes for all foreign key columns

<!-- CUSTOMIZE: Replace with your migration tool's specific commands and conventions -->

---

## Model File Organization

- One file per domain in your models directory
- Export all models from the models package `__init__.py`
- Computed properties (e.g., `total_cost`, `is_overdue`) belong on models, not routes
- Business logic (multi-model operations) belongs in services

---

## Timestamps

Add created/updated timestamps to all models:

<!-- CUSTOMIZE: Adjust to your ORM's timestamp pattern -->

```python
class BaseModel(db.Model):
    __abstract__ = True
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)
```
