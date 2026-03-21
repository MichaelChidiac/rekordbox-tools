# REQUIREMENTS-INTAKE.md

## Automatic Requirement Decomposition & Issue Generation

**Purpose:** When you drop unstructured requirements (a list, bullets, or freeform text), the system automatically:
1. Parses and identifies distinct issues
2. Classifies each by type and complexity
3. Creates GitHub issues with proper formatting
4. Generates planning folder structure
5. Auto-estimates parallelization strategy
6. Dispatches to agents immediately

**Status:** Invoked when you provide raw requirements without explicit structure.

---

## How It Works

### Input: Raw Requirements (Freeform Text)

<!-- CUSTOMIZE: Replace this example with something relevant to your project -->

```
The user profile page doesn't update after saving changes —
you have to refresh manually.

The sidebar navigation takes up too much space on tablet.
The menu items should collapse to icons.

We need a notification system so users get alerts when
something they care about changes. Email + in-app.

The search results page is really slow when there are
more than 1000 results. Needs pagination or lazy loading.

The admin dashboard should show a summary of today's
activity — new users, actions taken, errors logged.
```

### Processing Pipeline

```
Raw Requirements
    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 1: PARSE & DECOMPOSE                           │
│                                                     │
│ Claude/Copilot reads input                          │
│ Identifies: 5 distinct issues                       │
│ Groups by: concern type, dependencies               │
│                                                     │
│ Output: Issue list with metadata:                   │
│   Issue 1: Type=BUG, Complexity=2/10               │
│   Issue 2: Type=UI, Complexity=2/10                │
│   Issue 3: Type=FEATURE, Complexity=7/10           │
│   Issue 4: Type=PERFORMANCE, Complexity=4/10       │
│   Issue 5: Type=FEATURE, Complexity=6/10           │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 2: STRUCTURE EACH ISSUE                        │
│                                                     │
│ For each issue:                                     │
│   - Title with [TYPE] prefix                        │
│   - Clear summary                                   │
│   - Acceptance criteria                             │
│   - Out of scope definition                         │
│   - Complexity rating                               │
│   - Estimated time                                  │
│   - File paths and related code                     │
│                                                     │
│ Output: Structured issues ready for GitHub          │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 3: CREATE GITHUB ISSUES                        │
│                                                     │
│ For each structured issue:                          │
│   - Create GitHub Issue                             │
│   - Add labels (bug, feature, mobile, etc.)         │
│   - Assign to @copilot                              │
│                                                     │
│ Output: N GitHub Issues created                     │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 4: CREATE PLANNING STRUCTURE                   │
│                                                     │
│ Create epic folder (for grouped requirements):      │
│   .github/prompts/epic-[title]/                     │
│   ├── prompt.md (your original requirements)        │
│   ├── plan.md (master plan, N issues)               │
│   └── agents.md (overall parallelization)           │
│                                                     │
│ Create individual issue folders (optional):         │
│   .github/prompts/issue-XXX-[slug]/                 │
│   .github/prompts/issue-YYY-[slug]/                 │
│                                                     │
│ Output: Folder structure ready for tracking         │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 5: AUTO-DISPATCH TO AGENTS                     │
│                                                     │
│ For each issue, AUTO-DETECT-WORKFLOW:               │
│   ✓ Issue 1: BUG → Quick backend agent              │
│   ✓ Issue 2: UI → Frontend agent                    │
│   ✓ Issue 3: FEATURE → task-orchestrator (plan)     │
│   ✓ Issue 4: PERFORMANCE → backend agent            │
│   ✓ Issue 5: FEATURE → task-orchestrator (plan)     │
│                                                     │
│ Parallelization:                                    │
│   - Issues 1, 2, 4 start immediately (quick)        │
│   - Issues 3, 5 plan in parallel                     │
│   - After planning, 3 & 5 dispatch in parallel       │
│                                                     │
│ Output: All agents dispatched, tracking in SQL      │
└─────────────────────────────────────────────────────┘
    ↓
Result: "5 issues created, 3 quick tasks dispatched,
         2 complex features in planning. ETA: ~150 min total"
```

---

## Implementation: Requirements-Intake Skill

When you paste raw requirements, Claude/Copilot should:

### Step 1: Parse Requirements

```python
def parse_requirements(raw_text: str) -> list[dict]:
    """
    Extract distinct issues from raw requirements text.

    Returns: List of issue dicts with metadata
    """
    issues = []

    # Split by paragraph (empty line separator)
    paragraphs = [p.strip() for p in raw_text.split('\n\n') if p.strip()]

    for i, para in enumerate(paragraphs, 1):
        issue = {
            'number': i,
            'raw': para,
            'summary': para.split('\n')[0][:80],
            'type': classify_issue_type(para),
            'complexity': estimate_complexity(para),
            'keywords': extract_keywords(para),
            'files': infer_affected_files(para),
        }
        issues.append(issue)

    return issues
```

