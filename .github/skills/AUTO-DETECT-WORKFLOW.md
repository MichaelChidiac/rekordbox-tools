# AUTO-DETECT-WORKFLOW.md

## Automatic Request Routing & Workflow Selection

**Purpose:** When you make a request to Claude or Copilot, this skill auto-detects the request type and routes it to the appropriate workflow without requiring explicit instructions.

**Applies to:** Claude Code AND Copilot Coding Agent — both agents should follow the same auto-detection rules.

**Status:** Automatically invoked by Claude/Copilot when a user request matches entry patterns (no manual trigger needed).

---

## Quick Detection Decision Tree

```
User Request
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ DETECT REQUEST TYPE                                             │
└─────────────────────────────────────────────────────────────────┘
    ↓
    ├─→ "Add feature...", "Implement...", "Build..."
    │   → FEATURE REQUEST
    │   → Route: PLANNING-WORKFLOW-GUIDE.md
    │   → Auto: Create issue folder → plan-to-tasks → task-orchestrator
    │
    ├─→ "Fix bug...", "There's an issue...", "Users report..."
    │   → BUG FIX REQUEST
    │   → Auto: Minimal planning → quick dispatch → test coverage
    │
    ├─→ "Refactor...", "Split file...", "Reorganize..."
    │   → REFACTOR REQUEST
    │   → Auto: Use refactor agent → test coverage → code review
    │
    ├─→ "Performance...", "Optimize...", "Why is it slow?"
    │   → PERFORMANCE SPIKE
    │   → Auto: Profile → identify bottleneck → targeted fix
    │
    ├─→ "Write tests for...", "Test coverage for..."
    │   → TEST REQUEST
    │   → Route: test-writer agent directly
    │   → Auto: Coverage analysis → test generation
    │
    ├─→ "Review this...", "Check this code..."
    │   → CODE REVIEW REQUEST
    │   → Route: code-review agent directly
    │   → Auto: Analyze changes → identify issues
    │
    ├─→ "What's the status?", "Have these changes been made?", "Is X done?"
    │   → STATUS QUERY
    │   → Route: Check SQL todos → Review git history
    │   → Auto: Query todo status → list commits → summarize
    │
    ├─→ "How do I...?", "Can you explain...?", "What does...?"
    │   → QUESTION / CLARIFICATION
    │   → Route: Direct answer or reference to docs
    │   → Auto: Search docs → explain with examples
    │
    ├─→ Raw unstructured requirements (multi-concern bundle)
    │   → REQUIREMENTS INTAKE
    │   → Route: REQUIREMENTS-INTAKE.md
    │   → Auto: Parse → create issues → dispatch agents
    │
    └─→ "Can you plan..." (explicit request)
        → EXPLICIT PLANNING REQUEST
        → Route: PLANNING-WORKFLOW-GUIDE.md (Steps 1-4)
        → Auto: Create all planning docs
```

---

## Request Type Details

### 1. FEATURE REQUEST
**Keywords:** "Add", "Implement", "Build", "Create", "New feature", "Enhancement"

**Auto Workflow:**
```
1. Extract requirements from user message
2. Create issue folder: .github/prompts/issue-[NUMBER]-[slug]/
3. Generate prompt.md from user request
4. Display PLANNING-WORKFLOW-GUIDE.md (Steps 1-4)
5. Offer to auto-run plan-to-tasks skill
6. Ask: Sequential or parallel phases?
7. If user says "dispatch" → auto-launch task-orchestrator
8. Track in SQL todos
```

**AI Response Example:**
```
📋 Feature Detected: [Feature Name]

I'll help you plan and implement this. Here's what I'm doing:

1. Created: .github/prompts/issue-XXX-[feature-slug]/
   - prompt.md (your request + context)
   - Awaiting: plan.md, agents.md, acceptance-criteria.md

2. Next: Should I create a full plan with:
   ✓ Sequential phases (migration → backend → frontend)
   ✓ Parallel phases (frontend + tests run simultaneously)
   ✓ Multi-agent dispatch

Ready for: PLANNING-WORKFLOW-GUIDE.md step-by-step, or
Fast-track: Auto-generate plan + agents.md based on complexity

What's your preference?
```

---

### 2. BUG FIX REQUEST
**Keywords:** "Bug", "Issue", "Fix", "Broken", "Error", "Stack trace", "Users report"

**Auto Workflow:**
```
1. Parse stack trace or error description
2. Identify affected files/modules
3. Check git history for related commits
4. Create minimal issue folder
5. Auto-generate quick plan:
   - Root cause hypothesis
   - Fix strategy
   - Tests needed
6. Skip full planning → dispatch directly to backend + test-writer
7. Fast merge criteria (test pass + code review)
```

