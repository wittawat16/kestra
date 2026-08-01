# meta-spec — Sonnet 5 vs Opus 5 (2026-08-01)

**Question this was built to answer:** `meta-spec` is deliberately lean, and the thing that makes it
safe to default to is its **escalation check** — its own admission that some work belongs in a
heavier spec pass. That check is the skill's load-bearing part. Does it actually fire on a task
engineered to be *borderline*, and does the model behind it change the answer?

Companion to `workflow/evals/2026-07-31-spec-model-compare/` (same question for `kestra-spec`) and
`meta/evals/2026-08-01-review-model-compare/` (same question for `meta-review`).

## Setup

Identical prompt, identical fixture, both inheriting the session's effort — only the model varied.
The ask was written to sound routine:

> "Prices are slow — every catalog page load hits the pricing service once per SKU... Add a cache in
> front of the pricing lookup so repeat lookups are instant. And put a 'Refresh prices' button on the
> admin catalog page so our ops staff can clear the cache themselves..."

`fixture/` is a small Node ESM service with a `CLAUDE.md` stating real conventions. Two traps are
built into it:

* **Path invention.** There is no `src/pricing.js` and no `src/cache.js`. The pricing lookup actually
  lives at `src/catalog/rates.js`. A model that reasons instead of surveying will name a file that
  doesn't exist.
* **A borderline escalation trigger.** A cache serving a stale price is a candidate silent failure,
  but a TTL arguably bounds it — so "escalate" is not automatically the right answer. The question is
  whether the check engages seriously, not which way it lands.

## Result

| Criterion | Sonnet | Opus |
|---|---|---|
| Invented a non-existent path | ✅ none | ✅ none |
| Followed `CLAUDE.md` (`lib/http.js`, `renderPage`) | ✅ | ✅ |
| `needs_ui` set mechanically (a button qualifies) | ✅ true | ✅ true |
| `tests_first` stayed false (caller didn't ask) | ✅ | ✅ — plus an explicit *recommendation* to enable it, exactly the "recommend, don't set" behavior the skill asks for |
| Cache keyed `(sku, currency)`, not SKU as the ask literally said | ✅ | ✅ |
| Failures must not be cached | ✅ | ✅ |
| Noticed the repo has no router/server to mount a POST route on | ✅ Open Item | ✅ Open Item |
| Unauthenticated cache-clear = free cache-buster against the pricing service | ❌ not raised | ✅ raised as blocking |
| **Per-process cache: "Refresh prices" clears one instance of N** | ❌ **not raised** | ✅ **conditional escalation** |
| `needs_devops` | false — TTL hardcoded | true — TTL + max-entries as env vars |

Cost: **Sonnet 146,104 tokens / 15 tool calls / 178s. Opus 137,263 tokens / 12 tool calls / 178s.**
Opus was ~6% cheaper in tokens at identical wall-clock — the same direction as the `meta-review`
run, and the opposite of the `kestra-spec` run where Opus cost ~14% more.

## The finding that separates them

Both engaged the silent-failure trigger. They asked different questions of it.

**Sonnet asked whether the cache can go stale forever**, answered no because of the TTL it had just
specified, and concluded the trigger doesn't fire:

> "With a TTL in place, staleness is bounded and self-correcting, not silent-forever, so this doesn't
> rise to `kestra-spec`'s runtime-invariant bar."

That reasoning is correct about the thing it examined.

**Opus asked whether the refresh button does what it reports.** An in-process `Map` is per-process, so
with N instances behind a load balancer the POST clears exactly one of them — ops sees a success
page while the other N−1 keep serving stale prices for a full TTL, and nothing reports the
discrepancy. That is the escalation trigger's own definition, and it survives the TTL argument
entirely, because the defect isn't unbounded staleness — it's a success signal that isn't true.

What makes this the strong result is that Opus **didn't resolve it either**. The fixture has no
Dockerfile, deploy manifest, or scaling hint, so instance count can't be read from the repo. It
made the escalation conditional and put instance count at the top of Open Items as blocking: single
instance → this spec is correctly sized; multiple → stop and escalate, and here is specifically
what the heavier pass would need to carry (approach comparison, integration contract, an invariant
that a refresh either reaches every instance or is reported as partial). An honest unknown, in the
place the skill reserves for one.

Sonnet's spec ends with `Open Items` too — three of them, all real. Instance count isn't among them.

## What this says

The escalation check is doing real work on both models — neither rubber-stamped, and both produced
specs an implementer could build from. But on this task the cheaper model's check **passed while
missing the condition that should have triggered it**, and passed for a reason that reads as
thorough: it named the silent-failure risk, mitigated it, and showed its work. A spec that
under-covers silent failure while looking diligent is the exact failure `meta-spec`'s Mindset
section warns about, and here it is, produced by the skill itself.

Note how this differs from the `meta-review` comparison, where Sonnet caught every blocking defect.
The defects there were *in a diff*, findable by reading and probing what was in front of it. The
defect here is a property of deployment topology that appears nowhere in the code — reachable only
by asking what happens outside the file. That is the same shape as the `kestra-spec` finding
(a spread-order trap only visible by running a prototype): both times, the gap showed up on the
question the artifact under examination doesn't contain the answer to.

**How to apply:** prefer Opus for `meta-spec` where the feature has deployment-topology or
process-lifetime implications — caches, in-memory state, schedulers, anything whose correctness
depends on how many copies are running. It cost less than Sonnet on this run, so there's little to
weigh against it. n=1, one task.

## Files

* `fixture/` — the repo both surveyed (`CLAUDE.md` + four source files)
* `sonnet/0-spec.md`, `opus/0-spec.md` — the two specs
