# Notes for Claude sessions working on this repository

More than one Claude session works on this codebase and pushes to `main`. Fetch and merge before
pushing, and keep the product decisions below unless the owner asks to change them.

## Product decisions

### Long-term goals use a weekly spending limit, not milestones (decided 2026-11-28)

Findings from the company check come in two kinds (`horizon` on each finding):

- **Quick fix** (`quick`): a one-off job Oton finishes in days (a launch video, analytics, a
  directory listing). One goal with a fixed one-time cost ("Fix it now", "$4 one-time cost").
- **Long-term goal** (`ongoing`): a result that needs steady work (followers, rankings, reviews,
  meetings). It shows the **objective** ("10K+ followers across LinkedIn and X"), what Oton
  **keeps doing** every week, and **"Up to $X a week"**. The goal runs until it's stopped and never
  spends more than its weekly limit (`Campaign.weekly_cap`, Monday to Sunday UTC; enforced in
  `app/services/ledger.py`; when it's used up the goal waits for Monday instead of stopping).

Don't bring back milestones (a quick step 1, then longer steps) for long-term goals in new checks.
Older findings saved with milestones still display. At least one finding should be long-term,
chosen from evidence of what the company cares about (see `STRUCTURE_SYSTEM` in
`backend/app/agent/opportunities.py`).
