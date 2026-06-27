---
name: loop-engineering
description: Structure non-trivial or recurring work as a self-improving loop instead of one-shot prompting. Use when building automation, agents, pipelines, trading/quant systems, CI triage, or any task that benefits from independent verification, persistent memory, and objective stop conditions. Triggers - "set up a loop", "make this autonomous/self-improving", "run on a schedule", "maker-checker", "verify its own work", "remember between runs".
---

# Loop engineering

Stop being the thing inside the loop. Instead of typing a prompt, reading the
output, and typing the next one, build the system that does that for you: it
runs the work, checks it independently, decides what's next, and remembers what
it learned. The model at the center stays the same — everything that improves is
the loop you wrapped around it.

**Honest framing first.** "Self-improving" does not mean the model's weights
change. It means the *system* around the model gets sharper: memory accumulates,
skills get edge cases added, the grader keeps it honest. A loop multiplies
whatever is underneath it — wrap one around a weak harness and you just produce
slop faster. Build the harness first.

## The six pieces (miss one and the loop breaks quietly)

1. **Automation** — the heartbeat. A schedule, webhook, `/loop`, cron, or hook
   that fires without you typing. `/loop` reruns on a cadence; a goal-driven run
   keeps going until an *independent* check says the objective is met.
2. **Skill** — a procedure manual (a `SKILL.md` like this) the agent reads
   instead of being re-told conventions every run. Intent compounds.
3. **State file** — `STATE.md`/`PROGRESS.md`. The agent forgets between runs;
   the file does not. Read it at the start, write it at the end. This dumb-
   looking markdown file is the spine of every working loop.
4. **Verifier (maker/checker)** — the agent that produced the work is the worst
   judge of it. A *separate* checker, ideally a different model, with a fresh
   context, sees only the artifact and the standard. Maker proposes, checker
   disposes. This separation is the edge.
5. **Worktrees** — when more than one agent touches the same files, give each
   its own git worktree/branch so they don't collide.
6. **Connectors** — MCP/tools so the loop can act in the real world (DB, API,
   broker, Slack), not just read files. The difference between a loop that
   *suggests* and one that *does*.

## How to build one (the order matters)

1. **Harness first.** Get one manual run reliable: standing facts in a
   `CLAUDE.md`, the right tools connected, a clear verification target. The loop
   reuses all of it every iteration, so every weakness gets multiplied.
2. **Goal + independent grader.** Define "done" as something checkable by
   something *other than the agent's own claim* — tests pass, a metric clears a
   threshold, it beats a benchmark. Never "the agent says it's done".
3. **Split maker from checker.** The checker runs the tests/criteria itself and
   reports pass/fail with concrete reasons. It is not generous.
4. **Put it on a timer, then in the cloud.** A cadence turns a run into a habit;
   scheduled/headless execution turns the habit into infrastructure.
5. **Give it memory.** Write lessons before walking away; read them at the
   start. Skip either and tomorrow restarts from zero — this is where most
   compounding quietly leaks out.
6. **Distill lessons into skills.** Project-specific → `STATE.md`. General
   enough to help the next project → graduate it into a `SKILL.md`.
7. **Fail safe.** No one watches each iteration, so guardrails are not optional:
   allow/deny permission lists, hooks the model can't talk past, no irreversible
   action (deploys, `rm`, pushing to main, real-money orders) without explicit
   gating. Route work by cost — heavyweight model for the orchestrator/checker,
   cheaper for high-volume passes.

## The seven mistakes that keep a loop from compounding

1. Looping a thin harness (slop, faster). Build the harness first.
2. Letting the maker grade itself (confident, not correct).
3. No checkable stop condition (halts at "good enough").
4. No memory (every run restarts from zero).
5. Lessons that never leave the state file (graduate the general ones).
6. An unattended loop with broad permissions (hooks + denies are mandatory).
7. Top-tier model for every iteration (route by task or it bleeds money).

## Reference implementation

`biipn/trading-bot` wires all six pieces around a trading cycle:
`backend/verifier.py` (maker/checker), `backend/state.py` + `STATE.md` (memory),
`backend/loop.py` (`run.py --loop`, objective stop conditions + kill switch),
`backend/research.py` (a plan→reflect→synthesize research agent), and
`SKILL.md`/`CLAUDE.md` (the harness). Note its honest result: the loop is good
engineering, but it did not manufacture alpha — the verifier *correctly* rejects
most trades. A loop makes you disciplined and tireless; it does not invent edge.
