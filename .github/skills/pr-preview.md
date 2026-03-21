# PR Preview & Human Testing

> Skill for using label-triggered preview deployments to validate UI/visual changes.

<!-- CUSTOMIZE: This skill assumes you have a CI workflow that deploys PR previews
     when a specific label is added. Adapt the label name, URL, and workflow
     to match your project's setup. -->

## When to Apply the Preview Label

Add the preview label (e.g., `needs-testing`) when your PR includes ANY of:
- Template / view changes
- CSS / JS changes
- Role-based UI visibility changes (admin vs user)
- Mobile / responsive layout changes
- Navigation changes (sidebar, header, footer)

## How It Works

1. Add label → CI workflow builds and deploys the PR branch
2. A preview environment is created with the PR's changes
3. Bot posts a comment on the PR with the preview URL
4. Removing the label or closing the PR → preview environment torn down

<!-- CUSTOMIZE: Replace with your project's preview infrastructure -->

## How to Apply

```bash
gh pr edit <number> --add-label "needs-testing"
```

## Required PR Body Section

Always include a `## Human Validation` section listing specific flows to test:

```markdown
## Human Validation
- [ ] Visit `/dashboard` on mobile — layout renders correctly
- [ ] Log in as [role] — correct UI elements visible
- [ ] Test [specific changed flow] — describe expected behavior
- [ ] Check responsive breakpoints (mobile, tablet, desktop)
```

## AI Agent Rule

AI agents (Claude/Copilot) **MUST** add the preview label to PRs with visual/UI changes.
In the PR body, note which flows to test manually under `## Human Validation`.

## When NOT to Apply

Skip the preview label when changes are:
- Backend-only (models, services, API logic)
- Test-only (new or updated tests)
- Documentation-only
- Configuration changes (CI, Docker, env vars)
- Database migrations with no UI impact

## CI Workflow Template

<!-- CUSTOMIZE: This is an example workflow. Adapt to your deployment setup. -->

```yaml
# .github/workflows/deploy-pr-preview.yml
name: PR Preview

on:
  pull_request:
    types: [labeled, unlabeled, closed]

jobs:
  deploy-preview:
    if: github.event.label.name == 'needs-testing'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build preview
        run: |
          # Build your application
          [BUILD_COMMAND]

      - name: Deploy to preview environment
        run: |
          # Deploy to a temporary environment
          # Post preview URL as PR comment
          echo "Preview deployed"

  teardown-preview:
    if: >
      github.event.action == 'closed' ||
      (github.event.action == 'unlabeled' && github.event.label.name == 'needs-testing')
    runs-on: ubuntu-latest
    steps:
      - name: Tear down preview
        run: |
          # Remove the preview environment
          echo "Preview torn down"
```

## References

- Planning workflow: `.github/skills/PLANNING-WORKFLOW-GUIDE.md`
- Issue planning: `.github/skills/issue-planning.md`
