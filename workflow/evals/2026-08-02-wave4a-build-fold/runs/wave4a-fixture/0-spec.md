# [fx] Spec — CSV export of orders

> Status: READY_FOR_BUILD | Created: 2026-08-02 | Next: kestra-build
> Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/37
> Delimiter precondition: every '## ' at column 0 outside a code fence is a template section heading; no line inside a requirement-surface section body begins with '## '; subsections use '### '; every code fence is closed.

---

## Overview
Fixture spec for the wave-4a sliced-fold eval: small, conforming, chain-marked, with a five-row AC
Coverage Map that three sliced tickets partition exactly.

## External Interface
* `GET /orders/export?filter=<q>` — in: `filter` (query); out: `200` with `text/csv`; side effect: one export job per (filter, day). `US-1`
* Reused, not extended: the existing order query builder. `US-2`
* Deliberately absent seam: tests may not write CSV bytes through the HTTP layer. `NFR-1`
* Not an interface: `_quote_cell` (private). `⚠ inferred`
* No export is added solely to make something testable.

## Problem Statement
Support exports orders by hand; two people asking at once produce two jobs and two different files. `US-1`

## Functional Requirements
* FR-1 One export job per (filter, day), whatever the request count. `US-2`
* FR-2 CSV cells are quoted per RFC 4180. `ID§csv-quoting`
* FR-3 Exports above 10000 rows stream rather than buffer. `NFR-1`

## Edge Cases & Error States
* Empty result set → `200` with a header-only body, never `204`. `US-1`
* A cell containing a comma or a quote → quoted, inner quotes doubled. `ID§csv-quoting`

## Runtime Invariants
| Invariant | Checked where | On violation |
|---|---|---|
| One export job per (filter, day) | the enqueue path | reject with `409`, never silently drop the second |
| The response never buffers the whole result set | the stream writer | raise, never truncate the body |

## Reality Constraints
* The object store does not guarantee read-after-write for a freshly written export. `⚠ inferred`

## Files to Touch
| File | Change | Why |
|---|---|---|
| *(none — illustrative fixture spec, no repo attached)* | — | this eval grades the fold, not a codebase |

## Acceptance Criteria
* AC-1 Given a filter matching rows, When `GET /orders/export`, Then `200` with a `text/csv` body. `US-1`
* AC-2 Given a filter matching nothing, When the export runs, Then the body is the header row alone. `US-1`
* AC-3 Given two concurrent requests for one filter, When both enqueue, Then one job exists. `US-2`
* AC-4 Given a cell containing a comma or a quote, When it is written, Then it is quoted per RFC 4180. `ID§csv-quoting`
* AC-5 Given a result set above 10000 rows, When the export runs, Then the body streams. `NFR-1`

## AC Coverage Map
| AC | Source | Covered by (files/steps) |
|---|---|---|
| AC-1 a completed export returns 200 with a text/csv body | US-1 | tests/csv_export/test_api.py::test_export_ok |
| AC-2 an export of an empty result set returns a header-only CSV | US-1 | tests/csv_export/test_writer.py::test_header_only |
| AC-3 two concurrent exports for one filter produce one job | US-2 | tests/csv_export/test_api.py::test_single_job |
| AC-4 a cell containing a comma or a quote is quoted per RFC 4180 | ID§csv-quoting | tests/csv_export/test_writer.py::test_quoting |
| AC-5 an export above 10000 rows streams instead of buffering | NFR-1 | tests/csv_export/test_stream.py::test_streams |

## Flags
* needs_ba: false · needs_ui: false · needs_sa: false

## Exit Criteria
**Stop condition:** AC-1 … AC-5 pass — **or** two consecutive attempt rounds pass without the
progress number below moving, at which point stop and summon the human rather than attempt a third.

* progress: number of failing assertions reported by `python3 -m pytest tests/csv_export/test_writer.py`
  — must reach 0, from a baseline of 3 failing / 0 passing.
* progress: number of failing assertions reported by `python3 -m pytest tests/csv_export` — must reach 0, from a baseline of 9 failing / 0 passing.
* Single-shot, no progress number: the RFC 4180 golden-file comparison.

## Mode Prediction
* **kestra-build mode:** `full` — three slices, two independent components, one shared writer.

## Open Items
* none.