### Step 2: Classify Issue Type

```python
def classify_issue_type(text: str) -> str:
    """Classify issue type by analyzing text"""

    text_lower = text.lower()

    # BUG indicators
    if any(word in text_lower for word in
           ['bug', 'error', 'broken', 'crash', "doesn't", 'fail', 'issue']):
        return 'BUG'

    # MOBILE indicators
    if any(word in text_lower for word in
           ['mobile', 'phone', 'responsive', 'touch', 'tablet']):
        return 'MOBILE'

    # PERFORMANCE indicators
    if any(word in text_lower for word in
           ['slow', 'optimize', 'performance', 'lag', 'pagination']):
        return 'PERFORMANCE'

    # UI indicators (layout, sizing, appearance)
    if any(word in text_lower for word in
           ['column', 'table', 'compact', 'size', 'layout', 'appearance',
            'sidebar', 'navigation']):
        return 'UI'

    # FEATURE indicators (add, implement, create, ability)
    if any(word in text_lower for word in
           ['add', 'implement', 'create', 'need', 'ability', 'allow', 'way']):
        return 'FEATURE'

    # REFACTOR indicators
    if any(word in text_lower for word in
           ['reuse', 'split', 'reorganize', 'maintain', 'consistency']):
        return 'REFACTOR'

    return 'FEATURE'  # default
```

### Step 3: Estimate Complexity

```python
def estimate_complexity(text: str) -> int:
    """Estimate complexity on 1-10 scale"""

    score = 5  # baseline

    # Increase for keywords indicating complexity
    if any(word in text.lower() for word in
           ['database', 'migration', 'schema', 'table']):
        score += 2

    if any(word in text.lower() for word in
           ['service', 'api', 'backend', 'endpoint']):
        score += 1

    if any(word in text.lower() for word in
           ['component reuse', 'refactor', 'maintain']):
        score += 1

    # Decrease for simple fixes
    if any(word in text.lower() for word in
           ['compact', 'button', 'size', 'column']):
        score -= 2

    if 'bug' in text.lower() or 'error' in text.lower():
        score -= 1

    if 'mobile' in text.lower() and score > 4:
        score -= 1

    return max(1, min(10, score))  # Clamp to 1-10
```

### Step 4: Create GitHub Issues

```bash
# For each parsed issue, create GitHub issue
gh issue create \
  --title "[TYPE] Summary of issue" \
  --body "Full structured description" \
  --label "bug,auto-generated" \
  --assignee copilot
```

### Step 5: Auto-Dispatch

```python
def dispatch_issues(issues: list[dict]):
    """Automatically dispatch each issue to correct agent"""

    quick_issues = [i for i in issues if i['complexity'] <= 3]
    complex_issues = [i for i in issues if i['complexity'] > 3]

    # Start quick issues immediately
    for issue in quick_issues:
        agent = map_type_to_agent(issue['type'])
        dispatch(agent, issue)  # backend, frontend, test-writer

    # Start complex issues with planning
    for issue in complex_issues:
        create_issue_folder(issue)
        dispatch_planning(issue)  # → PLANNING-WORKFLOW-GUIDE
```

---

## Instruction for CLAUDE.md / copilot-instructions.md

Add this to your project's AI instruction files:

```markdown
## Automatic Requirements Intake (REQUIREMENTS-INTAKE)

When you receive raw, unstructured requirements (just a list or bullets),
automatically invoke the requirements-intake process:

1. **Parse**: Identify distinct issues from the requirements
2. **Classify**: Determine type (bug, feature, mobile, ui, performance, refactor)
3. **Structure**: Create properly formatted issue descriptions
4. **Create**: Generate GitHub issues automatically
5. **Plan**: Create issue folders and planning structure
6. **Dispatch**: Auto-route each to the appropriate agent

**The system should NOT ask clarifying questions.** It should:
- Automatically separate multi-issue bundles
- Automatically estimate complexity
- Automatically create properly formatted issues
- Automatically dispatch without waiting for approval

**Report to the user:**
```
✓ Parsed: N distinct issues
✓ Created: GitHub issues #XXX, #YYY, #ZZZ, ...
✓ Dispatching:
  - Issues #XXX, #YYY (quick tasks, starting now)
  - Issues #ZZZ, #ABC (complex features, planning then dispatch)