**AI Response Example:**
```
🐛 Bug Detected: [Description]

Stack trace analysis:
- File: [path] line [N]
- Related commit: [sha] ([description])
- Likely cause: [hypothesis]

Action plan:
1. [Fix step]
2. Add test case for this scenario
3. Quick validation + merge

Time estimate: ~15 minutes

Should I:
a) Auto-dispatch backend agent + test-writer
b) Show you the fix first, then dispatch
c) Manual mode (show details only)
```

---

### 3. REFACTOR REQUEST
**Keywords:** "Refactor", "Split", "Reorganize", "Extract", "Improve structure", "God file"

**Auto Workflow:**
```
1. Identify target file(s) / module(s)
2. Analyze size, complexity, dependencies
3. Create refactor plan:
   - Current structure analysis
   - Proposed structure
   - Risk assessment
4. Dispatch refactor agent (no new features)
5. Run test-writer for new test structure
6. Auto-merge criteria: 100% test pass + coverage maintained
```

**AI Response Example:**
```
🔧 Refactor Detected: [Module] Decomposition

Current: [path/to/file] ([N] lines)
Complexity: [N] functions across [N] concerns

Proposed structure:
  [module]/
  ├── __init__.py (entry point)
  ├── [concern_a].py ([description])
  ├── [concern_b].py ([description])
  └── [concern_c].py ([description])

Risk: Low (pure refactor, zero feature changes)
Tests affected: [N] tests

Auto-dispatch: refactor agent + test-writer
Time estimate: [N] minutes

Ready to proceed? (y/n)
```

---

### 4. PERFORMANCE SPIKE
**Keywords:** "Slow", "Performance", "Optimize", "Bottleneck", "Lag", "Latency"

**Auto Workflow:**
```
1. Capture context: which feature, when, how much slower?
2. Create performance analysis plan
3. Identify profiling approach
4. Dispatch explore agent for code analysis
5. Run targeted optimization
6. Compare before/after metrics
7. Document improvement in code comments
```

**AI Response Example:**
```
⚡ Performance Spike: [Feature] Load Time ([N]s)

Profiling plan:
1. Identify slow queries
2. Check N+1 patterns
3. Review database indexes
4. Assess frontend rendering

Quick analysis:
- Route: [file:line]
- Estimated bottleneck: [hypothesis]

Proposed fix:
1. [Fix step]
2. [Fix step]

Auto-dispatch: backend agent
Expected improvement: [before] → [after]

Proceed? (y/n)
```

---

### 5. TEST REQUEST
**Keywords:** "Test", "Coverage", "Write tests for", "Test this"

**Auto Workflow:**
```
1. Identify target code/feature
2. Query current test coverage
3. Identify coverage gaps
4. Auto-dispatch test-writer agent
5. Generate test cases following project patterns
6. Validate: no regressions, coverage maintained
```

**AI Response Example:**
```
✅ Test Request: [Module] Coverage

Current coverage: [path] = [N]%
Gap analysis:
  - Missing: [untested function/branch]
  - Missing: [edge case]
  - Missing: [error path]

Auto-dispatch: test-writer agent
Task: Generate [N] test cases covering:
  ✓ [Test category 1]
  ✓ [Test category 2]
  ✓ Edge cases

Expected new coverage: [N]% → [M]%

Proceed? (y/n)
```

---

### 6. CODE REVIEW REQUEST
**Keywords:** "Review", "Check", "What do you think", "Any issues", "Problems"

**Auto Workflow:**
```
1. Get current branch / staged changes
2. Auto-dispatch code-review agent
3. Identify bugs, security issues, patterns
4. Generate detailed review with:
   - Critical issues (blocking)
   - Warnings (should fix)
   - Suggestions (nice to have)
5. Return actionable feedback
```

**AI Response Example:**
```
🔍 Code Review: [branch-name]

Changes detected:
- [file1] ([N] lines)
- [file2] ([N] lines)

Auto-dispatch: code-review agent

Issues found:
🔴 CRITICAL (blocking):
  - [Issue description]

🟡 WARNING (should fix):
  - [Issue description]

🟢 SUGGESTION (nice to have):
  - [Issue description]

Full report: [detailed review]

Approve after fixes? (y/n)
```

---

### 7. STATUS QUERY
**Keywords:** "Status", "Done", "Complete", "Merged", "How far", "Still in progress"

**Auto Workflow:**
```
1. Parse query target: feature, branch, issue number, agent
2. Query SQL todos table for status
3. List recent commits related to target
4. Show phases completed vs. pending
5. Display any blockers
6. Show estimated time to completion
```

