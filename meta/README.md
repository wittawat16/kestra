# meta/ — role-based delivery skills

Eight specialized skills, each modeling one role in a software delivery team — no fixed orchestrator
chains them; call one directly, chain them yourself, or reference one by name from a stage brief in
a `workflow/kestra-build`-generated `workflow.yaml`. The name borrows from
[MetaGPT](https://github.com/geekan/MetaGPT), a multi-agent framework that assigns the same kind of
software-company roles (PM, Architect, Engineer, QA) to complete a spec — the same idea `kestra`
borrows from the real workflow-orchestrator project of that name.

Unlike `workflow/`'s TDD-locked stage machine (mechanical write-scope/test-hash/exit-criteria
enforcement), these are judgment-driven role skills — no shared enforcement machinery between them.

**This is a role library, not a pipeline.** Earlier versions numbered these as phases (0, 0.3, 0.5,
… 3c), implying a fixed order. That numbering is gone, for a concrete reason: `workflow/kestra-spec`
now does the whole spec→plan front end — sharpening acceptance criteria, resolving business rules,
choosing an approach, and surveying the codebase — in a single pass, so the skills that used to
occupy phases 0 through 1 (`meta-pm`, `meta-ba`, `meta-sa`, `meta-architect`) no longer had a phase
to sit in and were retired. What remains is the set that still does something no other skill does.

| Skill | Role |
|---|---|
| [`meta-designer/`](meta-designer/) | Produces a real UI artifact (HTML mockup / Mermaid wireframe) plus component audit, token mapping, and all four screen states — the part `kestra-spec`'s tables-only Design Notes don't cover |
| [`meta-dev/`](meta-dev/) | Implements a plan into real code, scoped to the planned files, handing off rather than self-certifying |
| [`meta-qa/`](meta-qa/) | Independently verifies the implementation against acceptance criteria with real test runs and a real app start — never trusts a prior "it passed" claim |
| [`meta-test-review/`](meta-test-review/) | Reviews freshly written tests for test-double fidelity against the spec's Reality Constraints, before the tests are frozen |
| [`meta-review/`](meta-review/) | Independent code review of the real diff — correctness, edge cases, error handling, consistency. Folds in `meta-security`'s checklist by default |
| [`meta-security/`](meta-security/) | The security deltas a generic code review won't produce: protected-path scrutiny, the exploitability bar, and the tie rule (security wins) |
| [`meta-devops/`](meta-devops/) | Pre-deploy checklist — env vars, migration order + rollback, feature flags, monitoring (when the spec has deploy concerns) |
| [`meta-debug/`](meta-debug/) | Four-mantra debugging discipline (reproduce → trace fail path → falsify hypothesis → cross-reference breadcrumbs). Callable for any bug, and the escalation when a fix loop stops converging |

Real ordering constraints worth knowing (everything else is free-form):

* `meta-test-review` only makes sense **after** tests are written and **before** they're frozen —
  after the freeze, its only legal outcome is a `reworking` bounce, which turns every finding into a
  human stop.
* `meta-dev` → `meta-qa` → review is a genuine chain: nothing self-certifies, so each link is
  checked by the next one rather than by itself.
* `meta-debug` is where `meta-qa`'s circuit breaker (five loops without convergence) escalates —
  a non-converging fix loop is guessing, and that's what the discipline exists to stop.

Each skill's own `SKILL.md` is self-contained — read it directly for its exact process, inputs,
and output format.
