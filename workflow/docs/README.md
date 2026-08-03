# workflow/docs/ — diagrams and reference material

Supporting documentation for the `kestra-spec` → `kestra-build` → `kestra-run` pipeline. Nothing
here is loaded by a skill at runtime — these files exist for people reading the pipeline, not for
an agent executing it. Each skill's own behaviour lives in its `SKILL.md` and `references/`.

## Contents

| File | What it covers |
|------|----------------|
| [`kestra-sequence.md`](kestra-sequence.md) | Five mermaid sequence diagrams of the full pipeline — see below |

## `kestra-sequence.md`

The end-to-end call sequence, in five diagrams:

1. **Overview** — idea → `kestra-spec` → `kestra-build` → `kestra-run`, and what each hands the next
2. **The main loop** — `kestra-run`'s per-stage cycle: test-hash check, context pack, spawn, then
   mechanical verification
3. **On pass** — the freeze point, the metrics record, and commit-per-stage as the rollback point
4. **On fail** — the bounded `fixing` retry loop and its escalation to `reworking`, the one
   guaranteed human stop
5. **The three primitives** — why `generate-tests` and `freeze-tests` are separate stages, and how
   the write-scope allowlist keeps `fixing` out of test paths

These are a companion to [`../README.md`](../README.md), which describes the same pipeline in prose,
and to [`../kestra-run/references/enforcement.md`](../kestra-run/references/enforcement.md), which
carries the exact commands the diagrams summarise.

## Editing the diagrams

Mermaid rejects raw `<...>` and `<br/>` inside a message label, so placeholders are written as plain
words rather than angle brackets. Validate any change before committing — a broken chart renders as
a parse error, not a diagram:

```bash
npx -y -p @mermaid-js/mermaid-cli@11 mmdc -i workflow/docs/kestra-sequence.md -o /tmp/check.md
```

All five charts must report `✅`. The SVGs it writes are throwaway; delete them.