**AI Response Example:**
```
📊 Feature Status: [Feature Name] (issue-NNN)

Overall: [N]% Complete (Phase 1 done, Phase 2 in progress)

SQL Todos:
  ✅ DONE (2/5):
    ✅ migration agent (commit [sha])
    ✅ backend service (commit [sha])

  🔄 IN PROGRESS (2/5):
    🔄 frontend ([N]% done, [N] min remaining)
    🔄 test-writer (started [N] min ago)

  ⏳ PENDING (1/5):
    ⏳ mobile-api (blocked on frontend)

Timeline:
  - Phase 1 completed: [N] minutes ago
  - Phase 2 ETA: [N] minutes
  - Ready to merge: ~[N] minutes
```

---

### 8. QUESTION / CLARIFICATION
**Keywords:** "How", "What", "Why", "Explain", "Can you tell me", "Best practice"

**Auto Workflow:**
```
1. Identify question type: how-to, why, best-practice, explanation
2. Search relevant docs: .github/, docs/, instructions
3. Provide answer with examples + references
4. Offer deeper dive or related topics
```

---

### 9. EXPLICIT PLANNING REQUEST
**Keywords:** "Plan this", "Can you plan", "Create a plan", "Let's plan", "Break this down"

**Auto Workflow:**
```
1. Capture full context (user provides detailed description)
2. Create issue folder with all planning docs
3. Offer to auto-dispatch task-orchestrator
4. If user says "dispatch" → auto-run orchestrator
```

**AI Response Example:**
```
✅ Planning Request Accepted

Creating: .github/prompts/issue-[NUM]-[slug]/
  - prompt.md ✓
  - plan.md (needs your input)
  - agents.md (auto-generated after plan)
  - acceptance-criteria.md (needs your input)

Next steps:
1. Review + edit plan.md (architecture, phases, schema)
2. Review agents.md (auto-generated from plan)
3. Set acceptance-criteria.md (done definition)
4. Run task-orchestrator to dispatch

Your choice?
a) Manual (you edit planning docs)
b) Auto-generate (I create initial drafts)
c) Hybrid (I draft, you review)
```

---

## Auto-Invocation Rules for Claude/Copilot

**When you see a user request matching above patterns:**

1. **DO auto-detect** the request type
2. **DO route** to appropriate workflow (show guide name)
3. **DO create** any necessary folder structure
4. **DO NOT immediately dispatch agents** without explicit user approval
5. **DO offer choices**: "auto-plan" vs "manual plan" vs "fast-track"
6. **DO include** time estimates and risk assessment
7. **DO track** in SQL todos if dispatching

**These rules apply to both Claude and Copilot.** Both agents should follow the same auto-detection and routing logic.

**Examples of explicit dispatch triggers:**
- "Yes, dispatch"
- "Go ahead"
- "Automate it"
- "Run the orchestrator"
- "Execute this"

**Examples of hold-for-approval triggers:**
- First feature request → offer to auto-plan but wait for approval
- Anything marked "risky" or "breaking changes" → hold for review
- Multi-phase parallel work → show plan, wait for "dispatch"

---

## Reference Table for CLAUDE.md / copilot-instructions.md

Add this summary to your project's AI instruction files:

```markdown
## Automatic Request Routing (AUTO-DETECT-WORKFLOW)

Claude/Copilot automatically detects your request type and routes to the appropriate workflow:

| Request Type | Keywords | Auto Action |
|---|---|---|
| Feature | Add, Implement, Build, New | → PLANNING-WORKFLOW-GUIDE |
| Bug fix | Bug, Fix, Error, Broken | → Quick dispatch to backend agent |
| Refactor | Split, Reorganize, Extract | → refactor agent + test-writer |
| Performance | Slow, Optimize, Bottleneck | → Performance analysis + targeted fix |
| Test | Test, Coverage, Write tests | → test-writer agent |
| Code review | Review, Check, Issues | → code-review agent |
| Status | Status, Done, Complete | → Query SQL todos + git history |
| Question | How, Why, What, Explain | → Documentation + examples |
| Raw requirements | Multi-concern bundle | → REQUIREMENTS-INTAKE (parse + dispatch) |
| Explicit plan | Plan, Create plan, Let's plan | → PLANNING-WORKFLOW-GUIDE (steps 1-4) |

**Key Rule:** Claude will NOT auto-dispatch agents without explicit approval. It will:
1. Detect your request type
2. Show you the workflow/plan
3. Ask: "Should I proceed?" or "Approve this?"
4. Wait for approval before launching agents

**Explicit dispatch triggers:** "Yes", "Go ahead", "Automate", "Execute", "Dispatch"
```

---

## Future Enhancements

1. **Smart Phase Detection** — Auto-analyze task complexity → recommend sequential vs parallel
2. **Commit Message Templates** — Auto-fill based on request type
3. **Performance Baselines** — Track before/after metrics
4. **Dependency Graph Visualization** — Auto-render agents.md as diagrams
5. **Rollback Scripts** — Auto-generate for risky changes
6. **Merge Conflict Resolution** — Auto-suggest merge strategies
7. **Changelog Auto-Generation** — Summarize merged features
