# Skills & Guides Index

This directory contains reusable workflow guides and skills for AI-assisted development.

## Skill Index

| Skill | File | When to use |
|-------|------|-------------|
| Auto-Detect Workflow | `AUTO-DETECT-WORKFLOW.md` | Automatic routing based on request type |
| Planning Workflow | `PLANNING-WORKFLOW-GUIDE.md` | Master 5-step feature planning guide |
| Smart Dispatch | `SMART-DISPATCH.md` | Auto-analyze complexity + generate agents.md |
| Quality Gates | `QUALITY-GATES.md` | Automated quality checkpoints per phase |
| agents.md Spec | `agents-md-spec.md` | Format specification for dispatch plans |
| Plan to Tasks | `plan-to-tasks.md` | Decompose a plan doc into agent tasks |
| Issue Planning | `issue-planning.md` | Create structured issue folders, GitHub issues, and parallelization plans |
| PR Preview | `pr-preview.md` | Trigger staging preview deployments for visual/manual validation |
| Requirements Intake | `REQUIREMENTS-INTAKE.md` | Parse raw unstructured requirements into classified, dispatched GitHub issues |

## How These Work Together

```
New request
    ↓
AUTO-DETECT-WORKFLOW.md
    ↓ routes to
PLANNING-WORKFLOW-GUIDE.md
    ↓ creates plan.md → triggers
SMART-DISPATCH.md
    ↓ generates agents.md → triggers
task-orchestrator agent
    ↓ dispatches phases, enforces
QUALITY-GATES.md
    ↓
Done ✅
```

### Supporting Skills

```
Raw requirements (unstructured)
    ↓
REQUIREMENTS-INTAKE.md         ← auto-parses, classifies, creates issues
    ↓ generates issue folders using
issue-planning.md              ← structured folder + agents.md creation
    ↓ PR with UI changes triggers
pr-preview.md                  ← staging deployment for human validation
```

## Quick Start

For any new feature request, say:
> "Follow the PLANNING-WORKFLOW-GUIDE to plan [feature]"

For auto-generating the parallelization plan:
> "Use SMART-DISPATCH to generate agents.md from my plan"

For running it all automatically:
> "Orchestrate `.github/prompts/issue-NNN-title/agents.md`"

For raw unstructured requirements:
> "Here's my list of improvements..." → REQUIREMENTS-INTAKE auto-activates

For issue planning with proper folder structure:
> "Plan issue #NNN with full folder setup" → issue-planning skill
