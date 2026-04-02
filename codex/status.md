Current Status

- Project type: Python OSINT suite with codex orchestration layer.
- Backend status: package imports and CLI help entrypoints are covered by smoke tests.
- Orchestration status: orchestrator, routing rules, memory, and autonomous loop are present.
- Product direction (agreed): public **Telegram bot** as the near-term UI; no separate web frontend until an explicit design/scope exists.
- Planning source of truth for the next mount: **read `codex/initiative_next.md` first** (phases A->B->C, owners, checklists).
- **Last progress:** the initial **Phase C** Telegram deployment slice is now closed: live bot deployment and smoke passed, `.env` fallback with process-env precedence is in place, Windows stdout encoding crashes were removed from live command paths, and operator-facing Telegram telemetry was added. Current verified baseline is **81 passed** in the full `pytest -q` suite.
- **Phase B (codex role + contribution):** **complete** for the current checklist - [README.md](../README.md) documents the hybrid `codex/` model (orchestration + contract text verified by tests, notably `tests/test_setup.py`). Do not move `codex/` or change contractual phrases without updating `.cursorrules` and the relevant tests.
- **Git note:** when `tests/` is still untracked (`??`), add and commit those files when you own the change set; do not mix unrelated dirty tree unless intentional.

Active Loop

1. For Next Queue work, load `codex/initiative_next.md`. Phases **A** (install QA), **B** (codex contributor note), and the initial **Phase C** deployment/hardening slice are **closed** for the current checklist; **next focus** is the next functional Telegram batch, while keeping packaging smoke tests green when `setup.py` / `requirements.txt` change.
2. Scan the repository for the next reproducible defect or missing contract.
3. Add a failing test or check that captures the issue.
4. Apply the smallest safe fix inside the owning module (`codex/module_protocol.md`).
5. Re-run verification before reporting status.

Next Queue

- **Phase A (infra + backend):** treat as **complete** for the current checklist unless CI or a new packaging edge case appears; keep tests green when `setup.py` / `requirements.txt` change.
- **Phase B (agents + docs):** **complete** - README states that `codex/` governs agent behavior and that some `codex/*.md` files are contract-checked by tests; moving `codex/` or editing contractual wording requires updating `.cursorrules` and tests.
- **Phase C (backend + infra):** initial public Telegram deployment/hardening slice is **complete** for the current checklist: live smoke passed, `.env` fallback is supported, local secret files are ignored, and operator-facing telemetry is present.
- **Next focus - Phase C functional batch:** use [telegram_phase_c_design.md](telegram_phase_c_design.md) and `codex/initiative_next.md` to define the next small user-facing Telegram improvements without reopening solved deployment/hygiene work; keep thin handlers, async/long jobs, rate limits, and safe logging intact.
- Keep smoke coverage aligned with any new CLI entrypoints or package metadata changes.
