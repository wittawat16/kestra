# Test-Quality Failure Mode Taxonomy — Research Notes

Grounding research for a `test-quality-risk-taxonomy` section in `workflow/kestra-build/SKILL.md`, mapping 6 observed production failure modes to established software-testing literature.

## Summary Table

| Pattern # | Established Term | Mitigation Practice | Primary Source(s) |
|---|---|---|---|
| 1 | Non-hermetic / non-deterministic tests ("flaky tests") | Hermetic tests; clock/time injection (dependency injection of `Clock`) | testing.googleblog.com (Hermetic Servers, Flaky Tests, Where Flaky Tests Come From) |
| 2 | Mock behavior diverging from real collaborator's contract (no single canonical name — "mockist test" risk / contract-testing gap) | Integration Contract Tests; Consumer-Driven Contract testing (Pact) | martinfowler.com/articles/mocksArentStubs.html; docs.pact.io |
| 3 | No single canonical name — instance of "mocks aren't stubs"/unrealistic test double fidelity; related to "Don't Mock What You Don't Own" | Realistic/faithful test doubles ("Contract Tests Ensure Faithful Doubles"); prefer Fakes over hand-idealized Stubs/Mocks | martinfowler.com/bliki/TestDouble.html; GOOS (Freeman & Pryce) |
| 4 | Characterization testing / Golden Master (Approval) testing — repurposed for cross-path parity, not legacy-only | Characterization tests; Golden Master / Approval Testing | Feathers, *Working Effectively with Legacy Code*; approvaltests.com |
| 5 | "Mocks Aren't Stubs" fidelity gap — no single canonical name; xUnit Patterns calls the class of solutions "Fake Object" | Fakes over hand-typed Stubs; contract tests to keep doubles honest; (industry practice: generated/schema-derived doubles) | martinfowler.com/articles/mocksArentStubs.html; xunitpatterns.com Fake Object |
| 6 | "Don't Mock What You Don't Own" boundary issue, inverted — mocking too much of *your own* shared logic | Don't Mock What You Don't Own; Humble Object (isolate untestable seam so shared logic stays exercised) | GOOS (Freeman & Pryce) via hynek.me/javflores summaries; xunitpatterns.com Humble Object |

---

## 1. Tests depend on live/wall-clock/system state instead of pinning it

**Established term(s):** This is the textbook cause of a **"flaky test"** — a test that non-deterministically passes/fails without code changes. Google's testing blog treats **"hermetic" tests** (tests isolated from real/external dependencies including real time, network, and other live systems) as the named counter-concept — a non-hermetic test is exactly this failure mode.

**Mitigation practice name(s):** **Hermetic tests / hermetic test environments**; and specifically for time, **clock injection** (injecting a `Clock`/time-source dependency rather than calling `System.currentTimeMillis()`/`time.Now()` directly) — a specific case of Dependency Injection applied to non-deterministic system state.

**Sources:**
- https://testing.googleblog.com/2012/10/hermetic-servers.html — verified the definition: hermetic tests spawn the system under test *and* all its dependencies in an isolated environment, removing real inter-system/network calls as a flakiness source.
- https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html — verified Google's own data (analysis of 4.2M tests) naming timing (absolute/relative), randomness, and environment variability as leading flake causes, with hermetic isolation and reducing test size as primary mitigations.

**Note:** Maps cleanly. "Flaky test" / "hermetic test" is Google's own established vocabulary for this exact failure class.

---

## 2. Mocks don't enforce the real dependency's ordering/precondition constraints

**Established term(s):** No single one-word term in the literature for this specific sub-failure. It falls under the general risk Fowler names when discussing **mock/behavior verification**: "expectations on mockist tests can be incorrect, resulting in unit tests that run green but mask inherent errors" — i.e., the mock's programmed expectations don't match what the real collaborator actually requires or enforces.

**Mitigation practice name(s):** **Integration Contract Tests** (Fowler) — a test suite, written by the consumer, that runs against the real provider to verify the consumer's assumptions (including call sequencing/preconditions) actually hold; formalized at scale as **Consumer-Driven Contract testing**, implemented by tools like Pact.

**Sources:**
- https://martinfowler.com/articles/mocksArentStubs.html — verified: "Only mocks insist upon behavior verification... expectations on mockist tests can be incorrect, resulting in unit tests that run green but mask inherent errors" — this is the named risk.
- https://docs.pact.io/ — verified: Pact's consumer-driven contract flow (consumer writes expected interactions → contract file → replayed against the real, locally-running provider) is the concrete mechanism that catches a mock's wrong assumptions about ordering/preconditions, because the contract is verified against the real provider, not just asserted in the mock.

**Note:** Maps to a documented *risk* (mockist false-positive) with a named *mitigation* (integration contract tests / CDC), but there's no single established name for "ordering/precondition mismatch" as its own pattern — it's one instance of the broader mocks-aren't-stubs risk.

---

## 3. Mocks return "too-perfect"/idealized data, never simulating degraded/partial responses

**Established term(s):** No canonical name exists for this specific failure in the primary sources reviewed. It is best described as a **test-double fidelity gap** — the double doesn't represent the real collaborator's actual behavior space (error paths, partial/malformed data), only its happy path. This is adjacent to, but distinct from, the "Fakes vs Stubs" taxonomy question — a Stub that only returns canned "success" data is technically a correct Stub by Meszaros's definition, it's just an *incomplete* one relative to what production returns.

