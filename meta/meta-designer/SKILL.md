---
name: meta-designer
description: Turns a spec into a build-ready design.md plus a real artifact (HTML mockup or Mermaid wireframe) — component reuse-vs-new audit, real token names, breakpoints, and all four screen states as testable ACs. Trigger on "design this UI", "write design.md", "what components/tokens should this screen use", "spec out the screen states for X", or when a kestra-build design stage names a designer skill.
---

# meta-designer — UI Design Handoff

**Role:** Produce a design so clear that Dev can implement it without guessing about components, colors, or layout.

The UI-design role in the meta-* library — relevant when the spec sets `needs_ui: true`. Self-contained — use directly whenever a feature needs a UI spec before implementation. Note that `kestra-spec` already writes tables-only Design Notes into `0-spec.md`; what this skill adds beyond those is the **artifact** (something openable and inspectable) and the review gate that checks the artifact against reality — so when both exist, build on the spec's notes rather than re-deriving them, and keep the two consistent.

---

## Inputs to read (in order)

1. `0-spec.md` — feature intent, ACs, any Business Rules section (permission-gated fields, conditional flows, role-based states all change the UI)
2. `CLAUDE.md` — stack, existing component library paths, token locations

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

## Output: `design.md`

Every section of the template below is required — it doubles as the readiness checklist, so a section you can't fill honestly is the signal that the design isn't ready, not something to leave blank.

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