✓ ETA: ~N minutes total (parallel execution)
```
```

---

## Example: Raw Requirements → Auto-Dispatch

**INPUT:**
```
The user profile page doesn't update after saving changes —
you have to refresh manually.

The sidebar navigation takes up too much space on tablet.

We need a notification system so users get alerts when
something changes. Email + in-app.

The search results page is slow with 1000+ results.

The admin dashboard should show today's activity summary.
```

**AUTOMATIC PROCESSING:**

```
Claude/Copilot: "Analyzing requirements...

✓ Parsed: 5 distinct issues

Issue 1: [BUG] Profile page doesn't update after save
  Type: Bug | Complexity: 2/10 | Time: 15-20m
  Related: [routes directory]/profile.py, templates/profile/

Issue 2: [UI] Sidebar navigation too wide on tablet
  Type: UI | Complexity: 2/10 | Time: 10-15m
  Related: templates/layouts/, static/css/

Issue 3: [FEATURE] Notification system (email + in-app)
  Type: Feature | Complexity: 7/10 | Time: 90-120m
  Related: DB migration, backend service, frontend UI, email service

Issue 4: [PERFORMANCE] Search results slow with large datasets
  Type: Performance | Complexity: 4/10 | Time: 30-40m
  Related: [routes directory]/search.py, [services directory]/search_service.py

Issue 5: [FEATURE] Admin activity dashboard
  Type: Feature | Complexity: 6/10 | Time: 75-90m
  Related: [routes directory]/admin.py, [services directory]/admin_service.py

✓ Created: GitHub Issues #101, #102, #103, #104, #105

✓ Dispatching:

PHASE 1 (Immediate - Quick Tasks):
  #101 (bug) → backend agent (15m)
  #102 (ui) → frontend agent (12m)
  #104 (perf) → backend agent (35m)

PHASE 2 (Planning - Complex Tasks):
  #103 (feature/notifications) → planning workflow (120m total)
  #105 (feature/dashboard) → planning workflow (90m total)

✓ Creating: epic-improvements folder
  - prompt.md (your requirements)
  - plan.md (master plan)
  - agents.md (parallelization)

Estimated Timeline:
  - Issues #101, #102, #104: 50 min (running in background)
  - Issues #103, #105 planning: 30 min (parallel)
  - Issues #103, #105 execution: 90 min (parallel)

Total: ~130 minutes (vs 270 sequential)
Savings: 140 minutes (52% faster)

All agents dispatched. Track progress in SQL todos.
Ready to merge in ~2 hours."
```

---

## Why This Is Better

### Before (Without Requirements-Intake)
```
You: "Here's 5 things to fix..."
Claude: "I see 5 separate issues. Want me to create them individually?"
You: "Yes"
Claude: Creates issues, shows formats
You: Manually assigns to Copilot
Time lost: 10-15 minutes of back-and-forth
```

### After (With Requirements-Intake)
```
You: "Here's 5 things to fix..."
Claude: "✓ Parsed 5 issues, created #101-105, dispatching now..."
All agents start immediately, no clarification needed
Time: Instant dispatch, full parallelization
```

---

## Integration with AUTO-DETECT-WORKFLOW

Update the auto-detection flow to recognize raw requirements:

```
User Request
    ↓
Is it STRUCTURED ISSUES? (GitHub issue format, clear scope)
├─ YES → AUTO-DETECT-WORKFLOW (current path)
└─ NO  → Continue
    ↓
Is it RAW REQUIREMENTS? (unstructured, multi-concern bundle)
├─ YES → REQUIREMENTS-INTAKE (parse, create issues, dispatch)
└─ NO  → Continue
    ↓
Is it SINGLE REQUEST? (feature, bug, refactor, question)
├─ YES → AUTO-DETECT-WORKFLOW (current path)
└─ NO  → Ask for clarification
```

---

## Benefits

✅ **Drop raw requirements, get automatic everything**
✅ **No manual issue creation needed**
✅ **Proper formatting automatic, no clarification loops**
✅ **Parallelization optimized automatically**
✅ **Each issue routed to best agent immediately**
✅ **Planning structure created automatically**
✅ **SQL tracking set up automatically**
✅ **Complete visibility from day 1**

This is the "true" automation system — you type what you need, it figures out everything else.

## References

- Auto-detection: `.github/skills/AUTO-DETECT-WORKFLOW.md`
- Planning workflow: `.github/skills/PLANNING-WORKFLOW-GUIDE.md`
- Smart dispatch: `.github/skills/SMART-DISPATCH.md`
- Issue planning: `.github/skills/issue-planning.md`
- Issue template: `.github/prompts/issue-template.md`
