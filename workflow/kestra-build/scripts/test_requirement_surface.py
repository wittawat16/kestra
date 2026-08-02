#!/usr/bin/env python3
"""Deterministic fixture tests for requirement_surface.py — no LLM, no network.

Run:  python3 test_requirement_surface.py     (exit 0 on pass, 1 on failure)

Fixtures are inline, not the repo's real specs: this seam must keep answering
the same way when workflow/runs/*/0-spec.md is later repaired or regrown.
Uses stdlib unittest purely for the runner and its exit code; the assertions
are on external behavior only — hashes, section sets, exposed rows, raises.
"""
import unittest

from requirement_surface import SURFACE_SECTIONS, SurfaceError, extract_surface

# Today's shape: emoji headings, no External Interface, no Source column.
TODAY = """# [demo] Spec — Demo

## \U0001f959 Functional Requirements
* [ ] Customer can cancel any order in `paid` status.
* [ ] **Given** a shipped order
      **When** the customer cancels
      **Then** the cancellation is rejected.

## \U0001f324️ Edge Cases & Error States
* **Refund call fails:** order stays in `paid`, never half-cancelled.

## \U0001f6e1️ Runtime Invariants
| Invariant | Detected at runtime by | On violation |
|-----------|------------------------|--------------|
| Refund and release both apply or neither | Saga boundary | Halt and alert |

## \U0001f4dc Business Rules  *(needs_ba: true)*
* **BR-1 — Only pre-shipment orders are cancellable.**

## \U0001f3af Acceptance Criteria
* [ ] Cancelling a paid order refunds it in full

## \U0001f3af AC Coverage Map
| AC | Covered by (files/steps) |
|----|--------------------------|
| Pre-shipment cancel refunds in full | BR-1, BR-3 |
| Post-shipment cancel rejected | BR-1 |

## ⚠️ Risks & Watch-outs
* Refund and inventory release must be atomic.
"""

# Grown Wave-2 shape: plain headings, External Interface, Source column.
GROWN = """# [console] Spec — Console

## Overview

Loopback-bound console over the retry queue.

## External Interface

* **Primary (new): HTTP boundary.** Driven by platform `fetch`.
  * `GET /` — console page.

## Functional Requirements

* [ ] Console page shows pending count (US-1).
* [ ] Rows capped at `ROW_CAP = 200` (US-13).

## Edge Cases & Error States

* **Queue empty:** the page says so rather than rendering an empty table.

## Runtime Invariants

| Invariant | Detected at runtime by | On violation |
|-----------|------------------------|--------------|
| Summary and rows describe one moment | Single synchronous pass | Refuse to render |

## Acceptance Criteria

* [ ] **AC-1** Given a queue, Then the page shows the pending count.

## AC Coverage Map

| AC | Source | Covered by (files/steps) |
|----|--------|--------------------------|
| AC-1 | US-1, US-2 | `src/console.js` summary builder |
| AC-2 | US-3 | `src/console.js` Set over `pending` |

## Out of Scope

* Pager controls.
"""


def h(text):
    return extract_surface(text).surface_hash


class Boundary(unittest.TestCase):

    def test_both_shapes_extract(self):
        today = extract_surface(TODAY)
        self.assertEqual(set(today.sections),
                         set(SURFACE_SECTIONS) - {"External Interface"})
        self.assertEqual([r[0] for r in today.ac_rows],
                         ["Pre-shipment cancel refunds in full",
                          "Post-shipment cancel rejected"])

        grown = extract_surface(GROWN)
        self.assertEqual(set(grown.sections), set(SURFACE_SECTIONS))
        self.assertEqual(grown.ac_rows,
                         [("AC-1", "AC-1 | US-1, US-2"), ("AC-2", "AC-2 | US-3")])

    def test_out_of_surface_sections_never_leak(self):
        for out in ("Business Rules", "Acceptance Criteria", "Risks", "Overview",
                    "Out of Scope", "BR-1", "atomic", "Pager"):
            self.assertNotIn(out, extract_surface(TODAY).text + extract_surface(GROWN).text)


