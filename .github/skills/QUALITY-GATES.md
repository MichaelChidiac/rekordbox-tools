# QUALITY-GATES.md

## Automated Code Quality Checkpoints

**Purpose:** Define minimum quality standards that are automatically checked before merge/deployment. Prevents regressions and maintains code health across all parallel agent tasks.

**Applies to:** Both Claude Code and Copilot Coding Agent — gates enforced by task-orchestrator regardless of which agent executes

**Status:** Invoked automatically by task-orchestrator at Phase completion + manual pre-merge checks.

---

## Quality Gate Framework

Quality gates are **progressive checkpoints** — each phase has minimum standards:

### Phase 1 Gates (Migration + Backend Services)

| Gate | Standard | Check Method | Fail Action |
|------|----------|--------------|-------------|
| **Schema Valid** | Migrations run without error | Upgrade + downgrade test | Block merge |
| **Single Head** | No migration conflicts | Check migration heads | Block merge |
| **Type Safety** | Type checker strict mode | Type check services + models | Warn, document |
| **Model Integrity** | All foreign keys valid | Run model tests | Block merge |
| **Service Tests** | Service layer 85%+ coverage | Coverage report on services | Block merge |

<!-- CUSTOMIZE: Replace commands below with your project's equivalents -->

**Task:** Before any Phase 1 agent commits
```bash
# Check migrations
[MIGRATION_COMMAND] heads
[MIGRATION_COMMAND] upgrade test_db
[MIGRATION_COMMAND] downgrade test_db

# Type check services
[TYPE_CHECKER] [services directory]/ [models directory]/ --strict

# Test models + services
[TEST_COMMAND] tests/test_models.py tests/test_services/ -q --tb=short
```

**Example Failure:**
```
❌ PHASE 1 GATE FAILURE: Multiple Migration Heads

Error: 2 migration heads detected
- feature_branch_migration (from backend agent)
- other_migration (from migration agent)

Action: Merge migration heads before commit

Blocking merge until resolved.
```

---

### Phase 2 Gates (Frontend + Tests + Mobile API)

| Gate | Standard | Check Method | Fail Action |
|------|----------|--------------|-------------|
| **Route Docstrings** | 100% of new routes have docstrings | Script or grep check | Warn |
| **Template Syntax** | Templates valid, no undefined vars | Template test suite | Warn |
| **JavaScript Lint** | Linter clean (no errors) | JS linter with auto-fix | Warn + auto-fix |
| **API Response Format** | All responses use standard helpers | Grep for raw response calls | Warn |
| **Test Coverage** | Overall 70%+, new code 85%+ | Coverage report | Block if under 70% |
| **E2E Tests** | Critical paths pass (no flakes) | E2E test suite | Warn (log flaky tests) |
| **Security** | CSRF/auth on state-changing endpoints | Grep + manual review | Warn |

<!-- CUSTOMIZE: Replace commands below with your project's equivalents -->

**Task:** Before Phase 2 agents commit
```bash
# Type check
[TYPE_CHECKER] [source directory]/ --strict --ignore-missing-imports

# Test coverage (70% minimum)
[TEST_COMMAND] tests/ --cov=[source directory] --cov-report=term-missing --cov-report=html -q

# Template syntax
[TEST_COMMAND] tests/test_templates.py -q

# E2E critical paths (optional if flaky)
[TEST_COMMAND] tests/e2e/critical_paths/ -v --tb=short

# Lint JavaScript (auto-fix)
[JS_LINTER] static/js/ --fix

# Check docstrings on new routes
python scripts/check_route_docstrings.py
```

**Example Failure:**
```
❌ PHASE 2 GATE FAILURE: Test Coverage Below Threshold

Current coverage: 68%
Required: 70%
Missing coverage:
  - [routes directory]/dashboard.py: 2 branches uncovered (lines 145, 167)
  - [services directory]/feature_service.py: 1 function untested

Blocker: Phase 2 cannot merge with < 70% coverage.

Action: test-writer agent must add more test cases to reach 70%+
```

---

### Pre-Merge Gates (Final Validation)

| Gate | Standard | Check Method | Fail Action |
|------|----------|--------------|-------------|
| **All Tests Pass** | 100% pass rate (no skips except allowed) | Full test suite | Block merge |
| **No Regressions** | No new failures vs baseline | Compare with main branch | Block merge |
| **CI Clean** | All CI workflows pass | Check GitHub Actions | Block merge |
| **Code Review Approved** | At least 1 approval | Check PR reviews | Block merge |
| **Docs Updated** | API docs regenerated | Run docs command, check diff | Warn |
| **Feature Registry Updated** | New routes registered | Check feature manifest | Warn |
| **SQL Todo Cleanup** | All related SQL todos marked 'done' | Query todos table | Warn |

