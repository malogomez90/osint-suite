Current Status

- Project type: Python OSINT suite with codex orchestration layer.
- Backend status: package imports and CLI help entrypoints are covered by smoke tests.
- Orchestration status: orchestrator, routing rules, memory, and autonomous loop are present.
- Product direction (agreed): public **Telegram bot** as the near-term UI; no separate web frontend until an explicit design/scope exists.
- Planning source of truth for the next mount: **read `codex/initiative_next.md` first** (phases A->B->C, owners, checklists).
- **Last progress:** the approved Phase C validation/error-contract slice is now implemented for the current Telegram command and upload surface: [`CommandResult`](../osint_suite/telegram_services.py) remains the single presentation contract, command/file flows keep the same summary + JSON fallback behavior, and service-dispatched Telegram commands plus file uploads now normalize validation failures and controlled capability failures through one user-safe contract.
- **Current implementation status:** Telegram bot functionality is stable for the current phase: command/help UX is normalized, the response contract is enforced consistently across command and file presentation paths, command and upload validation now rely on the service-layer contract for the current Telegram capabilities, focused failure-path and contract-path coverage is passing, and no runtime inconsistencies were identified in the approved slice.
- **Current operational checkpoint:** VPS runtime baseline is deployed and active. The canonical runtime skeleton is in place: repo at `/opt/osint-suite`, venv at `/opt/osint-suite/.venv`, dependencies installed, env file at `/etc/osint-suite/telegram-bot.env`, systemd unit `osint-telegram-bot` enabled and running. Live operator verification is in progress against the runbook checklist.
- **Current planning decision:** [`osint_suite/social_analyzer.py`](../osint_suite/social_analyzer.py) and [`osint_suite/breach_checker.py`](../osint_suite/breach_checker.py) are now explicitly classified as Telegram-exposed capabilities in the current product surface, aligned with the already implemented `/social` and `/breach` command flow.
- **Phase B (codex role + contribution):** **complete** for the current checklist - [README.md](../README.md) documents the hybrid `codex/` model (orchestration + contract text verified by tests, notably `tests/test_setup.py`). Do not move `codex/` or change contractual phrases without updating `.cursorrules` and the relevant tests.
- **Git note:** when `tests/` is still untracked (`??`), add and commit those files when you own the change set; do not mix unrelated dirty tree unless intentional.

Active Loop

1. Phase C is fully closed. Load `codex/initiative_next.md` to determine the next phase or slice.
2. Architect owns the next decision. Route: Engineer completed with no blockers → Architect defines next narrowest step.
3. Keep future Telegram slices aligned with the single response contract and the current service-layer validation/error contract rather than adding per-capability message variants.
4. Treat social-analysis and breach-analysis as in-scope Telegram capabilities for future planning.

Next Queue

- **Phase A (infra + backend):** treat as **complete** for the current checklist unless CI or a new packaging edge case appears; keep tests green when `setup.py` / `requirements.txt` change.
- **Phase B (agents + docs):** **complete** - README states that `codex/` governs agent behavior and that some `codex/*.md` files are contract-checked by tests; moving `codex/` or editing contractual wording requires updating `.cursorrules` and tests.
- **Phase C (backend + infra):** the approved validation/error-contract slice is now **complete** for the current checklist: live smoke baseline remains intact, `.env` fallback is supported, local secret files are ignored, operator-facing telemetry is present, command UX is normalized, the Telegram presentation layer enforces one [`CommandResult`](../osint_suite/telegram_services.py) contract across command/file flows, and current Telegram commands plus document/image upload flows share one normalized validation/error contract with focused regression coverage green.
- **Checkpoint completion note:** the previously missing [codex/status.md](codex/status.md) update is now synchronized with the verified Telegram bot state and deployment documentation.
- **Phase C planning note:** [`osint_suite/social_analyzer.py`](../osint_suite/social_analyzer.py) and [`osint_suite/breach_checker.py`](../osint_suite/breach_checker.py) are explicitly part of the Telegram product surface; planning should treat `/social` and `/breach` as current capabilities rather than deferred or package-only tools.
- **Phase C operational verification: COMPLETE (2026-04-07)**
  - [x] Step 1: `--check-config` → `Telegram bot configuration OK` — **verified**
  - [x] Step 2: systemd unit running, polling active — **verified**
  - [x] Step 3: `/start` — **verified**
  - [x] Step 4: `/help` — **verified**
  - [x] Step 5: `/username <usuario>` success path — **verified** (JSON attachment confirmed)
  - [x] Step 6: validation failure path (no args) — **verified**
  - [x] Step 7: JSON attachment threshold — **verified** (`/username` result triggered attachment)
  - [x] Step 8: document upload (PDF) — **verified**
  - [x] Step 9: image upload — **verified** (mismatch resolved: custom JSON encoder for bytes EXIF fields, commit `d6f9f31`)
  - [x] Step 10: rate limiting — **verified**
  - [x] Step 11: log sanitization — **verified** (httpx token leak resolved: suppressed to WARNING, commit `d6f9f31`)
  - **Mismatches resolved and committed. VPS synced. Phase C closed.**
- Keep smoke coverage aligned with any new CLI entrypoints or package metadata changes.
