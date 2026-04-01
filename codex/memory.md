System Memory

Architecture Decisions:
- Monorepo structure
- Central orchestration
- Strict module ownership
- Near-term user-facing surface: **Telegram bot (public)** calling the Python package; not a separate web frontend until scoped.
- **`codex/` model:** hybrid — agent/orchestrator source of truth; where tests enforce phrases or paths, treat those files as **contracts** (update tests when changing them).
- **Install QA:** expand automated checks beyond `setup.py --name` (imports, entry points, version alignment, requirements drift) per `codex/initiative_next.md` Phase A.
