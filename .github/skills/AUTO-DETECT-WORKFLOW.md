# AUTO-DETECT-WORKFLOW.md

## Automatic Request Routing & Workflow Selection

**Purpose:** When you make a request to Claude or Copilot, this skill auto-detects the request
type and routes it to the appropriate workflow without requiring explicit instructions.

**Applies to:** Claude Code AND Copilot Coding Agent.

**Status:** Automatically invoked when a user request matches entry patterns (no manual trigger needed).

---

## Quick Detection Decision Tree

```
User Request
    ↓
┌──────────────────────────────────────────────────────────────┐
│ DETECT REQUEST TYPE                                          │
└──────────────────────────────────────────────────────────────┘
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
    │
    ├─→ "Review this...", "Check this code..."
    │   → CODE REVIEW REQUEST
    │   → Route: code-review agent directly
    │
    ├─→ "What's the status?", "Is X done?"
    │   → STATUS QUERY
    │   → Auto: Query SQL todos → review git history → summarize
    │
    ├─→ "How do I...?", "Can you explain...?"
    │   → QUESTION / CLARIFICATION
    │   → Auto: Search docs → explain with examples
    │
    └─→ "Can you plan..." (explicit request)
        → EXPLICIT PLANNING REQUEST
        → Route: PLANNING-WORKFLOW-GUIDE.md (Steps 1-4)
```

---

## Request Type Details

### 1. FEATURE REQUEST
**Keywords:** "Add", "Implement", "Build", "Create", "New feature", "Enhancement"

**Auto Workflow:**
```
1. Extract requirements from user message
2. Create issue folder: .github/prompts/issue-[NUMBER]-[slug]/
3. Offer to auto-run plan-to-tasks skill
4. Ask: Sequential or parallel phases?
5. If user says "dispatch" → auto-launch task-orchestrator
6. Track in SQL todos
```

**AI Response Example:**
```
📋 Feature Detected: [Feature Name]

I'll help plan and implement this. Here's what I'm doing:

1. Creating: .github/prompts/issue-NNN-[slug]/

Next: Should I create a full plan with:
✓ Sequential phases (migration → backend → frontend)
✓ Parallel phases (frontend + tests run simultaneously)
✓ Multi-agent dispatch

Ready for step-by-step planning, or should I auto-generate the plan?
```

---

### 2. BUG FIX REQUEST
**Keywords:** "Bug", "Issue", "Fix", "Broken", "Error", "Stack trace", "Users report"

**Auto Workflow:**
```
1. Parse error description or stack trace
2. Identify affected files/modules
3. Check git history for related commits
4. Auto-generate quick plan:
   - Root cause hypothesis
   - Fix strategy
   - Tests needed
5. Skip full planning → dispatch directly to backend + test-writer
```

**AI Response Example:**
```
🐛 Bug Detected: [Description]

Analysis:
- File: [path] line [N]
- Likely cause: [hypothesis]

Action plan:
1. [Fix step]
2. Add test case for this scenario
3. Quick validation + merge

Should I auto-dispatch or show you the fix first?
```

---

### 3. REFACTOR REQUEST
**Keywords:** "Refactor", "Split", "Reorganize", "Extract", "God file"

**Auto Workflow:**
```
1. Identify target file(s)
2. Analyze size, complexity, dependencies
3. Create refactor plan
4. Dispatch refactor agent (no new features)
5. Run test-writer for new test structure
```

---

### 4. PERFORMANCE SPIKE
**Keywords:** "Slow", "Performance", "Optimize", "Bottleneck", "Lag"

**Auto Workflow:**
```
1. Capture context: which feature, when, how slow?
2. Identify profiling approach
3. Dispatch explore agent for code analysis
4. Run targeted optimization
5. Compare before/after
```

---

### 5. TEST REQUEST
**Keywords:** "Test", "Coverage", "Write tests for", "Test this"

**Auto Workflow:**
```
1. Identify target code/feature
2. Analyze coverage gaps
3. Auto-dispatch test-writer agent
4. Validate: no regressions, coverage maintained
```

---

### 6. CODE REVIEW REQUEST
**Keywords:** "Review", "Check", "Any issues", "Problems"

**Auto Workflow:**
```
1. Get current branch / staged changes
2. Auto-dispatch code-review agent
3. Generate review with:
   - Critical issues (blocking)
   - Warnings (should fix)
   - Suggestions (nice to have)
```

---

### 7. STATUS QUERY
**Keywords:** "Status", "Done", "Complete", "Merged", "How far"

**Auto Workflow:**
```
1. Parse query target: feature, branch, issue number
2. Query SQL todos table for status
3. List recent commits related to target
4. Show phases completed vs. pending
5. Display any blockers
```

---

### 8. QUESTION / CLARIFICATION
**Keywords:** "How", "What", "Why", "Explain", "Best practice"

**Auto Workflow:**
```
1. Identify question type
2. Search relevant docs
3. Provide answer with examples + references
```

---

### 9. EXPLICIT PLANNING REQUEST
**Keywords:** "Plan this", "Create a plan", "Let's plan", "Break this down"

**Auto Workflow:**
```
1. Capture full context
2. Create issue folder with planning docs
3. Offer to auto-dispatch task-orchestrator
4. Wait for "dispatch" to proceed
```

---

## Auto-Invocation Rules

**When you see a user request matching above patterns:**

1. **DO auto-detect** the request type
2. **DO route** to appropriate workflow
3. **DO create** any necessary folder structure
4. **DO NOT immediately dispatch agents** without explicit user approval
5. **DO offer choices**: "auto-plan" vs "manual plan" vs "fast-track"
6. **DO include** time estimates and risk assessment
7. **DO track** in SQL todos if dispatching

**Explicit dispatch triggers:**
- "Yes, dispatch"
- "Go ahead"
- "Automate it"
- "Execute this"

**Hold-for-approval triggers:**
- First feature request → offer to auto-plan but wait
- Anything with "risky" or "breaking changes" → hold for review
- Multi-phase parallel work → show plan, wait for "dispatch"
