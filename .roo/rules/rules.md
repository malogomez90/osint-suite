This project uses a strict workflow:

Human -> Architect -> Engineer -> Debugger

Global rules:
- preserve existing behavior
- prefer minimal, safe changes
- no unnecessary refactors
- respect docs/repo-standard.md
- do not expand scope unless explicitly asked

Routing defaults:
- if the task is to choose the next best step -> Architect
- if there is already an approved scoped task -> Engineer
- if execution fails or reveals inconsistency -> Debugger

Automatic transitions:
- after Architect defines the next step -> Engineer
- after Engineer completes successfully with no blockers -> Architect
- after Engineer reports failure or inconsistency -> Debugger
- after Debugger proposes the smallest safe fix -> Engineer

If two options are acceptable, choose the narrower one.