class Fences(unittest.TestCase):

    def test_fenced_heading_never_truncates(self):
        fenced = TODAY.replace(
            "* [ ] Customer can cancel any order in `paid` status.",
            "* [ ] Customer can cancel any order in `paid` status.\n"
            "```\n## Runtime Invariants\n## AC Coverage Map\n```",
        )
        surface = extract_surface(fenced)
        # Every real section still found, and the fenced text landed in FR.
        self.assertEqual(set(surface.sections), set(extract_surface(TODAY).sections))
        self.assertEqual(len(surface.ac_rows), 2)
        self.assertIn("## Runtime Invariants", surface.sections["Functional Requirements"])
        # ...and it is content, so it moved the hash.
        self.assertNotEqual(h(fenced), h(TODAY))

    def test_tilde_fence_and_info_string(self):
        fenced = TODAY.replace(
            "* **Refund call fails:** order stays in `paid`, never half-cancelled.",
            "~~~python\n## Edge Cases & Error States\n~~~",
        )
        self.assertEqual(set(extract_surface(fenced).sections),
                         set(extract_surface(TODAY).sections))

    def test_unclosed_fence_fails_loudly(self):
        with self.assertRaises(SurfaceError):
            extract_surface(TODAY.replace("## \U0001f3af AC Coverage Map",
                                          "```\n## \U0001f3af AC Coverage Map"))


class Normalization(unittest.TestCase):

    def test_checkbox_list_prefix_and_whitespace_are_not_content(self):
        variant = (TODAY
                   .replace("* [ ] Customer can cancel", "- [x] Customer   can cancel")
                   .replace("* [ ] **Given** a shipped order",
                            "+ [X]  **Given** a shipped order")
                   .replace("      **When** the customer cancels\n"
                            "      **Then** the cancellation is rejected.",
                            "  **When** the customer cancels **Then** the "
                            "cancellation is rejected.")
                   .replace("| Pre-shipment cancel refunds in full | BR-1, BR-3 |",
                            "|  Pre-shipment cancel refunds in full  |BR-1, BR-3|"))
        self.assertNotEqual(variant, TODAY)
        self.assertEqual(h(variant), h(TODAY))

    def test_prose_edit_outside_the_surface_hashes_identical(self):
        edited = (TODAY
                  .replace("* **BR-1 — Only pre-shipment orders are cancellable.**",
                           "* **BR-1 — Only unshipped orders are cancellable.** Rewritten.")
                  .replace("* [ ] Cancelling a paid order refunds it in full",
                           "* [x] Cancelling a paid order refunds the uncredited balance")
                  .replace("* Refund and inventory release must be atomic.",
                           "* Nothing risky here after all."))
        self.assertNotEqual(edited, TODAY)
        self.assertEqual(h(edited), h(TODAY))

    def test_coverage_map_column_order_is_not_content(self):
        reordered = (GROWN
                     .replace("| AC | Source | Covered by (files/steps) |",
                              "| Source | AC | Covered by (files/steps) |")
                     .replace("| AC-1 | US-1, US-2 |", "| US-1, US-2 | AC-1 |")
                     .replace("| AC-2 | US-3 |", "| US-3 | AC-2 |"))
        self.assertNotEqual(reordered, GROWN)
        self.assertEqual(extract_surface(reordered).ac_rows,
                         extract_surface(GROWN).ac_rows)
        self.assertEqual(h(reordered), h(GROWN))

    def test_coverage_map_covered_by_column_is_out_of_surface(self):
        self.assertEqual(h(GROWN.replace("`src/console.js` summary builder",
                                         "`src/summary.js` builder, moved")), h(GROWN))

    def test_section_reorder_and_heading_decoration_are_not_content(self):
        undecorated = TODAY.replace("## \U0001f959 Functional Requirements",
                                    "## Functional Requirements")
        self.assertNotEqual(undecorated, TODAY)
        self.assertEqual(h(undecorated), h(TODAY))

        edge = GROWN[GROWN.index("## Edge Cases"):GROWN.index("## Runtime Invariants")]
        reordered = GROWN.replace(edge, "").replace(
            "## Acceptance Criteria", edge + "## Acceptance Criteria")
        self.assertNotEqual(reordered, GROWN)
        self.assertEqual(h(reordered), h(GROWN))


class RealChanges(unittest.TestCase):

    def test_real_content_change_moves_the_hash(self):
        cases = {
            "requirement reworded": TODAY.replace("in `paid` status", "in any status"),
            "edge case removed": TODAY.replace(
                "* **Refund call fails:** order stays in `paid`, never half-cancelled.", ""),
            "invariant weakened": TODAY.replace("Halt and alert", "Log and continue"),
            "AC row removed": TODAY.replace("| Post-shipment cancel rejected | BR-1 |", ""),
            "AC row reworded": TODAY.replace("Post-shipment cancel rejected",
                                             "Post-shipment cancel allowed"),
        }
        for label, edited in cases.items():
            with self.subTest(label):
                self.assertNotEqual(h(edited), h(TODAY))

    def test_source_column_change_moves_the_hash(self):
        self.assertNotEqual(h(GROWN.replace("| AC-1 | US-1, US-2 |", "| AC-1 | US-1 |")),
                            h(GROWN))


if __name__ == "__main__":
    unittest.main()
