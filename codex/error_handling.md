Error Handling

Principles

- Prefer explicit failures over silent fallback.
- Capture the failing command, exit code, and minimal context before changing code.
- Do not claim a fix until the original failure has been re-tested.

Severity

- High: install, startup, import, or CLI entrypoint failures.
- Medium: incorrect routing, broken docs that mislead setup or operation.
- Low: cosmetic text issues that do not change behavior.

Recovery

1. Reproduce the failure with a command or test.
2. Isolate the smallest responsible file or interface.
3. Apply a minimal change.
4. Re-run the failing check, then the broader smoke suite.
5. Record any remaining risk in the final status.
