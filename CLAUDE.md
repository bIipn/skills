# CLAUDE.md — standing instructions for this repo

> **Saved preference (set by the owner):** apply **loop engineering** to every
> task — current and future. This file is read at the start of every Claude Code
> session, so it is how that preference persists. (In this remote/ephemeral
> environment only committed files survive between sessions, so the preference
> lives in-repo by design.)

## Default working method: loop engineering

For any non-trivial or recurring task, don't one-shot a prompt — structure it as
a self-improving loop. The full methodology is the **`loop-engineering`** skill
(`skills/loop-engineering/SKILL.md`); invoke or follow it. In short:

1. **Harness first.** Get one reliable manual run (standing facts, tools,
   verification target) before automating — a loop multiplies whatever's under it.
2. **Maker / checker.** Whatever produces an artifact is checked by something
   independent before it's trusted. The maker never grades its own work.
3. **Objective stop conditions.** "Done" is checkable (tests pass, a metric
   clears a threshold, beats a benchmark) — never "feels done".
4. **Memory.** Read `STATE.md`/progress at the start; write lessons at the end.
   Graduate general lessons into a skill.
5. **Fail safe.** Permissions/hooks/guardrails are mandatory for unattended runs;
   no irreversible action without explicit gating. Route work by model cost.

## Honest defaults

- "Self-improving" = the *system* improves (memory, skills, grader), not the
  model's weights. Don't oversell autonomy.
- Be honest about results: show benchmarks and failure cases, not just wins.
- Don't weaken a test or a guardrail to make output look better — file a lesson.

## Map

- `skills/loop-engineering/SKILL.md` — the reusable methodology.
- `skills/` — example skills; `.claude-plugin/marketplace.json` registers them.
- Reference loop implementation: the `biipn/trading-bot` repo.
