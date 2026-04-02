# PaperLens Agent Guide

## Default Working Rule

For repository tasks that involve real changes, use this closed loop by default:

1. Implement the requested changes.
2. Run validation that is appropriate for the scope.
3. Record durable issues, fixes, decisions, and validation results in `docs/project_issue_log.md`.
4. Update `.autonomous/paperlens-demo/` tracking files when the task changes ongoing status, handoff context, or follow-up priorities.
5. Commit the relevant changes.
6. Push to `origin/main`.

Do not stop after only code changes unless the user explicitly asks to pause before validation, logging, commit, or push.

## Logging Rule

- Treat project logging as part of the default finish step, not as an optional extra.
- When a bug, regression, workflow gap, root cause, or durable decision is found, update `docs/project_issue_log.md` in the same working turn.
- When the work changes future continuation context, also update the relevant `.autonomous/paperlens-demo/` files.

## Commit And Push Rule

- After validation and logging, commit and push in the same turn unless the user explicitly says not to.
- If unrelated local changes exist, do not revert them. Stage only the files relevant to the current task when possible.
- If commit or push is blocked, report the blocker clearly instead of leaving the task in a half-finished state.

## Scope And Exceptions

- Follow direct user instructions over this guide when the user explicitly asks for plan-only work, analysis-only work, no-commit work, or no-push work.
- For review-only requests, findings come first; commit and push are not implied unless the user asks for changes.
- For trivial read-only questions, no logging or git action is required.

## Communication Preference

- Prefer concise Chinese updates and summaries for this repository.
- When user-visible behavior changes, mention what changed, how it was validated, and whether anything remains as a follow-up watch item.