**Pre-Merge Checklist:**
```bash
# Full test suite
[TEST_COMMAND] tests/ --ignore=tests/e2e -q

# Regenerate docs
[DOCS_COMMAND]

# Verify no unexpected doc changes
git status docs/

# Check SQL todos
sqlite3 session.db "SELECT id, status FROM todos WHERE status != 'done'"

# Verify single migration head
[MIGRATION_COMMAND] heads

# Final all-in-one validation
[BUILD_COMMAND]
```

---

## Quality Gate Severity Levels

### 🔴 **BLOCK** (Prevents Merge)
- Test coverage below 70%
- Migration conflicts (multiple heads)
- Critical security issues
- Broken imports / syntax errors
- Failed unit tests

**Action:** Agent must fix before commit. Orchestrator halts phase and marks as 'blocked'.

### 🟡 **WARN** (Log but Allow)
- Docstring missing on new route
- Flaky E2E test (logs retry count)
- Template validation warning
- Minor style issues

**Action:** Logged in PR, included in code review, but doesn't block merge.

### 🟢 **INFO** (Log Only)
- Coverage above 85% (good!)
- Zero security warnings
- Type checking clean

**Action:** Celebrated in PR summary, increases confidence.

---

## Auto-Enforcement via Task-Orchestrator

When task-orchestrator dispatches phases, it automatically checks gates:

```yaml
# agents.md with gates
phases:
  phase1:
    agents: [migration, backend]
    gates:
      - schema_valid
      - type_safe
      - service_coverage_85pct
    halt_on_fail: true  # Stop Phase 2 if Phase 1 gates fail

  phase2:
    agents: [frontend, test-writer, mobile-api]
    depends_on: [phase1]
    gates:
      - test_coverage_70pct
      - docstring_complete
      - e2e_critical_pass
    halt_on_fail: true

  pre_merge:
    gates:
      - all_tests_pass
      - ci_clean
      - code_review_approved
      - docs_updated
    halt_on_fail: true
```

**Orchestrator Logic:**
```
For each phase:
  1. Launch agents
  2. Wait for completion
  3. For each gate in phase.gates:
     - Run gate check
     - If BLOCK fails: mark phase 'blocked', halt orchestrator
     - If WARN: log to PR, continue
     - If INFO: log to summary
  4. Move to next phase (or halt)

Post-phase: Summarize gate results to user
```

---

## Gate Implementation Details

### 1. Test Coverage Gate

```python
# scripts/quality_gates/check_coverage.py
import subprocess
import re
import sys

def check_coverage(min_pct=70):
    # CUSTOMIZE: Replace with your test + coverage command
    result = subprocess.run(
        # Example: ["pytest", "tests/", "--cov=src", "--cov-report=term-missing"]
        ["[TEST_RUNNER]", "tests/", "--cov=src", "--cov-report=term-missing"],
        capture_output=True, text=True
    )

    match = re.search(r'TOTAL.*?(\d+)%', result.stdout)
    coverage = int(match.group(1)) if match else 0

    if coverage < min_pct:
        print(f"❌ Coverage {coverage}% < {min_pct}% required")
        return False
    print(f"✅ Coverage {coverage}% >= {min_pct}%")
    return True
```

### 2. Migration Heads Gate

```bash
# scripts/quality_gates/check_migration_heads.sh
# CUSTOMIZE: Replace with your migration tool's command
[MIGRATION_COMMAND] heads --resolve-dependencies

if [ $? -ne 0 ]; then
    echo "❌ Multiple migration heads detected"
    echo "Fix: [MIGRATION_COMMAND] merge heads -m 'merge heads'"
    exit 1
fi
echo "✅ Single migration head"
```

### 3. Docstring Gate

```python
# scripts/quality_gates/check_route_docstrings.py
import ast
from glob import glob

def check_route_docstrings(path='[routes directory]'):
    missing = []
    for file in glob(f'{path}/**/*.py', recursive=True):
        tree = ast.parse(open(file).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and has_route_decorator(node):
                if not ast.get_docstring(node):
                    missing.append(f"{file} - {node.name}")

    if missing:
        for m in missing:
            print(f"⚠️  Missing docstring: {m}")
    else:
        print("✅ All routes have docstrings")
```

### 4. Type Safety Gate

```bash
# scripts/quality_gates/check_types.sh
# CUSTOMIZE: Replace with your type checker
[TYPE_CHECKER] [services directory]/ [models directory]/ --strict --ignore-missing-imports

if [ $? -ne 0 ]; then
    echo "⚠️  Type errors found (non-blocking)"
    exit 0
fi
echo "✅ All types valid"
```

