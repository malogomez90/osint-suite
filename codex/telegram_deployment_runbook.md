# Telegram Deployment Runbook

## Startup prerequisites

Deployment target remains intentionally simple:

- one Linux host
- one dedicated Python process
- polling mode
- single replica
- restart managed by `systemd`

Required runtime prerequisites:

- Python **3.9+**
- installed dependencies from [`requirements.txt`](../requirements.txt)
- outbound internet access to the Telegram Bot API
- writable working directory for temporary file handling
- a real Telegram bot token

Required environment variable:

- `TELEGRAM_BOT_TOKEN`

Optional but supported environment variables:

- `TELEGRAM_ALLOWED_USERS`
- `TELEGRAM_RATE_LIMIT_PER_MINUTE`
- `TELEGRAM_RATE_LIMIT_PER_HOUR`
- `TELEGRAM_LONG_JOB_THRESHOLD_SECONDS`
- `TELEGRAM_MAX_CONCURRENT_JOBS`
- `TELEGRAM_RESULT_FILE_THRESHOLD_BYTES`
- `TELEGRAM_MAX_UPLOAD_SIZE_BYTES`
- `TELEGRAM_MAX_DOCUMENT_UPLOAD_SIZE_BYTES`
- `TELEGRAM_MAX_IMAGE_UPLOAD_SIZE_BYTES`
- `TELEGRAM_ANALYSIS_TIMEOUT_SECONDS`
- `TELEGRAM_ALLOWED_DOCUMENT_EXTENSIONS`
- `TELEGRAM_ALLOWED_IMAGE_EXTENSIONS`

Startup configuration precedence:

1. process environment
2. local `.env` file for missing values only
3. startup failure if `TELEGRAM_BOT_TOKEN` is still missing

