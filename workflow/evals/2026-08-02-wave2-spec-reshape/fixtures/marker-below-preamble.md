# [fx] Spec — marker below the first '## '

> Status: READY_FOR_BUILD | Created: 2026-08-02 | Next: kestra-build
> Delimiter precondition: every '## ' at column 0 outside a code fence is a template section heading; no line inside a requirement-surface section body begins with '## '; subsections use '### '; every code fence is closed.

---

## Overview

> Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
Minimal fixture spec for validate_spec.py's chain-marker-conditional checks.

## External Interface
* `POST /fx/{id}` — in: `{id}` (path); out: `202` with `{job_id}`; side effect: one queued job. `US-1`
* Reused, not extended: the existing queue client. `US-1`
* Deliberately absent seam: tests may not drive the queue directly. `US-1`
* Not an interface: `_fx_enqueue_unsafe` (private). `⚠ inferred`
* No export is added solely to make something testable.

## Problem Statement
Re-submitting an id enqueues a duplicate job. `US-1`

## Functional Requirements
* FR-1 One queued job per id, whatever the submit count. `US-1`

## Edge Cases & Error States
* Duplicate id → `202`, no second job. `US-1`

## Runtime Invariants
| Invariant | Checked where | On violation |
|---|---|---|
| One queued job per id | enqueue path | reject with `409`, never silently drop |

## Reality Constraints
* The queue does not guarantee delivery order. `⚠ inferred`

## Files to Touch
| File | Change | Why |
|---|---|---|
| `workflow/kestra-build/scripts/validate_spec.py` | edit | the fixture needs one row whose path really exists |

## Acceptance Criteria
* AC-1 Given an unqueued id, When `POST /fx/{id}` twice, Then one job exists. `US-1`

## AC Coverage Map
| AC | Source | Covered by (files/steps) |
|---|---|---|
| AC-1 | US-1 | tests/test_fx.py::test_idempotent_enqueue |

## Flags
* needs_ba: false · needs_ui: false · needs_sa: false

## Exit Criteria
**Stop condition:** AC-1 passes — **or** two consecutive attempt rounds pass without the
progress number below moving, at which point stop and summon the human rather than attempt a third.

* progress: number of failing assertions reported by `python3 -m pytest tests/test_fx.py` — must
  reach 0, from a baseline of 1 failing / 0 passing.
* Single-shot, no progress number: the path-existence check in `validate_spec.py`.

## Mode Prediction
* **kestra-build mode:** `lite` — one file, one seam, no schema change.

## Open Items
* none.