### 5. Custom Gate Template

```python
# scripts/quality_gates/[gate_name].py
class QualityGate:
    name = "gate_name"
    description = "What this gate checks"
    severity = "BLOCK"  # or WARN or INFO

    def check(self, **context):
        """
        Returns: (bool, str)
            - bool: True if gate passes
            - str: Message to log
        """
        result = self._run_check()
        message = f"Gate result: {result}"
        return (result, message)

    def _run_check(self):
        # Implement your check here
        pass

# Register in orchestrator:
gates_registry = {
    'gate_name': QualityGate(),
    # ...
}
```

---

## Integration with CI/CD

### GitHub Actions Integration

<!-- CUSTOMIZE: Replace with your actual CI workflow and commands -->

Add quality gates to your CI workflow:

```yaml
# .github/workflows/pre-merge-validation.yml
quality-gates:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Test Coverage (70% required)
      run: |
        [TEST_COMMAND] --cov=[source directory] --cov-report=term-missing -q
        [COVERAGE_COMMAND] report --fail-under=70

    - name: Type Checking
      run: [TYPE_CHECKER] [source directory]/

    - name: Migration Check
      run: [MIGRATION_COMMAND] heads

    - name: Route Docstrings
      run: python scripts/quality_gates/check_route_docstrings.py
```

---

## Gate Customization per Agent

Each agent type can have specific quality gates:

| Agent | Primary Gates |
|-------|---------------|
| **migration** | `schema_valid`, `single_head`, `rollback_test` |
| **backend** | `type_safe`, `service_tests_pass`, `docstrings_complete` |
| **frontend** | `template_syntax_valid`, `css_lint_clean`, `a11y_check` |
| **test-writer** | `test_coverage_+10pct`, `all_tests_pass`, `no_flaky` |
| **mobile-api** | `api_response_format`, `auth_required`, `cors_valid` |
| **refactor** | `no_behavior_change`, `100pct_test_pass`, `coverage_maintained` |
| **pattern-enforcer** | `no_functional_change`, `patterns_fixed_100pct` |

<!-- CUSTOMIZE: Adjust gates to match your project's requirements -->

---

## Reporting Quality Gate Results

### To SQL Todos Table

```sql
-- After each phase, update todos with gate status
INSERT INTO todo_results (todo_id, gate_name, status, result)
VALUES
  ('backend-service', 'type_safe', 'pass', '✅'),
  ('backend-service', 'coverage_70pct', 'pass', '✅ 72%'),
  ('frontend-dashboard', 'docstring_complete', 'warn', '⚠️ 3 missing');
```

### To PR Comment

```markdown
## ✅ Quality Gates Summary

### Phase 1: Migration + Backend (✅ PASS)
| Gate | Result |
|------|--------|
| Schema Valid | ✅ Migration clean |
| Type Safe | ✅ 0 errors |
| Coverage 85%+ | ✅ 87% |
| Service Tests | ✅ 156/156 pass |

### Phase 2: Frontend + Tests (⚠️ WARNINGS)
| Gate | Result |
|------|--------|
| Coverage 70%+ | ✅ 73% |
| Docstrings | ⚠️ 2 missing (warnings/logged) |
| E2E Critical | ✅ 12/12 pass |
| JavaScript Lint | ✅ 0 errors |

### Pre-Merge: Final (✅ READY)
| Gate | Result |
|------|--------|
| All Tests | ✅ 1247/1247 |
| CI Clean | ✅ All workflows pass |
| Code Review | ✅ 2 approvals |
| Docs | ✅ Updated |

**Result:** ✅ Ready to merge — All gates pass
**Estimated savings:** 47 minutes (parallel Phase 2)
```

---

## Adding New Quality Gates

**Template for custom gates:**

```python
# scripts/quality_gates/[gate_name].py
class QualityGate:
    name = "gate_name"
    description = "What this gate checks"
    severity = "BLOCK"  # or WARN or INFO

    def check(self, **context):
        """
        Returns: (bool, str)
            - bool: True if gate passes
            - str: Message to log
        """
        result = run_check()
        message = f"Gate result: {result}"
        return (result, message)
```

---

## Future Gate Enhancements

1. **Performance Regression Detection** — Track request latency, detect slowdowns
2. **Security Scanning** — OWASP Top 10 checks via static analysis
3. **Database Size Monitoring** — Alert if migrations significantly increase DB size
4. **Dependency Audit** — Scan dependency files for known CVEs
5. **Custom Business Rules** — E.g., "all state-changing routes must have auth"
6. **A/B Test Safety Checks** — Ensure feature flags are properly gated
7. **Accessibility Compliance** — WCAG 2.1 AA automated checks
