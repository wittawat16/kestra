# meta/ — role-based spec→plan→build→review agents

Ten specialized skills, each modeling one role in a software delivery team — no fixed orchestrator
chains them; call one directly, chain them yourself, or reference one by name from a stage brief in
a `workflow/kestra-build`-generated `workflow.yaml`. The name borrows from
[MetaGPT](https://github.com/geekan/MetaGPT), a multi-agent framework that assigns the same kind of
software-company roles (PM, Architect, Engineer, QA) to complete a spec — the same idea `kestra`
borrows from the real workflow-orchestrator project of that name.

Unlike `workflow/`'s TDD-locked stage machine (mechanical write-scope/test-hash/exit-criteria
enforcement), these are judgment-driven role skills — no shared enforcement machinery between them.

| Skill | Phase | Role |
|---|---|---|
| [`meta-pm/`](meta-pm/) | 0 | Sharpens a rough spec into a build-ready `0-spec.md` with testable acceptance criteria |
| [`meta-ba/`](meta-ba/) | 0.3 | Turns vague business rules into explicit numbered rules with examples/counter-examples (when the spec flags it) |
| [`meta-designer/`](meta-designer/) | 0.5 | Turns a spec into a build-ready `design.md` — mockup, token mapping, all screen states (when the spec needs UI) |
| [`meta-sa/`](meta-sa/) | 0.7 | Resolves cross-service concerns and NFRs into one chosen approach with justification (when the spec touches multiple services) |
| [`meta-architect/`](meta-architect/) | 1 | Surveys the real codebase and produces an ordered implementation plan (`1-plan.md`) with every file path verified |
| [`meta-dev/`](meta-dev/) | 2a | Implements the plan into real code, scoped to planned files, hands off rather than self-certifying |
| [`meta-qa/`](meta-qa/) | 2b | Independently verifies the implementation against acceptance criteria with real test runs — never trusts a prior "it passed" claim |
| [`meta-review/`](meta-review/) | 3a | Independent code review of the real diff — correctness, edge cases, error handling, consistency |
| [`meta-security/`](meta-security/) | 3b | Independent security review of the real diff — injection, authn/authz, secrets, vulnerable dependencies |
| [`meta-devops/`](meta-devops/) | 3c | Pre-deploy checklist — env vars, migration order + rollback, feature flags, monitoring (when the spec has deploy concerns) |

Each skill's own `SKILL.md` is self-contained — read it directly for its exact process, inputs,
and output format.
