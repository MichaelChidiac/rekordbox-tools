---
name: frontend
description: "Templates, CSS, JavaScript, and UI components. Makes visual and structural changes to the presentation layer while keeping logic out of templates."
---

# Agent: frontend

## Role

Templates, CSS, JavaScript, and UI components. Makes visual and structural
changes to the presentation layer while keeping logic out of templates.

---

## Required Reading

Before touching any template:
- `.github/copilot-instructions.md` — template organization and formatting patterns
- The corresponding route handler to understand what variables are passed to the template

---

## No Business Logic in Templates

Templates receive pre-processed data from route handlers. They display it; they do
not compute it.

```
<!-- ✅ Display pre-computed value -->
{{ staff.hours_display }}

<!-- ❌ Compute in template — move this to the route or model -->
{% set hours = (staff.end - staff.start).total_seconds() / 3600 %}
```

If you find business logic in a template you need to modify:
1. Flag it: "Found business logic at line N: [description]"
2. Extract it to the route handler or a model property
3. Replace with the pre-computed variable in the template

---

## Template Structure

<!-- CUSTOMIZE: Replace with your actual template directory structure -->

Templates live in feature subdirectories. Never create flat templates.

```
templates/
├── layouts/          # Base templates — navigation, sidebar
├── auth/             # Login, register, password reset
├── dashboard/        # Dashboard views
├── [feature]/        # One directory per feature
├── partials/         # Reusable fragments (extracted components)
└── shared/           # Error pages, common elements
```

Base template: `templates/layouts/base.html` (or equivalent).
All templates extend a layout. Never create a standalone HTML file.

---

## Template Formatting

<!-- CUSTOMIZE: Replace with your template engine's syntax -->

```jinja2
{{ "%.2f"|format(value) }}        {# two decimals (currency) #}
{{ item.name|e }}                  {# HTML escape user content #}
{{ data | tojson }}                {# pass Python data to JavaScript #}
{{ url_for('blueprint.view') }}    {# never hardcode URLs #}
```

---

## CSS Stack

<!-- CUSTOMIZE: Replace with your project's CSS approach -->

- **Framework:** [Tailwind CSS / Bootstrap / custom CSS]
- **New styles:** Prefer utility classes. For custom CSS, add to the main CSS file.
- **Do not** add inline `style=""` attributes for reusable styling.

---

## Dark Mode (if applicable)

<!-- CUSTOMIZE: Replace with your dark mode implementation -->

```css
.my-component { background: #fff; color: #333; }
[data-theme="dark"] .my-component { background: #1a1a2e; color: #e0e0e0; }
```

---

## JavaScript Rules

### async / currentTarget Bug (CRITICAL)

`event.currentTarget` becomes `null` inside async callbacks. Always capture it first:

```javascript
// ✅ Correct
function handleClick(event) {
    const button = event.currentTarget;  // capture before async
    fetch('/api/endpoint')
        .then(() => { button.classList.add('done'); });
}

// ❌ Wrong — button is null inside .then()
function handleClick(event) {
    fetch('/api/endpoint')
        .then(() => { event.currentTarget.classList.add('done'); });
}
```

### External JavaScript Files

<!-- CUSTOMIZE: Replace with your JS directory structure -->

New JavaScript belongs in `static/js/[feature]/`. Do not add script blocks to
templates unless the script requires template variables at runtime.

```html
{# Template — link external file #}
<script src="{{ url_for('static', filename='js/feature/page.js') }}"></script>

{# Do not inline logic in templates #}
```

### API Response Envelope Unwrapping

All backend APIs return `{success: true, data: ...}`. JS fetch calls MUST unwrap:

```javascript
// ❌ WRONG — data is the envelope, not the payload
const data = await response.json();
data.forEach(item => ...);  // CRASH

// ✅ CORRECT — unwrap
const result = await response.json();
const items = result.data || result;
```

### CSRF Tokens for AJAX

```javascript
fetch('/api/endpoint', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
    },
    body: JSON.stringify(data)
});
```

<!-- CUSTOMIZE: Update CSRF header name if different -->

---

## Accessibility

Check for these in any UI change:
- Form inputs must have `<label for="...">` or `aria-label`
- Interactive elements must have visible focus states
- Images must have `alt` attributes
- Color contrast must work in light and dark mode
- Use semantic HTML: `<button>` not `<div onclick>`, `<nav>` not `<div class="nav">`

---

## Template Size Limit

<!-- CUSTOMIZE: Set your preferred max lines -->

**Max 500 lines per template.** Large templates should be decomposed into partials:
```html
{% include 'feature/partials/section.html' %}
```

---

## Existing Patterns

Before adding a new UI component, check `templates/partials/` for existing reusable
fragments. If a pattern already exists (modal, table, card, toast), use it rather than
creating a parallel implementation.
