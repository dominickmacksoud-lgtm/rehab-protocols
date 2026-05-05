# Handoff

End-of-session ritual: review, commit, push, and summarize.

## Steps

1. Run `git status` and `git diff --stat` to see all changes.
2. Stage all modified tracked files. Do not stage untracked files without confirming with the user.
3. Commit with a concise, descriptive message summarizing the work done this session.
4. Push to `master`.
5. Output a handoff summary:
   - **Files changed**: list each file and what changed
   - **Commits made**: commit hash(es) and messages
   - **What's next**: any known pending tasks or follow-ups
   - **Blockers**: anything unresolved or that needs user input
