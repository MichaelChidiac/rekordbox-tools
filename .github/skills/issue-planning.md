# Issue Planning & Organization

> Skill for creating well-structured issue folders, GitHub issues, and parallelization plans.

## Issue Folder Structure

For each new feature, create a folder in `.github/prompts/`:

```
.github/prompts/issue-[NUMBER]-[TITLE]/
├── prompt.md                # Original user request/context
├── plan.md                  # Implementation plan & architecture
├── agents.md                # Agent dispatch plan (see agents-md-spec.md)
├── acceptance-criteria.md   # Testable completion checklist
└── notes.md                 # Decisions, blockers, implementation notes
```

**Naming:** `issue-142-user-notifications` (descriptive, kebab-case).

## GitHub Issue Format (for Copilot Coding Agent)

Use this structure so Copilot can act autonomously:

```markdown
## Summary
One sentence: what this accomplishes and why.

## Context
- Relevant files: list key files involved
- Related issues or PRs: #number
- Constraints: anything Copilot must not change or break

## Acceptance Criteria
- [ ] Criterion 1 (specific, testable)
- [ ] Tests pass with `[TEST_COMMAND]`
- [ ] No regressions in [area]

## Implementation Notes
Step-by-step approach hints. Copilot can deviate if it finds a better path.

## Human Validation
(If UI changes) List pages/flows to test manually.

## Out of Scope
Explicitly list what this issue does NOT cover.
```

Full template: `.github/prompts/issue-template.md`

## Agent Parallelization

When planning multi-agent work, create `agents.md` with phases:

```markdown
## Phase 1: Foundation (sequential)
- [ ] **migration agent** — Add schema columns
  - Depends on: (none)
- [ ] **backend agent** — Create service + routes
  - Depends on: migration agent

## Phase 2: UI + Tests (parallel)
- [ ] **frontend agent** — Build templates
  - Depends on: backend routes
- [ ] **test-writer agent** — Write tests
  - Depends on: backend routes
```

**Rules:**
- Group by domain (backend vs frontend)
- Independent tasks → parallelize
- Dependent tasks → sequence
- Use `task-orchestrator` agent to automate dispatch from agents.md

Full spec: `.github/skills/agents-md-spec.md`

## Task Delegation Workflow

1. Plan feature (Claude) → generate GitHub Issue in format above
2. Paste into GitHub Issues, assign to `@copilot`
3. Copilot opens draft PR, runs tests, requests review
4. Return to Claude for review or next planning task

## Epic Organization (Multi-Issue)

When a single user request generates multiple issues, create an epic folder:

```
.github/prompts/epic-[TITLE]/
├── prompt.md              # Original requirements
├── plan.md               # Master plan (all issues)
├── acceptance-criteria.md # Epic-level AC
├── notes.md              # Decisions
└── agents.md             # Overall parallelization strategy
```

Individual issues get their own folders:
```
.github/prompts/issue-XXX-subtask-a/
.github/prompts/issue-YYY-subtask-b/
```

## After Completion

Archive finished work:

```bash
# Option A: Rename with _DONE suffix
mv ".github/prompts/issue-NNN-title" \
   ".github/prompts/issue-NNN-title_DONE"

# Option B: Move to docs/implemented/
mv ".github/prompts/issue-NNN-title/plan.md" \
   "docs/implemented/feature-design.md"
```

Update `docs/implemented/README.md` with a link to the commit/PR.

## References

- agents.md format: `.github/skills/agents-md-spec.md`
- Planning workflow: `.github/skills/PLANNING-WORKFLOW-GUIDE.md`
- Smart dispatch: `.github/skills/SMART-DISPATCH.md`
- Issue template: `.github/prompts/issue-template.md`
