---
status: accepted
---

# Acceptance Criteria joins the requirement surface (extractor v2)

The requirement surface deliberately excluded `## Acceptance Criteria`, on the theory that the
`AC Coverage Map` is their canonical paraphrase, so hashing the map hashed the ACs
(`workflow/kestra-build/scripts/requirement_surface.py`, the boundary docstring at v1). The theory
does not survive the specs this repo ships: `workflow/kestra-spec/SKILL.md:496` permits the map's
`AC` cell to be `[ac id / text]`, and `workflow/runs/install-check/0-spec.md:149-158` took the
id-only reading (`AC-1`…`AC-8`), as did `workflow/runs/install-check/tickets/issue-41.md:15-22`. On
an id-only spec every word of AC text can be rewritten — inverted — with the hash unmoved and every
downstream gate still reporting FRESH. So `## Acceptance Criteria` is now in the surface and
`EXTRACTOR_VERSION` goes 1 → 2.

This was measured, not inferred: `workflow/evals/2026-08-03-wave4b-run-slim/README.md:42-46`
records a leg editing a Given-When-Then bullet and then appending a whole new AC, with the hash
unmoved both times, and excusing it as the deliberate boundary. `test_requirement_surface.py`
shipped that behavior as a *passing* test.

## Considered Options

**A `validate_spec.py` check requiring the map's `AC` cell to carry text** — rejected. It leaves the
Given-When-Then section itself unhashed, so closing the hole would need a parity check between
multi-line GWT text and a one-cell paraphrase: new fragile machinery at the one boundary this repo
insists has a single owner (`requirement_surface.py`, the "a second implementation of the boundary
anywhere is the failure this module exists to prevent" docstring).

## Consequences

- v1 and v2 hashes are not comparable, by rule. `validate_workflow.py` FAILs and `exam_anchor.py`
  REFUSES on a version mismatch, so anything that recomputes against the v2 skill copy refuses until
  re-derived. That refusal is the intended behavior, not a regression to route around.
- The committed v1 anchors stay internally verifiable, because each folder vendors its own v1
  extractor: `workflow/runs/install-check/workflow.yaml`, the wave4a eval's fixture workflow, and
  wave3's exam manifest/pointer/`exam.py`. Nothing is in flight — install-check is complete and
  `workflow/runs/order-cancellation-refund` has never left `pending`.
- A bare id in the `AC` cell becomes harmless, and the Coverage Map returns to being a pure mapping
  table: identity and text now come from the Acceptance Criteria section, so the map's only job is
  AC → Source.
- Residual, stated so nobody assumes otherwise: `ac_hash` is computed from Coverage Map rows only
  (`workflow/kestra-build/references/ticket-fold.md:157-161`), so this bump moves no `ac_hash`, and a
  per-slice `ac_hash` on an id-only spec still will not move when AC text is rewritten.
