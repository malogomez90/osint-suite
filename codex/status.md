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

Approved Task

- **[A2] Entry point registration test** — add one focused packaging test in [`tests/test_setup.py`](tests/test_setup.py) that parses the declared `console_scripts` from [`setup.py`](setup.py) and asserts they are present in [`importlib.metadata.entry_points()`](tests/test_setup.py:178) for the installed `osint-suite` distribution after editable install. Keep scope limited to entry-point registration only; do not change runtime code, version assertions, or requirements-alignment checks.

Last Outcome

- Completed [A1](codex/status.md:40): [`tests/test_setup.py`](tests/test_setup.py) now verifies that after editable install, [`import osint_suite`](../osint_suite/__init__.py) succeeds without an import-time crash while preserving the existing editable-install smoke coverage.

Debugger Fix

_none_

Loop Halt Reason

_none_

Next Queue

- **[A2] Entry point registration test** — add test: `importlib.metadata.entry_points(group="console_scripts")` contains the entry points declared in `setup.py`.
- **[A3] Version alignment test** — add test: `importlib.metadata.version("osint-suite")` matches the version string in `setup.py`.
- **[A4] requirements.txt ↔ setup.py alignment test** — add test: parse both files and assert no package present in one is absent from the other (name-level check, not version pinning).

- **[D1] HIBP module** — create `osint_suite/hibp_checker.py`. Reads `HIBP_API_KEY` from env (optional). If key present: GET `https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false` with `hibp-api-key` header and `User-Agent: osint-suite`; return list of breach dicts (Name, Domain, BreachDate, PwnCount, DataClasses). If key absent: return `CommandResult` with summary `"HIBP no configurado — añade HIBP_API_KEY al entorno."` and empty payload. No crash, no partial result. Add `requests` call with 10s timeout. Add unit tests with mocked HTTP.
- **[D2] Wire HIBP into `/breach` command** — in `osint_suite/telegram_services.py`, when `service_name == "breach"` and input looks like an email, call `hibp_checker.check_email(email)` in addition to existing `breach_checker`; merge results into one `CommandResult`. When input is a username (no `@`, no `.tld`), skip HIBP and use only existing breach_checker. Add HIBP_API_KEY to `codex/telegram_deployment_runbook.md` optional env vars list.
- **[D3] Expose HIBP_API_KEY in systemd env file docs** — update `codex/telegram_deployment_runbook.md` to list `HIBP_API_KEY` as optional env var with note: "leave unset to disable HIBP lookups gracefully".

- **[E1] Profile analyzer module** — create `osint_suite/profile_analyzer.py`. Function `analyze_profile(target: str) -> CommandResult`. If target contains `@` and `.`: treat as email — run email_analyzer + hibp_checker + breach_checker; merge into unified profile dict with sections: `email`, `breaches`, `risk_score` (count of breaches × avg PwnCount heuristic). If target has no `@`: treat as username — run username_checker + social_analyzer; merge into unified profile dict with sections: `username`, `social`, `platform_count`. Return single `CommandResult` with summary of top findings and full merged payload as JSON.
- **[E2] `/profile` Telegram command** — add handler in `telegram_bot.py` and dispatch in `telegram_services.py`. Usage: `/profile <email|usuario>`. Calls `profile_analyzer.analyze_profile`. Long result always sends JSON attachment. Add to HELP_TEXT. Add unit tests covering email path and username path.
- **[E3] Update runbook and status** — add `/profile` to `codex/telegram_deployment_runbook.md` post-deploy verification checklist (step: run `/profile` with a test email, confirm merged output). Update `codex/status.md` to reflect Phase D+E as new approved feature surface.

Completed

- **[A1] Package importability test** — complete. Editable install smoke now asserts [`import osint_suite`](../osint_suite/__init__.py) succeeds without import-time crash.
- **Phase A smoke** — basic `setup.py --name` smoke test exists and passes.
- **Phase B** — complete. README documents codex hybrid model; contract phrases tested.
- **Phase C** — complete. Telegram bot deployed and verified (2026-04-07, all 11 runbook steps).

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
