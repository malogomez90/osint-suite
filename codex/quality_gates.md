Quality Gates

Required Checks

- A targeted failing test or reproducible command exists before the fix.
- The targeted check passes after the fix.
- The shared smoke suite passes after the change.
- No unrelated files are modified without clear reason.

Do Not Claim Success

- Do not report completion from reasoning alone.
- Do not rely on stale output from earlier runs.
- Do not trust terminal rendering artifacts as proof of file corruption.

Release Gate

- For packaging changes, verify `setup.py` behavior directly.
- For CLI changes, verify `python -m <module> --help`.
- For orchestration docs, verify required files are present and non-empty.
