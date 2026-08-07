# Kestra — Sequence Diagrams

Reference diagrams for the `kestra-spec` → `kestra-build` → `kestra-run` pipeline.

## 1. Overview: idea to spec to workflow to execution

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant G as grilling
    participant KS as kestra-spec
    participant KB as kestra-build
    participant KR as kestra-run
    participant FS as Repository

    U->>G: Raw idea
    G-->>U: Sharpened understanding
    U->>KS: Request a build-ready spec
    KS->>FS: Survey real code and verify every file path
    KS->>KS: Derive testable ACs in Given-When-Then form
    KS->>KS: Set flags needs_ba, needs_ui, needs_sa, needs_devops
    KS->>KS: Record Runtime Invariants and Reality Constraints
    KS->>KS: Self-check by executing commands, not on paper
    KS->>FS: Write 0-spec.md under the run folder
    KS-->>U: READY_FOR_BUILD, with Open Items if any
    U->>KB: Request a workflow from the spec
    KB->>FS: Read 0-spec.md
    KB->>KB: Decide mode, lite or full, from the condition table
    KB->>KB: Map each flag to its stage, mechanically
    KB->>KB: Derive stages, write_scope, exit_criteria, on_fail
    KB->>U: Single question. Preferred skill per stage?
    KB->>FS: Write workflow.yaml and state.json
    KB->>FS: Dry-run validate_workflow.py
    KB-->>U: Present both files and a walkthrough. Execute nothing
    U->>KR: Request execution of the workflow
    Note over KR: See diagram 2
    KR-->>U: Halt on reworking, blocked stage, test-hash mismatch, or human_approval
```

## 2. kestra-run, the main loop, per stage

```mermaid
sequenceDiagram
    autonumber
    participant KR as kestra-run
    participant ST as state.json
    participant SH as Bash and git
    participant SA as Stage subagent
    participant TK as Task checklist

    KR->>ST: Read current_stage and test_hash
    KR->>TK: Seed one task per stage
    KR->>KR: Confirm with the user once, before the first stage

    loop Each iteration over current_stage
        KR->>SH: Recompute sha256 over the frozen write_scope
        SH-->>KR: Current hash
        alt Hash differs from test_hash
            KR-->>KR: Hard stop. Frozen tests were modified
        end

        rect rgb(240,248,255)
        Note over KR,SA: Step 2. Perform the stage work
        KR->>SH: Read the source spec in full
        KR->>SH: Run exit_criteria.run and capture the exit code
        KR->>SH: Diff against the last code-touching commit
        KR->>SH: List evidence and harness, grep the prior verdict line
        KR->>KR: Decide whether a subagent is warranted at all
        KR->>SA: Spawn with context pack, brief, write_scope, model and effort
        SA->>SH: Perform the work, writing code or reviewing a diff
        SA-->>KR: Report tersely. Command, exit code, one-line verdict
        end

        rect rgb(255,250,240)
        Note over KR,SH: Step 3. Verify mechanically. A subagent claim is not evidence
        KR->>SH: Match the real diff against the write_scope globs
        alt A path falls outside write_scope
            KR->>SH: Revert it. Checkout if tracked, remove if untracked
            KR-->>KR: Count the attempt as a failure
        end
        KR->>SH: Re-run exit_criteria independently for a real exit code
        end
    end
```

## 3. On pass, freeze and commit

```mermaid
sequenceDiagram
    autonumber
    participant KR as kestra-run
    participant ST as state.json
    participant SH as git
    participant TK as Task checklist

    KR->>ST: Mark the stage as passed
    alt Stage declares freeze_after true
        KR->>SH: Hash every file in the write_scope, one sorted pass from the repo root
        SH-->>KR: Digest
        KR->>ST: Store test_hash. This is the freeze point
    end
    KR->>ST: Record metrics. Tokens, wall-clock, attempt, spawn type
    KR->>SH: Stage all changes including state.json
    KR->>SH: Commit as stage feature-id stage-id passed
    Note right of SH: The commit is the rollback point. No per-stage tag
    KR->>TK: Stage completed. Newly ready stages become in_progress
    KR->>ST: Advance current_stage to every stage whose dependencies are satisfied
```

## 4. On fail, fixing and escalation to reworking

```mermaid
sequenceDiagram
    autonumber
    participant KR as kestra-run
    participant ST as state.json
    participant SH as Bash and git
    participant SA as Stage subagent
    actor U as User

    KR->>ST: Increment attempt on the failing stage own entry
    KR->>SH: Hash the normalized diff, scoped to write_scope only
    SH-->>KR: Semantic diff hash
    KR->>SH: Hash the normalized failure output
    SH-->>KR: Failure signature for seen_failures, diagnostic only

    alt Under max_attempts, and the diff is new or attempt is below escalate_at
        Note over KR: Remain in fixing
        KR->>ST: Append the diff hash to seen_diffs
        alt on_fail.target is set on a review stage with empty write_scope
            KR->>SA: Fix inside the target write_scope, at the target model and effort
            Note right of KR: The recheck is scope-capped. Confirm prior findings, review changed lines only
        else
            KR->>SA: Retry the same stage. Resume below roughly 150k tokens, otherwise respawn
        end
        KR->>SH: Re-run the failing stage own exit_criteria
    else Attempts exhausted, or a repeated diff at or past escalate_at
        Note over KR,U: reworking. The one guaranteed human stop
        KR-->>U: Report the stage, the attempt count, and the recurring failure
        KR-->>U: State that the frozen spec and tests are the primary suspect
    end
```

## 5. The three primitives that make the freeze real

```mermaid
sequenceDiagram
    autonumber
    participant GT as generate-tests
    participant FT as freeze-tests
    participant IM as implement
    participant FX as fixing
    participant ST as state.json

    GT->>GT: Write the scenario table, then the test code. No freeze here
    Note right of GT: No implementation exists yet, so locking now protects nothing
    FT->>ST: freeze_after true. Store test_hash over the write_scope
    IM->>IM: Implement against the frozen tests
    IM->>IM: Install the guards named in Runtime Invariants
    FX-->>FX: May touch non-test paths only
    Note over FX,ST: Editing a test to accommodate broken code is closed off by design
    Note over FX,ST: The only legal route is reworking. Unlock, return to spec-review, re-freeze
```
