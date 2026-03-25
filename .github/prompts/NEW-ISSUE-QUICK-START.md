# New Issue Quick Start

Paste this reference when creating a new feature/issue folder.

## 30-Second Checklist

```bash
# 1. Create folder
mkdir -p ".github/prompts/issue-NNN-[title]"

# 2. Create files
touch ".github/prompts/issue-NNN-[title]"/{prompt,plan,agents,acceptance-criteria,notes}.md

# 3. Fill in prompt.md (original request)
# 4. Fill in plan.md (architecture)
# 5. Generate agents.md (ask AI to use SMART-DISPATCH)
# 6. Fill in acceptance-criteria.md

# 7. Dispatch
# Claude: Orchestrate .github/prompts/issue-NNN-[title]/agents.md
```

---

## agents.md Template (copy-paste)

```markdown
# Agent Dispatch Plan

## Phase 1: Foundation (sequential)

- [ ] **migration agent** — Add [feature] schema
  - Files: migrations/versions/[filename]
  - Depends on: (none)
  - Blocks: backend agent
  - Est time: 15 min

- [ ] **backend agent** — [Feature]Service + routes
  - Files: src/services/[feature]_service.py, src/routes/[feature].py
  - Depends on: migration agent
  - Blocks: frontend agent, test-writer
  - Est time: 45 min

## Phase 2: Parallel

- [ ] **frontend agent** — [Feature] UI
  - Files: templates/[feature]/, static/js/[feature]/
  - Depends on: backend agent
  - Est time: 30 min

- [ ] **test-writer agent** — Test suite
  - Files: tests/test_[feature].py
  - Depends on: backend agent
  - Est time: 30 min
```

---

## Acceptance Criteria Template (copy-paste)

```markdown
# Acceptance Criteria: [Feature Name]

## Functional
- [ ] [Core behavior works]
- [ ] [Edge case handled]

## Technical
- [ ] Tests pass: `[test command]`
- [ ] Coverage: 70%+
- [ ] No regressions

## Human Validation
- [ ] [Page/flow to test]
- [ ] Mobile layout
- [ ] Role-specific access
```

---

## Issue Template (copy-paste for GitHub)

```markdown
## Summary
[One sentence]

## Context
- Relevant files: [list]
- Constraints: [what not to change]

## Acceptance Criteria
- [ ] [Specific, testable criterion]
- [ ] Tests pass: `[test command]`
- [ ] No regressions

## Implementation Notes
1. [Step one]
2. [Step two]

## Out of Scope
- [Not covered]
```

---

## Quick Dispatch Phrases

```
"Plan [feature] using PLANNING-WORKFLOW-GUIDE"
"Generate agents.md from my plan using SMART-DISPATCH"
"Orchestrate .github/prompts/issue-NNN-title/agents.md"
"Use the backend agent to [specific task]"
"Use the test-writer agent for [feature] coverage"
"What's the status of issue-NNN?"
```