## Verified startup procedure

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=<real-token>
python -m osint_suite.telegram_bot --check-config
python -m osint_suite.telegram_bot
```

Expected pre-start validation output:

```text
Telegram bot configuration OK
```

Expected startup condition:

- process stays alive
- polling starts without immediate crash
- bot responds to `/start` and `/help`

## Pre-launch checklist

- `TELEGRAM_BOT_TOKEN` present and valid
- dependencies installed in the target virtual environment
- local secret files are not committed
- host can reach Telegram API
- deployment remains single-process
- operator knows how to stop or restart the process cleanly

## Post-deploy verification checklist

After the process is running:

1. Send `/start`
2. Send `/help`
3. Run at least one command happy path, such as `/username <usuario>`
4. Run at least one second happy path, such as `/email <email>` or `/social <usuario>`
5. Confirm one validation failure returns a user-safe reply
6. Confirm one internal failure path still returns a sanitized fallback if triggered during operator testing
7. Confirm one large result still sends summary plus JSON attachment when applicable
8. Confirm rate limiting still blocks repeated abuse from one user

## Live operator verification checkpoint

This checkpoint is the current approved operational-readiness slice for Phase C.

Goal:

- verify that the documented deployment procedure matches the real Telegram runtime behavior
- capture enough operator evidence to prove runbook-to-runtime parity
- avoid new feature work during verification

Execution rule:

- run the checklist against the real deployed bot after startup validation succeeds
- record the evidence for each step before declaring the deploy verified
- if a step fails because the runtime behavior does not match this document, treat it as a concrete mismatch and route it back through the normal workflow before changing runtime code
- if a step cannot be reproduced deterministically in the operator session without changing runtime configuration, thresholds, or code, mark that step as **blocked** with captured evidence rather than forcing the checkpoint to pass

### Verification status model

Each checklist step must be recorded with exactly one status:

- **verified**: the operator executed the step and captured the required evidence
- **blocked**: the step could not be reproduced deterministically in the current environment, and the operator captured evidence showing why
- **mismatch**: the runtime behavior contradicted the runbook or the approved Telegram contract

Do not substitute one status for another. In particular:

- do not mark a non-reproducible checkpoint as verified
- do not change configuration only to force a checkpoint to trigger unless that configuration change is already part of the approved deployment state
- do not treat missing evidence as verification

### Live verification checklist with acceptance criteria

| Step | Operator action | Acceptance criteria | Evidence to capture |
|------|-----------------|---------------------|---------------------|
| 1 | Validate startup with `python -m osint_suite.telegram_bot --check-config` or deployed equivalent | Output contains `Telegram bot configuration OK` and process exits cleanly | terminal output or service log line |
| 2 | Start the bot process or restart the `systemd` unit | process stays alive, polling starts, no immediate crash loop | service status output plus first healthy log window |
| 3 | Send `/start` from an allowed Telegram user | bot replies with activation/intro text and no traceback-like content | Telegram screenshot or copied reply |
| 4 | Send `/help` | bot replies with the normalized command/help surface currently documented for Telegram | Telegram screenshot or copied reply |
| 5 | Run one representative command success path such as `/username <valor>` | bot returns a structured summary message and completes without sanitized-fallback error text | Telegram reply plus related log excerpt |
| 6 | Run one representative controlled failure path using an intentionally invalid command input | bot returns a user-safe validation/failure message with no stack trace, local path, or raw exception detail | Telegram reply plus related log excerpt |
| 7 | Run one representative long-result path that triggers JSON attachment | bot sends summary text first and JSON attachment when payload size crosses the configured threshold | Telegram screenshot showing summary and attached JSON, or blocked evidence showing that the configured threshold could not be deterministically crossed in the current operator session |
| 8 | Upload one supported document | bot accepts the upload, completes analysis, and responds with the same summary/JSON contract used for file flows | Telegram screenshot plus filename/type used |
| 9 | Upload one supported image | bot accepts the upload, completes analysis, and responds with the same summary/JSON contract used for file flows | Telegram screenshot plus filename/type used |
| 10 | Trigger a rate-limit event from one user | bot returns the expected rate-limit message and continues serving later requests after the window resets | Telegram reply plus approximate timestamps |
| 11 | Inspect recent logs after the above checks | logs show outcomes and timing signals without token leakage, traceback exposure in chat, or full sensitive payload dumps | sanitized log excerpt |

### Deterministic reproduction rule for conditional checkpoints

Some checkpoints depend on runtime conditions that may not be reproducible on demand in every operator session.

Apply the following rule:

- verify the step only when the operator can trigger it using the already deployed configuration and normal approved inputs
- mark the step as blocked when the outcome depends on an unknown or non-observable threshold, insufficiently large real-world payload, missing safe fixture, or another condition the operator cannot reproduce deterministically

Current example:

- **JSON attachment threshold:** if the operator cannot deterministically prove that the tested command or file result crossed `TELEGRAM_RESULT_FILE_THRESHOLD_BYTES` in the current deployed configuration, record step 7 as **blocked** and attach the evidence used to reach that conclusion

### Evidence capture table

Minimum evidence set per verification run:

| Evidence item | Minimum content |
|---------------|-----------------|
| Startup proof | config-check success and healthy running process |
| Telegram smoke proof | `/start` and `/help` replies |
| Success-path proof | one successful command reply |
| Controlled-failure proof | one user-safe validation or controlled failure reply |
| JSON parity proof | one summary + JSON attachment example, or blocked evidence that deterministic threshold reproduction was not possible |
| File-path proof | one document upload result and one image upload result |
| Rate-limit proof | one blocked reply from repeated requests |
| Logging proof | one log excerpt showing sanitized operational signals |

Blocked evidence should be concrete. Prefer:

- the command or upload used
- the observed Telegram reply
- the related sanitized log excerpt, if available
- the specific reason the step could not be reproduced deterministically

### Verification completion rule

Declare the deploy checkpoint **fully verified** only when all of the following are true:

- startup validation succeeded
- `/start` and `/help` passed in the real environment
- at least one success path and one controlled failure path matched the runbook
- JSON attachment behavior was observed when expected
- document and image upload flows were both verified
- rate limiting was observed in the real environment
- logs remained sanitized and operator-usable

Declare the deploy checkpoint **blocked** when all non-conditional steps passed but one or more conditional checkpoints could not be reproduced deterministically and were recorded with evidence.

Declare the deploy checkpoint **mismatched** when any verified step contradicts the runbook or the approved Telegram contract.

## Observable runtime signals

- **successful command execution:** Telegram reply contains a structured summary and, when payload is large, a JSON attachment
- **validation failure:** Telegram reply returns a short user-facing validation message without traceback
- **timeout:** Telegram reply is `La solicitud excedio el tiempo maximo de analisis.`
- **internal error:** Telegram reply is `Se produjo un error interno al procesar la solicitud.`

## Safe rollback / stop procedure

If startup or post-deploy verification fails:

1. stop the running bot process or `systemd` unit
2. keep the current environment file and logs for diagnosis
3. revert to the last known-good deployed revision
4. restart only the last verified working version
5. re-run `/start` and `/help` smoke checks before declaring recovery complete

## Suggested `systemd` service

```ini
[Unit]
Description=OSINT Suite Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/osint-suite
EnvironmentFile=/etc/osint-suite/telegram-bot.env
ExecStart=/opt/osint-suite/.venv/bin/python -m osint_suite.telegram_bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Operational notes:

- store environment variables outside the repo
- do not commit `.env` or token-bearing files
- keep deployment single-instance while concurrency and rate limiting remain in memory
- do not treat webhook or multi-replica operation as part of the current deployment model
