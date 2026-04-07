# Repository Standard

## 1. Purpose and scope

This document defines the current operating standard for maintainers of this repository.

It describes:
- the primary product surface,
- the effective module boundaries,
- the status of CLI interfaces,
- which `codex/` documents are authoritative,
- how to treat generic scaffolding,
- and which OSINT tool modules are exposed through Telegram versus still requiring classification.

This document does not authorize refactors, file deletion, or product expansion by itself.

## 2. Product surface standard

The primary product surface of this repository is the Telegram bot.

Maintainers should treat the bot runtime and its supporting service layer as the main user-facing workflow of the project.

The Python package remains the execution core behind the bot. The bot is a delivery layer over reusable OSINT capabilities, not a separate product disconnected from the package.

## 3. Effective module boundaries

### 3.1 Telegram transport layer

Telegram-specific handlers, bot configuration, upload handling, rate limiting, and chat-facing execution belong to [`osint_suite/telegram_bot.py`](../osint_suite/telegram_bot.py).

Standard:
- keep handlers thin,
- keep Telegram concerns isolated here,
- do not move OSINT analysis logic into transport handlers.

### 3.2 Application service layer

Command dispatch, file dispatch, result shaping, and adaptation between Telegram inputs and OSINT tools belong to [`osint_suite/telegram_services.py`](../osint_suite/telegram_services.py).

Standard:
- all Telegram-exposed capabilities should pass through this layer,
- summary formatting and filename normalization belong here,
- this layer may orchestrate tools, but should not become a second transport layer.

### 3.3 Reusable OSINT tool layer

The investigation and analysis modules under [`osint_suite/`](../osint_suite/) are the reusable tool layer.

These modules are the engine of the repo and should remain usable independently of Telegram where practical.

### 3.4 Secondary CLI/package layer

Packaging, metadata, and console entrypoints are defined in [`setup.py`](../setup.py). The menu-based CLI entrypoint lives in [`osint_suite/main.py`](../osint_suite/main.py).

Standard:
- package health and installability remain required,
- CLI support remains valid,
- CLI is not the primary product narrative or design driver.

### 3.5 Quality and contract layer

Behavioral and packaging checks belong in [`tests/`](../tests/).

Current anchors:
- [`tests/test_telegram_bot.py`](../tests/test_telegram_bot.py) for Telegram behavior,
- [`tests/test_setup.py`](../tests/test_setup.py) for packaging, CLI smoke, and selected `codex/` contracts.

## 4. Interface classification

### Primary
- Telegram bot workflow via [`osint_suite/telegram_bot.py`](../osint_suite/telegram_bot.py)

### Secondary
- reusable Python package modules under [`osint_suite/`](../osint_suite/)
- console scripts declared in [`setup.py`](../setup.py)
- menu/help CLI in [`osint_suite/main.py`](../osint_suite/main.py)

Implication for maintainers:
- new user-facing work should be evaluated first in terms of Telegram experience,
- reusable implementation should still land in the package/service layers rather than directly in Telegram handlers.

## 5. `codex/` document classification

### 5.1 Authoritative operational documents

The following documents are currently authoritative because they reflect active operating rules, current state, deployment reality, or test-coupled contracts:

- [`codex/status.md`](../codex/status.md)
- [`codex/initiative_next.md`](../codex/initiative_next.md)
- [`codex/telegram_phase_c_design.md`](../codex/telegram_phase_c_design.md)
- [`codex/telegram_deployment_runbook.md`](../codex/telegram_deployment_runbook.md)
- [`codex/error_handling.md`](../codex/error_handling.md)
- [`codex/quality_gates.md`](../codex/quality_gates.md)
- [`codex/module_protocol.md`](../codex/module_protocol.md)

These should be treated as active repo guidance unless replaced intentionally.

### 5.2 Legacy or template-oriented material

The following should be treated as legacy, generic, or template-oriented unless a maintainer can point to active operational use:

- [`codex/orchestrator.md`](../codex/orchestrator.md)
- [`codex/routing_rules.md`](../codex/routing_rules.md)
- [`codex/memory.md`](../codex/memory.md)
- [`codex/session_prompts.md`](../codex/session_prompts.md)
- content under [`codex/intelligence/`](../codex/intelligence/)
- role-description files under [`modules/`](../modules/)

Legacy/template-oriented does not mean delete immediately. It means these files must not drive structure decisions unless they are explicitly revalidated.

## 6. Cleanup policy for generic scaffolding

Generic scaffolding must not be expanded by default.

Maintainer policy:
- do not add new generic orchestration/framework files unless they support the actual Telegram-first workflow,
- do not preserve broad template structure only because it already exists,
- prefer consolidation over proliferation when multiple documents describe the same workflow,
- before keeping a generic file, identify a concrete maintainer or test dependency that requires it,
- if a document is historical but not active, mark it as legacy before deleting or rewriting it in a later change.

Until cleanup work is approved, existing files remain in place but should be treated according to the classification in this document.

## 7. Tool exposure status

### 7.1 Clearly exposed through Telegram

These modules are clearly exposed through the current Telegram command/file flow:

- [`osint_suite/username_search.py`](../osint_suite/username_search.py)
- [`osint_suite/email_osint.py`](../osint_suite/email_osint.py)
- [`osint_suite/phone_investigator.py`](../osint_suite/phone_investigator.py)
- [`osint_suite/company_research.py`](../osint_suite/company_research.py)
- [`osint_suite/geolocation_helper.py`](../osint_suite/geolocation_helper.py)
- [`osint_suite/document_analyzer.py`](../osint_suite/document_analyzer.py)
- [`osint_suite/image_metadata.py`](../osint_suite/image_metadata.py)

### 7.2 Explicit classification decision

The following modules are implemented in the package and are already wired through the current Telegram command/service flow. For repository planning purposes, they are now classified as **Telegram-exposed capabilities** and remain in scope for the Phase C Telegram product surface:

- [`osint_suite/social_analyzer.py`](../osint_suite/social_analyzer.py) via `/social`
- [`osint_suite/breach_checker.py`](../osint_suite/breach_checker.py) via `/breach`

Maintainer interpretation:
- keep both capabilities in the Telegram-first product surface,
- keep orchestration and response shaping in [`osint_suite/telegram_services.py`](../osint_suite/telegram_services.py),
- keep Telegram transport concerns in [`osint_suite/telegram_bot.py`](../osint_suite/telegram_bot.py),
- do not treat these modules as package-only or deprecated unless a later approved planning decision explicitly changes that status.

## 8. Maintainer rule of interpretation

If documentation or structure conflicts with this file, maintainers should interpret the repository as:

1. Telegram-first,
2. package-backed,
3. CLI-secondary,
4. selective about keeping generic orchestration scaffolding.
