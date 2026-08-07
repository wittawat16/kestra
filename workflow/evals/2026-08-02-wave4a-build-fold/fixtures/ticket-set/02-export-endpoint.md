## What to build
The `GET /orders/export` endpoint and the one-job-per-(filter, day) enqueue guard. Returns whatever
the writer produces.

## Acceptance criteria
- [ ] AC-1 a completed export returns 200 with a text/csv body
- [ ] AC-3 two concurrent exports for one filter produce one job

## Blocked by
- 01-csv-writer (the endpoint returns what the writer produces — see #47 for why the split is here)

## Parent
- issues/37
