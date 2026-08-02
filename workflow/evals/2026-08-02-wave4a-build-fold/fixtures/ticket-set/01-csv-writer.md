## What to build
The CSV writer: the header row, RFC 4180 quoting, and the header-only shape for an empty result
set. Nothing HTTP-facing — the writer takes rows and yields text.

## Acceptance criteria
- [ ] AC-2 an export of an empty result set returns a header-only CSV (Source: US-1)
- [ ] AC-4 a cell containing a comma or a quote is quoted per RFC 4180

## Blocked by
- nothing
