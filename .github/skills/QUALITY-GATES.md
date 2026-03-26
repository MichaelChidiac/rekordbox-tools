# QUALITY-GATES.md

## Automated Code Quality Checkpoints

**Purpose:** Define minimum quality standards automatically checked before merge/deployment.
Prevents regressions and maintains code health across all parallel agent tasks.

**Status:** Invoked automatically by task-orchestrator at Phase completion + manual pre-merge checks.

---

## Quality Gate Framework

Quality gates are **progressive checkpoints** — each phase has minimum standards:

### Phase 1 Gates (Migration + Backend Services)

| Gate | Standard | Fail Action |
|------|----------|-------------|
| **Schema Valid** | Migration runs without error | Block merge |
| **Type Safety** | Type checker passes | Warn, document |
| **Model Integrity** | All foreign keys valid | Block merge |
| **Service Tests** | Service layer coverage meets threshold | Block merge |
| **Single Head** | No migration conflicts | Block merge |

<!-- CUSTOMIZE: Replace commands with your project's equivalents -->

```bash
# Check migration
[migration_command] upgrade test_db
[migration_command] downgrade test_db

# Type check services
[type_checker] src/services/ src/models/

# Test models + services
[test_command] tests/test_models.py tests/test_services/ -q
```

**Example Failure:**
```
❌ PHASE 1 GATE FAILURE: Migration Conflict

Error: Multiple migration heads detected
  - feature_branch_migration (from backend agent)
  - main_migration (from migration agent)

Action: Merge migration heads before commit
Blocking merge until resolved.
```

---

### Phase 2 Gates (Frontend + Tests + Mobile API)

| Gate | Standard | Fail Action |
|------|----------|-------------|
| **Route Docstrings** | 100% of new routes have docstrings | Warn |
| **Template Syntax** | Templates valid, no undefined vars | Warn |
| **JavaScript Lint** | Linter clean | Warn + auto-fix |
| **API Response Format** | All responses use standard helpers | Warn |
| **Test Coverage** | Overall ≥ 70%, new code ≥ 85% | Block if under 70% |
| **E2E Tests** | Critical paths pass | Warn (log flakes) |

<!-- CUSTOMIZE: Replace with your project's check commands -->

```bash
# Type check everything
[type_checker] src/

# Test coverage (70% minimum)
[test_command] tests/ --cov=src --cov-report=term-missing

# Lint JavaScript
[js_linter] static/js/

# Check docstrings
[check_docstrings_script]
```

---

### Pre-Merge Gates (Final Validation)

| Gate | Standard | Fail Action |
|------|----------|-------------|
| **All Tests Pass** | 100% pass rate | Block merge |
| **No Regressions** | No new failures vs baseline | Block merge |
| **CI Clean** | All CI workflows pass | Block merge |
| **Code Review** | At least 1 approval | Block merge |
| **Docs Updated** | API docs regenerated | Warn |
| **Feature Registry** | New routes added to registry | Warn |
| **SQL Cleanup** | All todos marked 'done' | Warn |

```bash
# Full test suite
[test_command] tests/

# Regenerate docs
[docs_command]

# Check SQL todos
SELECT * FROM todos WHERE status != 'done';

# Verify no migration conflicts
[migration_command] heads
```

---

## Quality Gate Severity Levels

### 🔴 BLOCK (Prevents Merge)
- Test coverage below 70%
- Migration conflicts
- Critical security issues
- Broken imports / syntax errors
- Failed unit tests

**Action:** Agent must fix before commit. Orchestrator halts phase and marks as 'blocked'.

### 🟡 WARN (Log but Allow)
- Missing docstring on new route
- Flaky E2E test
- Template validation warning

**Action:** Logged in PR, included in code review, but doesn't block merge.

### 🟢 INFO (Log Only)
- Coverage above 85%
- Zero security warnings
- Type checking clean

**Action:** Celebrated in PR summary.

---

## Auto-Enforcement via Task-Orchestrator

```yaml
# agents.md with gates
phases:
  phase1:
    agents: [migration, backend]
    gates:
      - schema_valid
      - type_safe
      - service_coverage_85pct
    halt_on_fail: true

  phase2:
    agents: [frontend, test-writer, mobile-api]
    depends_on: [phase1]
    gates:
      - test_coverage_70pct
      - docstrings_complete
      - e2e_critical_pass
    halt_on_fail: true

  pre_merge:
    gates:
      - all_tests_pass
      - ci_clean
      - code_review_approved
    halt_on_fail: true
```

---

## Gate Implementation Templates

### Test Coverage Gate

```python
# scripts/quality_gates/check_coverage.py
import subprocess
import re
import sys

def check_coverage(min_pct=70):
    # CUSTOMIZE: Replace with your test + coverage command
    result = subprocess.run(
        ["pytest", "tests/", "--cov=src", "--cov-report=term-missing"],
        capture_output=True, text=True
    )
    match = re.search(r'TOTAL.*?(\d+)%', result.stdout)
    coverage = int(match.group(1)) if match else 0
    
    if coverage < min_pct:
        print(f"❌ Coverage {coverage}% < {min_pct}% required")
        sys.exit(1)
    print(f"✅ Coverage {coverage}%")
```

### Custom Gate Template

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
```

---

## Gate Customization Per Agent

| Agent | Primary Gates |
|-------|---------------|
| **migration** | schema_valid, single_head, rollback_test |
| **backend** | type_safe, service_tests_pass, docstrings_complete |
| **frontend** | template_syntax_valid, css_lint_clean, a11y_check |
| **test-writer** | coverage_+10pct, all_tests_pass, no_flaky |
| **mobile-api** | api_response_format, auth_required, cors_valid |
| **refactor** | no_behavior_change, 100pct_test_pass, coverage_maintained |
| **pattern-enforcer** | no_functional_change, patterns_fixed_100pct |

<!-- CUSTOMIZE: Adjust gates to match your project's requirements -->

---

## CI/CD Integration

Add quality gates to your CI workflow:

```yaml
# .github/workflows/pre-merge-validation.yml
quality-gates:
  steps:
    - name: Test Coverage
      run: |
        [test_command] --cov=src --cov-report=term-missing
        [coverage_command] report --fail-under=70

    - name: Type Checking
      run: [type_checker] src/

    - name: Migration Check
      run: [migration_command] heads

    - name: Docstrings
      run: python scripts/quality_gates/check_docstrings.py
```

<!-- CUSTOMIZE: Replace with your actual CI commands -->

---

## Reporting Quality Gate Results

### To PR Comment

```markdown
## ✅ Quality Gates Summary

### Phase 1: Migration + Backend (✅ PASS)
| Gate | Result |
|------|--------|
| Schema Valid | ✅ Migration clean |
| Type Safe | ✅ 0 errors |
| Coverage 85%+ | ✅ 87% |

### Phase 2: Frontend + Tests (⚠️ WARNINGS)
| Gate | Result |
|------|--------|
| Coverage 70%+ | ✅ 73% |
| Docstrings | ⚠️ 2 missing (logged) |
| E2E Critical | ✅ 12/12 pass |

**Result:** ✅ Ready to merge — All blocking gates pass
```
