# Handoff

End-of-session ritual: review, commit, push, and summarize.

## Steps

1. Run `git status` and `git diff --stat` to see all changes.
2. Stage all modified tracked files. New pages the generator created under `protocols/`
   are expected; stage them too. Do not stage any other untracked file without
   confirming with the user (every file in this repo is publicly served).
3. If the generator was run this session, run `python rp_verify.py` and confirm
   `ALL CHECKS PASSED` before committing.
4. Commit with a concise, descriptive message summarizing the work done this session.
5. Push to `master`. If the push is rejected because the weekly popularity workflow
   pushed first, rebase (see CLAUDE.md, Usage tags) and push again.
6. Output a handoff summary:
   - **Files changed**: list each file and what changed
   - **Commits made**: commit hash(es) and messages
   - **What's next**: any known pending tasks or follow-ups
   - **Blockers**: anything unresolved or that needs user input
