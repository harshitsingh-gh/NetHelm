# /week-check — Weekly Status Check Against Execution Plan

Check the current week's deliverables against the execution plan, identify what's done vs pending, flag blockers, and suggest the next 3 actions to take.

## Process

1. Read `progress.md` to understand what has been logged as completed.

2. Read `paper/refs/nethelm_execution_plan.md` — find the current week (today is in the context).

3. Check the deliverables checklist for the current week by examining:
   - Files that should exist per the plan (committed in git)
   - Experiment outputs that should exist in `runs/`
   - Notes that should exist in `reading/` or `harness/grader_notes/`
   - Run: `git log --oneline -20` to see what's been committed
   - Check existence of specific deliverable files

4. For each deliverable, determine: **DONE / IN PROGRESS / NOT STARTED / BLOCKED**

5. Check if the current week is on track, ahead, or behind.

6. Output:
   ```
   ## Week [N] Status — [date range]
   
   ### Deliverables
   - [x] Done: [deliverable] — [commit or file evidence]
   - [~] In progress: [deliverable] — [what remains]
   - [ ] Not started: [deliverable]
   - [!] BLOCKED: [deliverable] — [blocker description]
   
   ### Verdict: ON TRACK / BEHIND [X days] / AHEAD
   
   ### Active blockers
   [list]
   
   ### Next 3 actions (in priority order)
   1. [action] — [why it's first / what it unblocks]
   2. [action]
   3. [action]
   
   ### Slip risk
   [anything that could slip the week further, with mitigation]
   
   ### Decision points triggered
   [any kill-criteria from Appendix B of the execution plan that apply]
   ```

## Usage
- `/week-check` — check current week
- `/week-check phase` — summarize entire phase status
- `/week-check summer` — check against the Aug 23 end-of-summer milestone checklist (Appendix D)
