# GitHub Issue Template — AI Coding Agent

<!--
  Use this template when generating issues for AI coding agents (Copilot, etc.)
  Save completed issues to GitHub Issues and assign them to @copilot or your AI agent.
  The agent reads this file as context when placed in .github/prompts/.
-->

---

## Summary
<!-- One sentence: what this accomplishes and why it matters. -->


## Context
- **Relevant files:**
  - `path/to/file.ext` — reason it's relevant
- **Related issues/PRs:** #
- **Branch to work from:** `main` (or specify)
- **Constraints:**
  - Do not modify `[file/module]`
  - Must remain compatible with `[system/interface]`

## Acceptance Criteria
- [ ] Feature/fix behaves as described in Summary
- [ ] Existing tests still pass (`[test command]`)
- [ ] New tests added for new behavior
- [ ] No new lint errors (`[lint command]`)
- [ ] PR description explains approach taken

## Implementation Notes
<!--
  Suggested approach — agent can deviate if it finds a better path.
  Be specific enough that the agent doesn't need to guess intent.
-->

1. Step one
2. Step two
3. Step three

## Human Validation
<!-- If this PR includes UI/template/CSS/layout changes:
     List pages/flows to test manually.
     Add the `needs-testing` label to trigger a preview deployment. -->
- [ ] Page/flow to test
- [ ] Expected behavior on mobile vs desktop
- [ ] Role-specific checks (admin vs regular user)

## Out of Scope
<!-- Be explicit. This prevents the agent from going too far. -->
- This issue does NOT cover `[X]`
- Refactoring `[Y]` is a separate concern
- Do not change `[Z]`
