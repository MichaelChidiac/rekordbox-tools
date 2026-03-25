# UPDATE-FROM-PROJECT.md

## Purpose

Pull improvements from a real project into this template, keeping everything
**100% project-agnostic**. Call this skill whenever a downstream project has
improved an agent, skill, or workflow guide worth generalizing.

**Trigger phrases:**
- "Update the framework from [project path or repo]"
- "Pull improvements from [project] into the template"
- "Run UPDATE-FROM-PROJECT for [project]"

---

## Step 1: Locate the Source

The source project is the one passed in the trigger (e.g. `~/projects/traktor-ml`
or a GitHub repo URL). If not specified, ask:

```
Which project should I pull improvements from?
(Provide a local path or GitHub repo URL)
```

If a URL, clone it first:
```bash
git clone [repo-url] /tmp/source-project
SOURCE=/tmp/source-project
```

If a local path:
```bash
SOURCE=[local path]
```

---

## Step 2: Diff Against the Template

Compare each file in the source project's `.github/` against this repo:

```bash
TEMPLATE=$(pwd)  # copilot-agent-framework root

# List all framework files in the source project
find "$SOURCE/.github" -name "*.md" | sort

# For each file that also exists here, diff it
for f in agents/*.md skills/*.md prompts/*.md instructions/*.md; do
  if [ -f "$SOURCE/.github/$f" ]; then
    diff "$TEMPLATE/.github/$f" "$SOURCE/.github/$f" && echo "SAME: $f" || echo "DIFFERS: $f"
  fi
done
```

Also check for **new files** in the source that don't exist in the template:
```bash
for f in $(find "$SOURCE/.github" -name "*.md" -not -name "copilot-instructions.md"); do
  rel="${f#$SOURCE/.github/}"
  [ ! -f "$TEMPLATE/.github/$rel" ] && echo "NEW: $rel"
done
```

---

## Step 3: Decide What to Pull

Present the diff summary to the user:

```
Found in [source project]:

DIFFERS (may have improvements):
  agents/backend.md
  agents/test-writer.md
  skills/QUALITY-GATES.md

NEW (not yet in template):
  agents/data-pipeline.md
  skills/NEW-SKILL.md

SKIP (always project-specific — never pull):
  copilot-instructions.md
  CLAUDE.md

Which files should I pull? (list them, or say "all differing" / "only new")
```

Wait for confirmation before proceeding.

---

## Step 4: Generalize Each File

For every confirmed file, apply the full generalization rules below before
writing it to the template. **Do not copy any file verbatim.**

### Generalization Rules

#### Names & branding
| Find (any variant) | Replace with |
|--------------------|-------------|
| `[Project Name]` / any real project name | `[PROJECT NAME]` |
| `[project-slug]` / any repo slug | `[project-slug]` |

#### Tech stack
| Find | Replace with |
|------|-------------|
| Specific framework (FastAPI, Django, Rails…) | `[e.g. FastAPI / Django / Express]` |
| Specific ORM / DB library | `[e.g. SQLAlchemy / Django ORM / Prisma]` |
| Specific DB (SQLite, PostgreSQL…) | `[e.g. PostgreSQL (prod) / SQLite (test)]` |
| Specific auth pattern | `[your auth decorator / dependency]` |
| Specific test runner (pytest, jest…) | `[TEST_COMMAND]` |
| Specific build command | `[make build / npm run build / python -m build]` |
| Specific linter | `[flake8 / eslint / rubocop]` |
| Specific frontend framework (React, Vue…) | `[your frontend framework]` |

#### File paths
| Find | Replace with |
|------|-------------|
| Real source paths (`api/routes/`, `app/controllers/`…) | `[your routes directory]/` |
| Real test paths | `tests/` or `[your test directory]/` |
| Real config file names | `config.py` / `[config file]` |
| Real model/schema directories | `[models directory]/` |
| Real service directories | `[services directory]/` |

#### Code examples
Replace all project-specific identifiers in code blocks with `[bracket]` placeholders:

```python
# ❌ Project-specific
@router.get("/api/tracks")
async def list_tracks(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tracks").fetchall()

# ✅ Template
@router.get("/api/[resource]")
async def list_resource([auth_param]):
    # [your db access pattern]
    rows = [db].execute("SELECT * FROM [table]").fetchall()
```

#### Add CUSTOMIZE comments
Any section containing something project-specific must get a comment:

```markdown
<!-- CUSTOMIZE: Replace with your actual auth decorator names and import paths -->
<!-- CUSTOMIZE: Replace with your ORM's recommended pattern -->
<!-- CUSTOMIZE: Replace [TEST_COMMAND] with pytest, jest, rspec, etc. -->
```

#### Strip entirely
Remove without replacement:
- Deployment details (hostnames, IPs, cloud provider paths)
- Credentials or secret references
- CI/CD pipeline specifics
- Any section that only makes sense for one project

---

## Step 5: Verify Before Writing

Run a scan on each generalized file before saving:

```bash
# Check for any remaining project-specific strings
# (update this grep pattern to match the source project's identifiers)
grep -iE "[project-name]|[specific-framework]|[specific-path]" generalized_file.md
```

If any matches remain, re-generalize. Do not proceed until the scan is clean.

Also confirm:
- [ ] No real project name
- [ ] No real file paths
- [ ] No deployment/infrastructure details
- [ ] All project-specific code uses `[bracket]` placeholders
- [ ] All project-specific sections have `<!-- CUSTOMIZE: -->` comments
- [ ] `copilot-instructions.md` was not touched
- [ ] `CLAUDE.md` was not touched

---

## Step 6: Write and Commit

```bash
# Write each generalized file to the template
cp generalized/agents/[file].md .github/agents/[file].md
cp generalized/skills/[file].md .github/skills/[file].md

# Commit
git add .github/
git commit -m "feat: improve [agent/skill name] based on [project] learnings

- [What improved or was added]
- Generalized from [source project] — all project specifics removed"
```

---

## Files That Are Always Project-Specific (Never Pull)

| File | Why |
|------|-----|
| `.github/copilot-instructions.md` | Project overview, stack, architecture |
| `CLAUDE.md` | Project-specific commands and context |

Everything else is fair game if it improves the framework.
