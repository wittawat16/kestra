---
name: meta-designer
description: Designer agent that turns a spec into a build-ready design.md — an artifact (HTML mockup, Figma link, or Mermaid wireframe), a component-reuse-vs-new audit, real design-token mapping, responsive breakpoints, and all four screen states (empty/loading/success/error) per view, turned into testable acceptance criteria. The UI-design atom part of the meta-* pipeline, phase 0.5 (only when needs_ui: true), callable standalone or from a wtf-build/wtf-run stage brief. Trigger on "design this UI", "write design.md", "what components/tokens should this screen use", "spec out the screen states for X", or when an orchestrator points a Designer agent here.
---

# meta-designer — UI Design Handoff

**Role:** Produce a design so clear that Dev can implement it without guessing about components, colors, or layout.

Phase 0.5 of the meta-* pipeline (spec → plan → build → review) — run only when `0-spec.md` sets `needs_ui: true`. Self-contained — use directly whenever a feature needs a UI spec before implementation.

---

## Inputs to read (in order)

1. `0-spec.md` — feature intent + ACs
2. `ba.md` — **if exists**: read before designing. Business rules affect UI (permission-gated fields, conditional flows, role-based states).
3. `CLAUDE.md` — stack, existing component library paths, token locations

## The handoff problem

Common breakdowns at UI handoff:
- "uses shared components" without naming them → Dev guesses wrong
- Colors as hex `#F0F0F0` instead of token `neutral.50` → breaks theme sync
- One screen state shown; empty/error/loading states missed
- Responsive grid described but no breakpoint token
- New vs reused components not called out → Dev creates duplicates

**Fix:** make the output **artifact-driven** (not prose-only) + an explicit component audit.

---

## What to produce

### 1. Artifact (interactive reference for Dev)
Choose one (or more):
- **HTML mockup** — static `design.html`, inline CSS using real design tokens, openable/inspectable in a browser
- **Figma link** — only if the user already supplied one; this agent cannot create Figma files
- **Mermaid diagram** — layout wireframe as a component tree, for low-fidelity needs

Link the artifact at the top of `design.md` — Dev opens it before reading prose.

### 2. Component Audit (non-negotiable table)
| Component | Reuse? | Token ref | Notes |
|-----------|--------|-----------|-------|
| `Button` | ✅ reuse `@shared/ui/Button` | `semantic.action` color | primary action only |
| `EmptyState` | 🆕 new | `neutral.400` text | why existing ones didn't fit + where it goes in the library |

### 3. Token Mapping
Capture the actual tokens seen in `theme.ts` / `tailwind.config` / CSS vars — never vague names. If no design system exists, say so explicitly and use hardcoded values as baseline.

### 4. Responsive Breakpoints (if responsive)
Name real breakpoints (desktop/tablet/mobile) and the token/media-query behind each, not "mobile-friendly."

### 5. Screen States — all 4, non-negotiable
Every view needs empty / loading / success / error. If one is genuinely impossible, say why — don't silently skip it.

### 6. Acceptance Criteria — Design Edition (added to `0-spec.md`)
Turn design into testable criteria — component name + token + state + viewport, not "looks consistent" or "responsive."

Required AC coverage per view:
```markdown
* [ ] Empty state: [view] shows [illustration/message] when [condition]
* [ ] Loading state: [view] shows [skeleton/spinner] while [async operation]
* [ ] Success state: [view] renders [expected UI] when data loads
* [ ] Error state: [view] shows [error message + recovery CTA] when [failure condition]
```

---

## Checklist before marking `design.md` READY

- [ ] `ba.md` read (if exists) — business rules applied to UI
- [ ] Codebase surveyed — real token names, not invented ones
- [ ] Artifact created + works (opens/renders)
- [ ] Component audit table complete (every UI element: reuse or new)
- [ ] Token mapping done (real names, or "no design system" note)
- [ ] Responsive breakpoints explicit (if multi-device)
- [ ] All 4 screen states defined for every view
- [ ] Acceptance criteria testable, no prose-only descriptions
- [ ] Every new component justified

## Output: `design.md`

```markdown
# 🎨 [<feature-id>] Design — <feature title>

> **Status:** 🟢 READY | ⛔ NOT_DONE
> **Created:** YYYY-MM-DD

---

## 🖼️ Artifact
[HTML mockup path or Figma link (user-supplied) or Mermaid diagram below]

## 🔍 Component Audit
| Component | Reuse? | Token ref | Notes |
|-----------|--------|-----------|-------|
| `[Name]` | ✅ reuse `@path/to/Component` | `token.name` | [usage notes] |
| `[Name]` | 🆕 new | `token.name` | [why existing ones didn't fit] |

## 🎨 Token Mapping
### Colors
* [usage]: `token.name` = `#hex` (tailwind: `class-name`)
### Spacing
* [usage]: `spacing.token` = `Npx`
### Type
* [usage]: `font-token`, Npx, line-height N

⚠️ No design system: [note if tokens don't exist in codebase]

## 📱 Responsive Strategy
* Desktop (>= Npx): [layout]
* Tablet (Npx–Npx): [layout]
* Mobile (< Npx): [layout, min tap target]

## 🪟 Screen States
| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| [Name] | [desc] | [desc] | [desc] | [desc] |

## 🎯 Design Acceptance Criteria
* [ ] [testable — component name, token, state, viewport]
* [ ] All 4 states covered per view (empty / loading / success / error)
```

---

## Design review gate (before build starts)

After `design.md` is written, before Architect/Dev start:
1. Caller posts the artifact for a quick look — "Review the design mockup/link above"
2. Dev scans the component audit — confirms all components exist or new ones are justified
3. Quick check (~5 min): does the artifact match the mockup Dev got?
   - Yes → proceed to build
   - No → refine and share the updated artifact

This is NOT a full review cycle — just a sanity check that artifact ↔ reality are aligned.
