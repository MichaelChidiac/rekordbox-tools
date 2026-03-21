# QUALITY-GATES.md — rekordbox-tools

## Automated Code Quality Checkpoints

**Purpose:** Define minimum quality standards checked before any script change is committed. Prevents regressions and maintains safety discipline (backup patterns, SQLCipher correctness, dry-run coverage).

**Applies to:** Both Claude Code and Copilot Coding Agent — gates enforced by task-orchestrator at phase completion.

---

## Quality Gate Framework

Quality gates are **progressive checkpoints** — each phase has minimum standards.

### Phase 1 Gates (Schema + Script Implementation)

| Gate | Standard | Check Method | Fail Action |
|------|----------|--------------|-------------|
| **Syntax Valid** | All modified scripts parse without error | `python3.11 -m py_compile` | Block merge |
| **PRAGMA Completeness** | All SQLCipher connections have 3 PRAGMAs including legacy=4 | grep check | Block merge |
| **Dry-Run Present** | All write scripts support `--dry-run` | grep argparse | Block merge |
| **Backup Pattern** | All master.db write paths call `backup_master_db()` | grep check | Block merge |
| **No Hardcoded Key** | SQLCIPHER_KEY defined as module constant, not inline | grep check | Block merge |

**Phase 1 check commands:**
```bash
# Syntax check all Python scripts
python3.11 -m py_compile traktor_to_rekordbox.py rebuild_rekordbox_playlists.py \
  cleanup_rekordbox_db.py traktor_to_usb.py sync_master.py pdb_to_traktor.py find_duplicates.py

# Check PRAGMA completeness (every PRAGMA key must have PRAGMA legacy=4 nearby)
grep -n "PRAGMA key" *.py
grep -n "PRAGMA legacy" *.py

# Check for hardcoded key outside SQLCIPHER_KEY assignment
grep -n "402fd482" *.py | grep -v "SQLCIPHER_KEY ="

# Check --dry-run in all write scripts
grep -rn "dry.run\|dry_run" *.py | grep "argparse\|add_argument"

# Check backup calls
grep -n "readonly=False\|READWRITE" *.py  # then verify backup_master_db nearby
```

**Example failure:**
```
❌ PHASE 1 GATE FAILURE: Missing PRAGMA legacy=4

File: cleanup_rekordbox_db.py (line 47)
  con.execute(f"PRAGMA key='{SQLCIPHER_KEY}'")
  con.execute("PRAGMA cipher='sqlcipher'")
  # Missing PRAGMA legacy=4 → will fail with "file is not a database"

Action: Add con.execute("PRAGMA legacy=4") after PRAGMA cipher line.
Blocking merge until fixed.
```

---

### Phase 2 Gates (Tests + Pattern Enforcement)

| Gate | Standard | Check Method | Fail Action |
|------|----------|--------------|-------------|
| **Tests Pass** | All existing tests pass (if test suite exists) | `python3.11 -m pytest tests/ -x` | Block merge |
| **No Real Library Files** | `tests/fixtures/` contains only synthetic files | Manual check | Block merge |
| **Fixtures Centralized** | No fixtures defined in test files | grep check | Warn |
| **No Production Path Writes** | Tests don't write to `~/Library/Pioneer/` | grep check | Block merge |

**Phase 2 check commands:**
```bash
# Run tests (if they exist)
python3.11 -m pytest tests/ -x --tb=short -q 2>/dev/null || echo "No tests yet — skipping"

# Check no real library paths in tests
grep -rn "Library/Pioneer\|Documents/Native Instruments" tests/ || echo "✅ No real paths"

# Check no fixtures in test files
grep -rn "@pytest.fixture" tests/test_*.py || echo "✅ All fixtures centralized"
```

---

### Pre-Merge Gates (Final Validation)

| Gate | Standard | Check Method | Fail Action |
|------|----------|--------------|-------------|
| **All Tests Pass** | 100% pass rate | Full test suite | Block merge |
| **Syntax Clean** | All scripts compile | `py_compile *.py` | Block merge |
| **Safety Rules** | Dry-run, backup, PRAGMA patterns all intact | grep sweep | Block merge |
| **No Regressions** | Existing CLI flags still work | `--help` check | Block merge |
| **SQL Todos Cleaned** | All related SQL todos marked done | Query todos | Warn |