**Mitigation practice name(s):** No single named practice; the literature converges on: (a) writing **Fakes** with a "working implementation" (Fowler/Meszaros) that can be configured into realistic failure/degraded states, not just canned success; (b) validating doubles against the real dependency via **contract tests**, which — if the contract itself encodes error/edge responses — forces the double to cover them too.

**Sources:**
- https://martinfowler.com/bliki/TestDouble.html — verified the Meszaros taxonomy (Dummy/Fake/Stub/Spy/Mock) and that a Stub only needs to provide "canned answers... to what's programmed in for the test" — nothing in the taxonomy requires realism, which is exactly the gap this pattern describes.
- https://docs.pact.io/ — verified contract tests are provider-verified, so if the contract set includes degraded-response scenarios, the consumer's mock is forced to match them (mitigation, not the term itself).

**Note:** Doesn't map cleanly to one established term. This is an honest gap — closest framing is "test doubles lack behavioral fidelity to the real dependency's full response space," which the sources support only as an implication, not a named pattern.

---

## 4. No parity test between two paths meant to produce equivalent real-world behavior

**Established term(s):** **Characterization testing** (Michael Feathers) and its close relative **Golden Master testing / Approval testing** are the established techniques for asserting two things produce/should produce the same output — normally applied to "legacy code's current behavior vs. a refactor," but the underlying mechanism (snapshot one path's output as the reference, assert the other path matches it) is exactly what a backtest-vs-live parity check needs.

**Mitigation practice name(s):** **Characterization tests**; **Golden Master (Approval) testing** — comparing a complex actual result against a stored/reference result rather than individual assertions.

**Sources:**
- (Feathers, *Working Effectively with Legacy Code*, Ch. 13 "I Need to Make a Change, but I Don't Know What Tests to Write") — verified via secondary summaries (daedtech.com, understandlegacycode.com) since the book itself isn't web-hosted in full: a characterization test "captures the actual behavior of a piece of code" as a regression baseline, not a correctness spec.
- https://approvaltests.com/ — verified: "Approvals work by comparing the test results to a golden master... comparing a complex result... with the result of the same process in a previous version" — the exact "compare two outputs for equivalence" mechanism this pattern needs, just typically applied version-over-version rather than path-over-path.

**Note:** Maps cleanly to the *mechanism* (golden-master/characterization comparison), but the literature's framing is always "old version vs. new version" of the *same* code path, not "two different code paths meant to agree." Applying it to backtest-vs-live parity is a reasonable extension of the technique, not something the sources describe verbatim — flagged honestly.

---

## 5. Hand-typed mocks don't match the real dependency's actual types/shapes

**Established term(s):** This is the core warning inside **"Mocks Aren't Stubs"** itself — the classic mock-vs-reality drift problem. No shorter canonical name beyond that essay's own framing exists in the primary sources; it's sometimes referred to informally in the wider community (blog title format, not Fowler's own words) as ensuring "faithful doubles."

**Mitigation practice name(s):** Preferring **Fakes** (working, if simplified, implementations) over hand-typed Stubs/Mocks where feasible, per Meszaros's taxonomy; and, at the boundary of an external system, **Integration Contract Tests** run against the real provider to catch shape drift mechanically rather than trusting a hand-maintained mock to stay in sync.

**Sources:**
- https://martinfowler.com/articles/mocksArentStubs.html — verified the general "expectations can be incorrect... mask inherent errors" warning applies directly to shape/type mismatches, not just behavioral ones.
- http://xunitpatterns.com/Fake%20Object.html (Fake Object pattern, Meszaros) — the standard prescription for a double that needs to *behave* like the real thing rather than being hand-authored to an assumed shape.

**Note:** No distinct established name beyond "the mocks-aren't-stubs problem" itself — pattern 5 and pattern 2 share the same root literature (mock fidelity to the real collaborator), differing only in *what* drifts (types/shapes here vs. call-ordering there). Said plainly rather than inventing a separate term.

---

## 6. Code depending on shared cross-cutting logic is tested with a mock that bypasses that logic

**Established term(s):** Best described as the **inverse of "Don't Mock What You Don't Own"** (Freeman & Pryce, *Growing Object-Oriented Software, Guided by Tests*) — that principle says don't mock third-party/external types because you don't control their contract; the production failure here is the same root cause turned inward: mocking *your own* shared invariant/guard logic means the mock silently substitutes for code the team *does* own and *should* be exercising for real.

**Mitigation practice name(s):** **Humble Object** pattern (xUnit Patterns / GOOS) — isolate only the genuinely hard-to-test seam (e.g. framework glue) behind a thin adapter, and keep all real logic — including shared guards/invariants — in the testable, unmocked path; more generally, "don't mock what you own" as the inverse guidance.

**Sources:**
- http://xunitpatterns.com/Humble%20Object.html — verified: the pattern's purpose is to keep as much real logic as possible on the *testable* side of the seam, pushing only the untestable framework dependency into a thin, deliberately "humble" shim — directly counter to mocking away shared logic that's actually testable.
- GOOS's "Don't Mock What You Don't Own" (verified via https://hynek.me/articles/what-to-mock-in-5-mins/ and https://javflores.github.io/dont-mock-what-you-dont-own/, both summarizing Freeman & Pryce's book directly) — the book's own guidance is about not mocking code you don't control; this pattern's fix is the mirror image: don't mock code you *do* own when it encodes a shared invariant the test is supposed to protect.

**Note:** Doesn't map to one established term. "Don't Mock What You Don't Own" is well-established but describes the opposite direction (external dependencies); no source names "don't mock your own shared cross-cutting logic" verbatim — this section states that honestly rather than forcing a fit.
