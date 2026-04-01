Module Protocol

Ownership

- `backend`: Python package behavior, CLI entrypoints, validation, and shared utilities.
- `infra`: packaging, install flow, dependency metadata, and deployment docs.
- `agents`: orchestrator prompts, routing rules, memory, and autonomous loop docs.
- `frontend` and `data`: reserved until concrete implementation exists in the repo.

Handoff

1. Classify the task by affected files and user-facing impact.
2. Route to the owning module.
3. Make the smallest change inside that boundary.
4. Verify locally before returning control to the orchestrator.

Boundary Rules

- Do not modify unrelated modules to bypass a local defect.
- Escalate cross-module changes explicitly when one fix touches multiple owners.
- Keep shared contracts tested where possible.
