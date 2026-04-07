# Orchestrator Loop Rules

## Loop cycle

```
START
  → read codex/status.md
  → Next Queue empty? → STOP (report to human)
  → Approved Task exists? → Engineer
  → no Approved Task → Architect
Architect
  → writes Approved Task to codex/status.md
  → signals Orchestrator
Engineer
  → executes Approved Task
  → runs tests
  → commits
  → updates codex/status.md (outcome: completed / blocked / mismatch)
  → signals Orchestrator
Orchestrator
  → outcome = completed → clear Approved Task, loop to START
  → outcome = blocked/mismatch → Debugger
Debugger
  → diagnoses, writes Debugger Fix to codex/status.md
  → signals Orchestrator → Engineer
Engineer
  → applies fix, commits, reports outcome
  → signals Orchestrator
LOOP
```

## Stop conditions (hard stops — require human input)

- Next Queue is empty
- Task requires a design decision not answerable from existing codex files
- Task requires VPS/production access or secrets
- Three consecutive failures on the same queue item
- Scope would expand beyond what codex/initiative_next.md defines

## What the Orchestrator must never do

- Implement code directly
- Skip the Architect step when no Approved Task exists
- Mark a task complete without a green test run
- Push to production (VPS sync requires human)
- Open new phases not listed in codex/initiative_next.md

## codex/status.md fields used by the loop

- `Next Queue` — items available to work on (Orchestrator reads)
- `Approved Task` — current scoped task (Architect writes, Engineer reads)
- `Last Outcome` — completed / blocked / mismatch (Engineer writes, Orchestrator reads)
- `Debugger Fix` — proposed fix (Debugger writes, Engineer reads)
- `Loop Halt Reason` — written by Orchestrator when stopping for human