**Pre-merge checklist:**
```bash
# Full syntax check
python3.11 -m py_compile *.py

# Full test run
python3.11 -m pytest tests/ -x 2>/dev/null || echo "No tests yet"

# Safety sweep
grep -rn "PRAGMA key" *.py | wc -l    # count SQLCipher connections
grep -rn "PRAGMA legacy" *.py | wc -l  # must match above count

# Verify --help works on all scripts
for s in traktor_to_rekordbox.py rebuild_rekordbox_playlists.py cleanup_rekordbox_db.py \
         traktor_to_usb.py sync_master.py pdb_to_traktor.py find_duplicates.py; do
  python3.11 "$s" --help > /dev/null && echo "✅ $s --help OK" || echo "❌ $s --help FAILED"
done

# SQL todos
# sqlite3 session.db "SELECT id, status FROM todos WHERE status != 'done'"
```

---

## Quality Gate Severity Levels

### 🔴 BLOCK (Prevents Merge)
- Missing `PRAGMA legacy=4` on SQLCipher connection
- Hardcoded SQLCipher key (not using `SQLCIPHER_KEY` constant)
- Write script missing `--dry-run` support
- Write script missing `backup_master_db()` call
- Syntax error in any Python script
- Test writing to real `~/Library/Pioneer/` paths

**Action:** Must fix before commit. Orchestrator halts phase and marks as 'blocked'.

### 🟡 WARN (Log but Allow)
- Missing docstring on a function
- Fixture defined in test file instead of conftest.py
- Summary output missing from script

**Action:** Logged in PR, included in code review, does not block merge.

### 🟢 INFO (Log Only)
- Zero PRAGMA violations
- All scripts have module docstrings
- Tests exist and pass

---

## Gate-per-Agent Reference

| Agent | Primary Gates |
|-------|---------------|
| **migration** | `syntax_valid`, `no_sqlcipher_on_fingerprints_db` |
| **scripts** | `pragma_completeness`, `dry_run_present`, `backup_pattern`, `syntax_valid` |
| **test-writer** | `tests_pass`, `no_real_library_paths`, `fixtures_centralized` |
| **pattern-enforcer** | `pragma_completeness`, `no_hardcoded_key`, `dry_run_present`, `backup_pattern` |
| **refactor** | `syntax_valid`, `no_behavior_change`, `tests_pass` |

---

## NEVER Merge If

1. ❌ Any script has `PRAGMA key` without `PRAGMA legacy=4`
2. ❌ SQLCipher key string appears inline in any function call
3. ❌ Any write script is missing `--dry-run` support
4. ❌ Any write to `master.db` doesn't call `backup_master_db()` first
5. ❌ `collection.nml` is modified directly (not via timestamped backup copy)
6. ❌ Tests write to `~/Library/Pioneer/` or any real library path

---

## Reporting Gate Results

### To SQL Todos Table

```sql
INSERT INTO todo_results (todo_id, gate_name, status, result)
VALUES
  ('scripts-feature', 'pragma_completeness', 'pass', '✅ All 3 PRAGMAs set'),
  ('scripts-feature', 'dry_run_present', 'pass', '✅ --dry-run in argparse'),
  ('scripts-feature', 'backup_pattern', 'pass', '✅ backup_master_db() called');
```

### Summary Format

```markdown
## ✅ Quality Gates Summary — rekordbox-tools

### Phase 1: Script Implementation (✅ PASS)
| Gate | Result |
|------|--------|
| Syntax Valid | ✅ All scripts compile |
| PRAGMA Completeness | ✅ 3/3 PRAGMAs on all connections |
| Dry-Run Present | ✅ --dry-run in argparse |
| Backup Pattern | ✅ backup_master_db() called |
| No Hardcoded Key | ✅ SQLCIPHER_KEY constant used |

### Phase 2: Tests + Patterns (✅ PASS)
| Gate | Result |
|------|--------|
| Tests Pass | ✅ 12/12 tests pass |
| No Real Library Files | ✅ Only synthetic fixtures |
| Pattern Enforcer | ✅ Zero violations |

**Result:** ✅ Ready to merge — All safety gates pass
```
