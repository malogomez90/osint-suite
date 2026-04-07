Activate the autonomous loop.

Instructions:
1. Switch to Orchestrator mode.
2. Read codex/status.md and codex/initiative_next.md.
3. Determine state: is there an Approved Task? What is in Next Queue?
4. Route to the correct role using new_task.
5. Do not ask routing questions when the next role is obvious from the rules.
6. Loop until a hard stop condition is reached, then report to human.

Hard stop conditions:
- Next Queue is empty
- Task requires human decision or VPS access
- Three consecutive failures on the same item
