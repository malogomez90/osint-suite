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

- _none_

Last Outcome

- Completed [A3](codex/status.md:24): [`tests/test_setup.py`](tests/test_setup.py) now asserts editable-install package metadata version from [`importlib.metadata.version()`](importlib.metadata.version:1) matches the version declared through [`setup.py`](setup.py) package metadata.

Debugger Fix

_none_

Loop Halt Reason

_none_

Next Queue

- **[A4] requirements.txt ↔ setup.py alignment test** — add test: parse both files and assert no package present in one is absent from the other (name-level check, not version pinning).

- **[D1] HIBP module** — create `osint_suite/hibp_checker.py`. Reads `HIBP_API_KEY` from env (optional). If key present: GET `https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false` with `hibp-api-key` header and `User-Agent: osint-suite`; return list of breach dicts (Name, Domain, BreachDate, PwnCount, DataClasses). If key absent: return `CommandResult` with summary `"HIBP no configurado — añade HIBP_API_KEY al entorno."` and empty payload. No crash, no partial result. Add `requests` call with 10s timeout. Add unit tests with mocked HTTP.
- **[D2] Wire HIBP into `/breach` command** — in `osint_suite/telegram_services.py`, when `service_name == "breach"` and input looks like an email, call `hibp_checker.check_email(email)` in addition to existing `breach_checker`; merge results into one `CommandResult`. When input is a username (no `@`, no `.tld`), skip HIBP and use only existing breach_checker. Add HIBP_API_KEY to `codex/telegram_deployment_runbook.md` optional env vars list.
- **[D3] Expose HIBP_API_KEY in systemd env file docs** — update `codex/telegram_deployment_runbook.md` to list `HIBP_API_KEY` as optional env var with note: "leave unset to disable HIBP lookups gracefully".

- **[E1] Profile analyzer module** — create `osint_suite/profile_analyzer.py`. Function `analyze_profile(target: str) -> CommandResult`. If target contains `@` and `.`: treat as email — run email_analyzer + hibp_checker + breach_checker; merge into unified profile dict with sections: `email`, `breaches`, `risk_score` (count of breaches × avg PwnCount heuristic). If target has no `@`: treat as username — run username_checker + social_analyzer; merge into unified profile dict with sections: `username`, `social`, `platform_count`. Return single `CommandResult` with summary of top findings and full merged payload as JSON.
- **[E2] `/profile` Telegram command** — add handler in `telegram_bot.py` and dispatch in `telegram_services.py`. Usage: `/profile <email|usuario>`. Calls `profile_analyzer.analyze_profile`. Long result always sends JSON attachment. Add to HELP_TEXT. Add unit tests covering email path and username path.
- **[E3] Update runbook and status** — add `/profile` to `codex/telegram_deployment_runbook.md` post-deploy verification checklist (step: run `/profile` with a test email, confirm merged output). Update `codex/status.md` to reflect Phase D+E as new approved feature surface.

- **[F1] Paste checker module** — create `osint_suite/paste_checker.py`. Function `search_pastes(target: str) -> CommandResult`. Use `https://psbdmp.ws/api/v3/search/{target}` (free, no key) with 10s timeout. Parse response: list of dicts with `id`, `time`, `tags`. Build paste URLs as `https://psbdmp.ws/{id}`. Summary: count of hits, top 5 URLs with dates. If zero hits: "No se encontraron pastes públicos para este objetivo." If request fails: raise `ControlledServiceError`. Add unit tests with mocked HTTP for hit/empty/error cases.
- **[F2] `/paste` Telegram command** — add handler in `telegram_bot.py` and dispatch entry in `telegram_services.py`. Usage: `/paste <email|usuario>`. Calls `paste_checker.search_pastes`. Add to HELP_TEXT. Add unit test for command dispatch.

- **[G1] Phone analyzer improvement** — enhance `osint_suite/phone_analyzer.py` (or equivalent). Add `NUMVERIFY_API_KEY` env var (optional). If key present: GET `http://apilayer.net/api/validate?access_key={KEY}&number={E164_number}` with 10s timeout; extract `carrier`, `line_type`, `location`, `country_name`; merge into existing phone result dict under key `carrier_lookup`. If key absent: add `carrier_lookup: null` with note `"NumVerify no configurado"`. No crash. Add unit tests with mocked HTTP. Add `NUMVERIFY_API_KEY` as optional env var in `codex/telegram_deployment_runbook.md`.

- **[H1] Timeline analyzer module** — create `osint_suite/timeline_analyzer.py`. Function `build_timeline(target: str) -> CommandResult`. Detect target type (email vs username). Run all applicable sources in sequence: breach_checker (breach dates), hibp_checker if email (BreachDate field), paste_checker (paste timestamps), social_analyzer (platform list with no dates → mark as "detected, date unknown"). Build list of events: `{date, source, event_type, detail}`. Sort by date ascending. Summary: earliest event, latest event, total event count. Return `CommandResult` with summary text and full event list as JSON payload.
- **[H2] `/timeline` Telegram command** — add handler and dispatch. Usage: `/timeline <email|usuario>`. Calls `timeline_analyzer.build_timeline`. Long result always sends JSON attachment. Add to HELP_TEXT. Add unit tests.

- **[I1] Risk scorer module** — create `osint_suite/risk_scorer.py`. Function `score_risk(target: str) -> CommandResult`. Run: breach_checker + hibp_checker (if email) + paste_checker. Compute score 0–100: `breach_count × 10 + paste_count × 15 + hibp_pwn_count_log × 5`, capped at 100. Map score to level: 0–25 low, 26–50 medium, 51–75 high, 76–100 critical. Summary: score, level, breakdown per source. Return `CommandResult`. Add unit tests for each risk band.
- **[I2] `/risk` Telegram command** — add handler and dispatch. Usage: `/risk <email|usuario>`. Calls `risk_scorer.score_risk`. Add to HELP_TEXT. Add unit tests.

Completed

- **[A1] Package importability test** — complete. Editable install smoke now asserts [`import osint_suite`](../osint_suite/__init__.py) succeeds without import-time crash.
- **[A2] Entry point registration test** — complete. Editable install smoke now verifies declared `console_scripts` are registered in installed metadata entry points.
- **[A3] Version alignment test** — complete. Editable install smoke now verifies installed [`importlib.metadata.version()`](importlib.metadata.version:1) matches the package version declared by [`setup.py`](setup.py).
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
