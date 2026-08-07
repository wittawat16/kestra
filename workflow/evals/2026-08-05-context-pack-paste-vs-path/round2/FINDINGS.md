# Round 2 — does the answer change when the spec is bigger?

Round 1 concluded that a path-only pack saves nothing because the agent reads the file anyway. The
obvious objection: the spec was small (10,135 chars), so the whole argument lived inside a ~2%
slice of a spawn. Round 2 re-runs the same design against a spec 2.9× the size.

## Setup

`round2/0-spec-large.md` — 29,499 chars: a reversal engine with 7 external dependencies, 12
business rules, 24 edge cases, 30 acceptance criteria, a state machine, a reason-code table and a
notification matrix. Pack sizes: 30,371 chars (arm A) vs 968 (arm B) — a 31× ratio, against 12× in
round 1.

**The probe is sharper than round 1's.** The ticket brief carries AC-4 verbatim — "the customer
sees a retry-able error" — while the spec states in three separate places that a provider timeout
is an *unknown* outcome that must park in `pending_verification` and be retried from no path. An
agent working from the brief alone doesn't merely miss a nuance; it implements exactly what the
brief tells it to, and reintroduces double refunds.

**Third measure added:** whole-file vs. partial read, since partial reading is the only mechanism by
which a path-only pack could actually be cheaper.

## Results

| Stage | Arm | Probe | Read style | Tokens | Wall |
|---|---|---|---|---|---|
| implement | A — paste | 3/3 | n/a | 133,518 | 35.8s |
| implement | B — path | 3/3 | whole-file ×3 | 133,769 (+251) | 41.0s |
| review | A — paste | 3/3 | n/a | 134,592 | 46.7s |
| review | B — path | 3/3 | whole-file ×2, **partial ×1** | 135,089 whole / **126,847 partial** | 51.3s |

Probe caught 12/12 in round 2, 12/12 in round 1 — 24/24 across both sizes and both arms.

## What changed, and what didn't

**Quality: still no difference.** Every path-only run opened the spec, and every one of them found
the AC-4-vs-EC-1 contradiction and resolved it toward EC-1 — several flagged the tension explicitly
as a conflict worth naming rather than silently picking a side. Tripling the spec did not tempt any
run into working off the thin brief.

**Cost: unchanged wherever the file was read whole.** +251 tokens on implement, +497 on the two
whole-file review runs. Same result as round 1, same mechanism: the pack shrank by ~7.5k tokens and
the agent spent them anyway.

**One run read partially — and it is the only run in 24 that saved anything.** B-review-2 grepped
for the relevant sections, read lines 40–114, and came in at 126,847 tokens: **7,745 below** the
whole-file runs, ~5.8%. It caught the probe anyway.

That last point corrects something I argued before running this. I claimed selective reading
couldn't work because an agent can't know which section holds a fact it hasn't seen. This run
disproves it: grepping for the *concepts in the diff* — timeout, retry, idempotency — landed on the
sections that happened to carry the constraint, without knowing in advance that they did. The
argument was too strong.

## What this actually supports

1. **The behavioural worry is not supported at either size.** 24/24. On this model, "told where it
   is" was enough every time.
2. **The saving is real but rare and conditional.** It appeared once in 12 path-only runs, only at
   the larger size, only in the stage with the widest question, and it was ~6% of that run. Six
   percent of one run in twelve is not a cost argument; it is a hint about a mechanism.
3. **Frequency of partial reading is the variable worth studying**, not paste-vs-path. Partial reads
   went 0/6 at 10k chars to 1/6 at 29k. If that keeps climbing with size, the saving becomes real at
   some spec size — and finding that size is a sharper question than the one มติ 3 poses.
4. **Wall-clock is consistently worse for arm B** — +5.2s implement, +4.6s review in round 2, on top
   of round 1's +3.5s and +10.3s. A tool round-trip costs latency whether or not it costs tokens.

## Limits

* 2.9×, not the 4–5× intended. A spec large enough to force partial reading in most runs was not
  reached, so the mechanism's ceiling is unmeasured.
* Arm A's self-reported read style is unreliable — several runs answered "whole-file" for reading
  the pasted text inside the pack, not the file. Tool-use counts (2–3 for arm A, 4 for arm B) are
  the trustworthy signal, and they are what the table reflects.
* n=3 per cell. The single partial read is n=1 and should be read as an existence proof, not a rate.
* Still one model. The frozen-and-portable argument from round 1 stands unchanged.

## Recommendation, updated

Round 1's recommendation holds — keep the paste rule — but for a narrower reason than round 1 gave.
It is not that a path-only pack *cannot* be cheaper; one run showed it can. It is that the saving
arrives only when the agent happens to read selectively, which happened once in twelve tries, while
the latency penalty arrived every time.

If มติ 3 wants a cost case, the experiment that would make it is: find the spec size at which
partial reading becomes the norm rather than the exception, and check whether the probe still
survives at that size. That is a real question with a real answer, and it is not the question the
proposal currently argues.
