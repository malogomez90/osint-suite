Current Status

- Project type: Python OSINT suite with codex orchestration layer.
- Backend status: package imports and CLI help entrypoints are covered by smoke tests.
- Orchestration status: orchestrator, routing rules, memory, and autonomous loop are present.
- Product direction (agreed): public **Telegram bot** as the near-term UI; no separate web frontend until an explicit design/scope exists.
- Planning source of truth for the next mount: **read `codex/initiative_next.md` first** (phases A→B→C, owners, checklists).
- **Last progress:** setup/Telegram baseline now verifies at **72 passed** in `tests/test_setup.py` + `tests/test_telegram_bot.py`; recent work also replaced deprecated `PyPDF2` with `pypdf` and added a root `.gitignore` for local verification artifacts. Prior work already covered metadata/version, console scripts, and dev/runtime split.
- **Git note:** when `tests/` is still untracked (`??`), add and commit those files when you own the change set; do not mix unrelated dirty tree unless intentional.

Active Loop

1. For Next Queue work, load `codex/initiative_next.md` and follow the phase order (A install QA, B codex contribution note, C Telegram).
2. Scan the repository for the next reproducible defect or missing contract.
3. Add a failing test or check that captures the issue.
4. Apply the smallest safe fix inside the owning module (`codex/module_protocol.md`).
5. Re-run verification before reporting status.

Next Queue

- **Phase A (infra + backend):** treat as **complete** for the current checklist unless CI or a new packaging edge case appears; keep tests green when `setup.py` / `requirements.txt` change.
- **Phase B (agents + docs):** document the hybrid `codex/` model (orchestrator docs + tested contracts); add a short contributor note in README or CONTRIBUTING — **good next minimal step** if you want progress without opening Telegram scope.
- **Phase C (backend + infra):** Telegram bot (public): start with a **short design/plan** (commands, limits, deployment, secrets) — **after** you commit or stabilize `tests/` and when ready to scope bot work; thin handlers, async/long jobs, rate limits, safe logging; no “real” SPA/API until separately designed.
- Keep smoke coverage aligned with any new CLI entrypoints or package metadata changes.
