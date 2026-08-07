# Findings — full paste vs. path-only context pack

12 runs, Opus 5, 2026-08-05. Design in [README.md](README.md).

## Results

| Stage | Arm | Opened the spec | Probe caught | Tokens (mean) | Wall (mean) |
|---|---|---|---|---|---|
| implement | A — paste | 0/3 (had no reason to) | 3/3 | 125,527 | 34.1s |
| implement | B — path | **3/3** | **3/3** | 125,756 | 37.6s |
| review | A — paste | 0/3 | 3/3 | 126,441 | 38.5s |
| review | B — path | **3/3** | **3/3** | 126,649 | 48.8s |

Probe = the artifact treats a provider timeout as an ambiguous outcome needing reconciliation,
rather than assuming the refund did not happen. It appears only in the spec's "does **not**
guarantee" column, never in the ticket brief.

## What this settles, and what it doesn't

**The behavioural worry did not reproduce.** Every path-only run opened the spec unprompted, and
each said why in its own words — the ticket brief carried one acceptance criterion while the work
in front of it plainly reached further. Not one produced a plausible-looking artifact off the thin
brief. On this model, "told where it is" was enough.

**But the saving the change was made for did not appear either — and that is the finding.** Arm B
cost slightly *more*, not less: +229 tokens on implement, +208 on review, with all three B runs
above all three A runs in both stages (non-overlapping, though small against a ~125k fixed
overhead, so treat the magnitude as directional). Wall-clock was worse by a wider margin: +3.5s on
implement, +10.3s on review, the latter ~27%.

The mechanism is not subtle once measured. The pack shrank by ~10k characters, and the agent spent
them anyway by reading the same file — plus a tool round-trip for the privilege. Deferring a cost
is not removing it.

**The saving and the risk turn out to be the same event.** A path-only pack is cheaper exactly when
the spawn does *not* read the spec, and that is precisely the case where its output would be
under-informed. So the two outcomes are not a trade-off to be tuned; they are one coin. A model
disciplined enough to make the design safe is disciplined enough to make it pointless, and a model
careless enough to make it pay is careless enough to make it dangerous.

That reframes มติ 3. The proposal's stated benefit is cost, and cost is the thing the measurement
does not find. What it might still buy is *relevance* — a smaller pack means less irrelevant
material competing for attention — but that is a different claim, needs a different probe (one
where the full spec's bulk actively misleads), and was not tested here.

> **Superseded in part by [round2/FINDINGS.md](round2/FINDINGS.md).** The "~2% of a spawn" figure
> below is a function of this spec's size and should not be read as a general claim. Round 2 re-ran
> the same design at 2.9× the spec size: the quality result held (24/24 across both rounds), the
> cost result held wherever the file was read whole — but one run read the spec selectively and
> saved ~6%, which is a mechanism this round's design could not have surfaced.

## Limits

* One model, one spec, one probe, n=3. A probe planted in a *less* obviously load-bearing spot
  might separate the arms where this one did not.
* Both arms were handed their pack as a file to read, which nudges toward reading a second file.
  The nudge favours arm B, so it does not weaken the "B read every time" result — but it does
  weaken any inference about how B would behave with the pack inlined.
* Token totals are dominated by fixed session overhead; the ~2.5k pack difference is ~2% of each
  run. The direction is consistent across all 6 pairs, the magnitude is not precise.
* `workflow.yaml` is frozen and portable. Even a clean sweep here argues at most for a
  model-conditional rule — the artifact may execute later on a model this eval says nothing about.

## Recommendation

Leave `kestra-run`'s paste-verbatim rule as it stands. Not because the concern behind it was
vindicated — it wasn't, on this model — but because the change it would be traded for does not pay
for itself, and the existing rule already carries the escape hatch that matters ("a spec too large
to paste whole is the one exception"). If มติ 3 proceeds, its case should rest on relevance and on
tracker-shaped provenance, not on token cost, and the size threshold in that existing exception is
the smaller and more defensible thing to argue about.
