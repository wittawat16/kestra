# Kestra Workflow Chain

The vocabulary shared by the four cooperating skills under `workflow/kestra-*` — a spec sharpener,
a workflow generator, an orchestrator, and a spec-derived exam — and by the run folders and evals
that hold their evidence.

## Requirement identity

**Spec**:
The `0-spec.md` in a run folder — the vetted statement of what will be built. One per run.
_Avoid_: ticket (the artifact a spec is raised *from*), PRD, requirements doc

**Requirement surface**:
The part of a spec that counts as a requirement — a subset of its sections, and within the Coverage
Map only certain columns. Membership is owned by `SURFACE_SECTIONS` in
`workflow/kestra-build/scripts/requirement_surface.py` and is deliberately restated nowhere else,
in prose or in code.
_Avoid_: the spec (the surface is a subset of it), the ACs, hashed sections. "Surface" alone is the
accepted short form.

**surface_hash**:
The sha256 over a normalized requirement surface. Equal hashes mean the same requirements; any
change inside the surface moves it.
_Avoid_: spec hash, ac_hash (a different, per-slice hash over Coverage Map rows only)

**Raise**:
The commit that writes a vetted ticket body into `0-spec.md`. Found downstream by an
exactly-one-match search, so a re-raise replaces its predecessor rather than stacking.
_Avoid_: the Python `raise`, spec commit, initial commit

**Anchor**:
The triple `raise_commit` + `surface_hash` + `extractor_version` — which requirement text a
judgement was vetted against, at a named point in time. A run records it as `spec_anchor` in
`workflow.yaml`; an exam keeps three copies of its own (manifest, pointer body, `exam.py`) that must
agree with each other.
_Avoid_: baseline, pin, spec hash (the hash is one of the anchor's three fields)

**FRESH**:
The verdict that a recomputed surface still equals an anchor's, so the work is being judged against
the text that was vetted. The opposite verdict is a refusal, named differently at each site
(`MISMATCH`, `REFUSED`, `FAIL`); a comparison that could not run counts as a refusal, never a pass.
_Avoid_: STALE (not a word this codebase uses), out of date, in sync

## Pipeline and evidence

**Gate**:
A check that can stop the pipeline — its result decides an exit code or a stage transition. A check
that reports and continues is not a gate, however alarming its output.
_Avoid_: calling a WARN a gate, or calling a recorded-but-unread field a gate

**Run folder**:
The per-feature directory holding one run: its spec, `workflow.yaml`, `state.json`, any `tickets/`,
and byte copies of the scripts that check it. Those copies are what define it — an answer this
folder gave months ago must not change because a skill was reinstalled since.
_Avoid_: run (the execution, not the directory), workspace, feature folder

**Stage spawn**:
How a stage's work was actually done — a fresh subagent, a resumed one, or the orchestrator doing it
itself (`inline-controller`), recorded per stage as `metrics.spawn_type`. On the test-writing and
implementing stages it is a gated fact, because those two must not share one context.
_Avoid_: agent, session, worker — and do not read `inline-controller` as a kind of subagent

**Dogfood run**:
A real feature built through the chain, living in `workflow/runs/`. It is evidence that the pipeline
runs, and only evidence for a claim about *how* the work was divided if its stage spawns say so.
_Avoid_: eval (an instrumented experiment on the skills themselves, under `workflow/evals/`), demo,
worked example

**Red proof**:
The recorded run of an exam against a clone with no implementation, proving each must-flip check
really fails before the code exists. Without it, "the exam passes" is unfalsifiable.
_Avoid_: baseline run, failing test run, pre-flight
