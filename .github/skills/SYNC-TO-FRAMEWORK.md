# SYNC-TO-FRAMEWORK.md

## Purpose

Pull improvements from rekordbox-tools back into the `copilot-agent-framework` template,
keeping everything **100% project-agnostic**. Call this skill whenever a rekordbox-tools
agent, skill, or workflow guide has an improvement worth generalizing.

**This is the inverse of the initial bootstrap.** rekordbox-tools was bootstrapped FROM
the framework. Now improvements flow back.

**Trigger phrases:**
- "Sync improvements from rekordbox-tools to the framework"
- "Push [skill/agent] improvements back to copilot-agent-framework"
- "Run SYNC-TO-FRAMEWORK"

---

## Source and Target

```
SOURCE: /Users/chidiacm/projects/rekordbox-tools/.github/
TARGET: /Users/chidiacm/projects/copilot-agent-framework/.github/
```

---

## Step 1: Diff Against the Template

Compare each file against the framework:

```bash
TEMPLATE=/Users/chidiacm/projects/copilot-agent-framework/.github
SOURCE=/Users/chidiacm/projects/rekordbox-tools/.github

# Diff each file
for f in agents/task-orchestrator.md agents/planner.md agents/refactor.md \
          agents/test-writer.md agents/pattern-enforcer.md \
          skills/QUALITY-GATES.md skills/SMART-DISPATCH.md \
          skills/PLANNING-WORKFLOW-GUIDE.md skills/AUTO-DETECT-WORKFLOW.md \
          skills/REQUIREMENTS-INTAKE.md skills/agents-md-spec.md \
          skills/plan-to-tasks.md skills/issue-planning.md; do
  if [ -f "$SOURCE/$f" ] && [ -f "$TEMPLATE/$f" ]; then
    diff "$TEMPLATE/$f" "$SOURCE/$f" > /dev/null && echo "SAME: $f" || echo "DIFFERS: $f"
  fi
done
```

---

## Step 2: Decide What to Generalize

Present the diff summary. Files that differ may have improvements worth pulling back.

**Always skip (project-specific — never pull):**
- `copilot-instructions.md` — rekordbox-tools specific
- `CLAUDE.md` — rekordbox-tools specific
- `agents/backend.md` — repurposed as "scripts" agent
- `agents/migration.md` — SQLCipher-specific
- `agents/pattern-enforcer.md` — rekordbox-tools patterns
- `instructions/database-rules.md` — SQLCipher-specific
- `instructions/service-layer-rules.md` — script-specific
- `instructions/api-response-rules.md` — CLI output specific
- `skills/QUALITY-GATES.md` — rekordbox-tools safety gates
- `skills/README.md` — project-specific index
- `prompts/` — all project-specific

**Candidate for generalization:**
- `agents/task-orchestrator.md` — orchestration logic
- `agents/planner.md` — planning workflow (strip high-risk file references)
- `agents/test-writer.md` — test patterns (generalize SQLCipher → project DB)
- `agents/refactor.md` — refactor patterns (generalize utils/ extraction)
- `skills/SYNC-TO-FRAMEWORK.md` — this very skill (generalize as UPDATE-FROM-PROJECT improvement)

---

## Step 3: Generalization Rules

Before writing any file to the framework template, apply these rules:

### Names & branding

| Find | Replace with |
|------|-------------|
| `rekordbox-tools` / `rekordbox` | `[PROJECT NAME]` |
| `traktor` / `pioneer` | `[data source]` |

### Tech stack

| Find | Replace with |
|------|-------------|
| `SQLCipher` / `sqlcipher3` | `[your database library]` |
| `PRAGMA legacy=4` | `[your required connection setup]` |
| `python3.11` | `[TEST_COMMAND]` or `[your Python]` |
| `pytest` | `[TEST_COMMAND]` |
| `master.db` / `fingerprints.db` | `[your database]` |
| `collection.nml` | `[your critical data file]` |
| `argparse` | `[your CLI library]` |
| `tqdm` | `[your progress library]` |

### File paths

| Find | Replace with |
|------|-------------|
| `~/Library/Pioneer/rekordbox/` | `[your data directory]` |
| `*.py` | `[your source files]` |
| `tests/test_*.py` | `[your test files]` |

### Strip entirely
- SQLCipher-specific PRAGMA examples
- Pioneer USB-specific patterns
- macOS-only path patterns
- `backup_master_db()` specific implementation

---

## Step 4: Verify Before Writing

```bash
# Check for remaining project-specific strings
grep -iE "rekordbox|traktor|pioneer|sqlcipher|PRAGMA|master\.db|collection\.nml" \
  generalized_file.md
```

No matches = ready to write.

Confirm:
- [ ] No real project name
- [ ] No real file paths
- [ ] No deployment/infrastructure details
- [ ] All project-specific code uses `[bracket]` placeholders
- [ ] `copilot-instructions.md` was not touched
- [ ] `CLAUDE.md` was not touched

---

## Step 5: Write and Commit to Framework

```bash
cd /Users/chidiacm/projects/copilot-agent-framework

# Write generalized file
cp generalized/[file].md .github/[path]/[file].md

# Commit
git add .github/
git commit -m "feat: improve [agent/skill] based on rekordbox-tools learnings

- [What improved or was added]
- Generalized from rekordbox-tools — all project specifics removed

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Files That Are Always Project-Specific (Never Sync)

| File | Why |
|------|-----|
| `.github/copilot-instructions.md` | Project overview, stack, safety rules |
| `CLAUDE.md` | Project-specific commands and context |
| `.github/agents/backend.md` | Repurposed as "scripts" agent — SQLCipher specific |
| `.github/agents/migration.md` | SQLCipher/fingerprints.db specific |
| `.github/agents/pattern-enforcer.md` | rekordbox-tools patterns specific |
| `.github/instructions/*.md` | All SQLCipher/CLI output specific |
| `.github/skills/QUALITY-GATES.md` | Safety gates specific to this project |
| `.github/prompts/` | All planning artifacts are project-specific |
