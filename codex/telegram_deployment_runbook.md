# Telegram Deployment Runbook (MVP)

## Purpose

This runbook prepares the **first real deployment** of the current Telegram bot MVP **without adding new features yet**. It is the operational companion to `codex/telegram_phase_c_design.md`.

## Deployment Target

Initial deployment target:

- **One Linux host**
- **One dedicated Python process**
- **Polling mode**
- **Single replica**
- **Restart managed by `systemd`**

This target is intentionally simple. It matches the current bot design:

- in-memory rate limiting
- background jobs in the same process
- no shared state across replicas

## Runtime Requirements

- Python **3.9+**
- A Telegram bot token created with BotFather
- Outbound internet access to the Telegram Bot API
- A writable working directory for the process
- A service account or host user that can keep the process running

## Required Environment Variables

Required:

- `TELEGRAM_BOT_TOKEN`

Configuration loading order at startup:

1. Existing process environment variables (highest priority)
2. Missing values loaded from a local `.env` file in the current working directory
3. If `TELEGRAM_BOT_TOKEN` is still missing, startup fails with configuration error

Optional for the first deployment:

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

## Recommended First-Deploy Values

Use these values unless the first host has tighter constraints:

```env
TELEGRAM_BOT_TOKEN=<real-token>
TELEGRAM_ALLOWED_USERS=
TELEGRAM_RATE_LIMIT_PER_MINUTE=5
TELEGRAM_RATE_LIMIT_PER_HOUR=20
TELEGRAM_LONG_JOB_THRESHOLD_SECONDS=5
TELEGRAM_MAX_CONCURRENT_JOBS=1
TELEGRAM_RESULT_FILE_THRESHOLD_BYTES=2500
TELEGRAM_MAX_UPLOAD_SIZE_BYTES=10485760
TELEGRAM_MAX_DOCUMENT_UPLOAD_SIZE_BYTES=10485760
TELEGRAM_MAX_IMAGE_UPLOAD_SIZE_BYTES=10485760
TELEGRAM_ANALYSIS_TIMEOUT_SECONDS=30
TELEGRAM_ALLOWED_DOCUMENT_EXTENSIONS=.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.rtf
TELEGRAM_ALLOWED_IMAGE_EXTENSIONS=.jpg,.jpeg,.png,.gif,.bmp,.tif,.tiff,.webp
```

Notes:

- Leave `TELEGRAM_ALLOWED_USERS` empty for public mode.
- If the first deployment should be limited to operator testing only, set `TELEGRAM_ALLOWED_USERS` to a comma-separated list of Telegram numeric user IDs.

## Install Procedure

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Optional validation before starting the bot:

```bash
export TELEGRAM_BOT_TOKEN=<real-token>
python -m osint_suite.telegram_bot --check-config
```

For local development, you can also place `TELEGRAM_BOT_TOKEN` in a `.env` file at the repository root and run the same command. If both are present, the process environment value wins.

Expected output:

```text
Telegram bot configuration OK
```

## Start Command

The current bot should be started with:

```bash
python -m osint_suite.telegram_bot
```

There is no dedicated console script yet for the Telegram bot. For the first deployment, `python -m osint_suite.telegram_bot` is the correct startup command.

## Suggested `systemd` Service

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

- Store environment variables in a root-readable file such as `/etc/osint-suite/telegram-bot.env`.
- In production, keep using real environment injection (`EnvironmentFile`, secret manager, or host env vars). The local `.env` fallback is mainly for developer ergonomics.
- Do not commit the token or the environment file.
- Keep the service as a single instance while rate limiting and background jobs remain in memory.

## First Smoke Checklist

After the process is running:

1. Send `/start`
2. Send `/help`
3. Run at least two real commands, for example `/username <value>` and `/email <value>`
4. Trigger rate limiting intentionally from one user
5. Trigger one result large enough to confirm summary plus JSON attachment behavior, if practical
6. Confirm that failures return sanitized user-facing messages

## What To Capture During First Deployment

Record these items for the next issue:

- Did the process boot cleanly?
- Did polling connect successfully?
- Which commands worked end to end?
- Did rate limiting behave as expected?
- Did any command exceed the timeout unexpectedly?
- Were logs sufficient for diagnosis without leaking sensitive payloads?

## Known Constraints And Current Blockers

Known constraints:

- The first deployment is **single-process only** because concurrency and rate limiting are in memory.
- Polling is the intended mode for the first release; webhook is intentionally deferred.
- The bot depends on the host being able to reach Telegram and the external services used by the underlying OSINT functions.

Current blockers to starting the bot:

- Missing `TELEGRAM_BOT_TOKEN`
- Missing Python dependencies from `requirements.txt`
- Host-level network restrictions that prevent Telegram API access

These are operational blockers for `SYM-104`, not feature work.
