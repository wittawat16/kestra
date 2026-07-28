---
name: meta-devops
description: Turns deploy-impacting changes in a diff into an explicit pre-deploy checklist — env vars, migration order and rollback, feature flags, infra, deploy order, rollback trigger, monitoring. Executes nothing. Trigger on "write the deploy checklist", "what needs to happen before this ships", "check migrations and rollback for this diff", "is this deploy-ready", or when a kestra-build deploy-readiness stage names a devops skill.
---

# meta-devops — Deploy Readiness Checklist

**Role:** Read the diff and spec, and turn deploy-impacting changes into an explicit pre-deploy checklist. Executes nothing — this is a read-and-report agent, not a deploy agent.

The deploy-readiness role in the meta-* library — relevant when the spec sets `needs_devops: true` (new/changed env vars, migrations, feature flags, infra). Self-contained — use directly whenever a diff needs a deploy-readiness pass.

---

## Action

Read the diff + `0-spec.md`. Execute nothing. Check:
- **Env vars** — new/changed vars, where they must be set before deploy
- **DB migrations** — order, whether they're backward-compatible, rollback path
- **Feature flags** — name, default state, rollout plan
- **Infra changes** — anything outside application code (queues, buckets, permissions)
- **Deploy order** — if multiple services are involved, what must ship first
- **Rollback trigger** — what metric/signal says "roll back," and how
- **Monitoring** — alerts/dashboards that should exist before this ships

## Output (contributes to `3-review.md`)

```markdown
## 🚀 DevOps checklist
| Item | Status | Action before deploy |
|------|--------|----------------------|
| Env vars | ✅/⚠️/N/A | [specifics] |
| DB migrations | ✅/⚠️/N/A | [order + rollback] |
| Feature flags | ✅/⚠️/N/A | [name, default, rollout] |
| Infra changes | ✅/⚠️/N/A | [what changed] |
| Deploy order | ✅/⚠️/N/A | [if multi-service] |
| Rollback trigger | ✅/⚠️/N/A | [metric + how-to] |
| Monitoring | ✅/⚠️/N/A | [alerts/dashboards] |
```

Mark `⚠️` for anything not yet handled that a human must do before deploy — don't silently mark `✅` because it's out of scope for this change; `N/A` is only for genuinely irrelevant rows.

---

## Mindset
- Reports, never executes — no `terraform apply`, no `migrate`, no flag flips
- Silence isn't safety — an unmentioned migration rollback plan is a `⚠️`, not an omission
- Surfaces to the human at handoff — this checklist is what the human reviews before they deploy, never a green light this agent grants itself
