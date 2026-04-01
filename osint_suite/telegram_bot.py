"""
Bot público de Telegram para OSINT Suite.

Handlers finos: validan entrada, aplican rate limiting y delegan a la capa de
servicios del bot.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

from .telegram_services import CommandResult, dispatch_service


logger = logging.getLogger(__name__)


@dataclass
class TelegramBotConfig:
    bot_token: str
    allowed_users: set[int]
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 20
    long_job_threshold_seconds: int = 5
    max_concurrent_jobs: int = 1
    result_file_threshold_bytes: int = 2500

    @classmethod
    def from_env(cls) -> "TelegramBotConfig":
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("Missing TELEGRAM_BOT_TOKEN")

        raw_allowed_users = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
        allowed_users = {
            int(item.strip())
            for item in raw_allowed_users.split(",")
            if item.strip()
        }
        return cls(
            bot_token=bot_token,
            allowed_users=allowed_users,
            rate_limit_per_minute=int(os.environ.get("TELEGRAM_RATE_LIMIT_PER_MINUTE", "5")),
            rate_limit_per_hour=int(os.environ.get("TELEGRAM_RATE_LIMIT_PER_HOUR", "20")),
            long_job_threshold_seconds=int(os.environ.get("TELEGRAM_LONG_JOB_THRESHOLD_SECONDS", "5")),
            max_concurrent_jobs=int(os.environ.get("TELEGRAM_MAX_CONCURRENT_JOBS", "1")),
            result_file_threshold_bytes=int(os.environ.get("TELEGRAM_RESULT_FILE_THRESHOLD_BYTES", "2500")),
        )


class InMemoryRateLimiter:
    def __init__(self, per_minute: int, per_hour: int, max_concurrent_jobs: int) -> None:
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.max_concurrent_jobs = max_concurrent_jobs
        self._minute_buckets: dict[int, deque[float]] = defaultdict(deque)
        self._hour_buckets: dict[int, deque[float]] = defaultdict(deque)
        self._active_jobs: dict[int, int] = defaultdict(int)

    def allow_request(self, user_id: int, now: float | None = None) -> bool:
        now = now or time.time()
        minute_bucket = self._minute_buckets[user_id]
        hour_bucket = self._hour_buckets[user_id]
        self._expire(minute_bucket, now - 60)
        self._expire(hour_bucket, now - 3600)

        if len(minute_bucket) >= self.per_minute or len(hour_bucket) >= self.per_hour:
            return False

        minute_bucket.append(now)
        hour_bucket.append(now)
        return True

    def try_acquire_job_slot(self, user_id: int) -> bool:
        if self._active_jobs[user_id] >= self.max_concurrent_jobs:
            return False
        self._active_jobs[user_id] += 1
        return True

    def release_job_slot(self, user_id: int) -> None:
        if self._active_jobs[user_id] > 0:
            self._active_jobs[user_id] -= 1

    @staticmethod
    def _expire(bucket: deque[float], threshold: float) -> None:
        while bucket and bucket[0] < threshold:
            bucket.popleft()


HELP_TEXT = (
    "Comandos disponibles:\n"
    "/username <valor>\n"
    "/email <valor>\n"
    "/phone <numero>\n"
    "/company <nombre>\n"
    "/geo <lat, lon>\n"
    "\n"
    "Uso publico con rate limiting por usuario."
)


def create_application(config: TelegramBotConfig) -> Application:
    application = Application.builder().token(config.bot_token).build()
    limiter = InMemoryRateLimiter(
        per_minute=config.rate_limit_per_minute,
        per_hour=config.rate_limit_per_hour,
        max_concurrent_jobs=config.max_concurrent_jobs,
    )
    application.bot_data["config"] = config
    application.bot_data["rate_limiter"] = limiter

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("username", username_command))
    application.add_handler(CommandHandler("email", email_command))
    application.add_handler(CommandHandler("phone", phone_command))
    application.add_handler(CommandHandler("company", company_command))
    application.add_handler(CommandHandler("geo", geo_command))
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_user_allowed(update, context):
        return
    await update.effective_message.reply_text(
        "OSINT Suite Bot activo.\n"
        "Usa /help para ver comandos disponibles.\n"
        "Los resultados largos se enviaran como JSON."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_user_allowed(update, context):
        return
    await update.effective_message.reply_text(HELP_TEXT)


async def username_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "username", "Uso: /username <valor>")


async def email_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "email", "Uso: /email <valor>")


async def phone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "phone", "Uso: /phone <numero>")


async def company_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "company", "Uso: /company <nombre>")


async def geo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "geo", "Uso: /geo <lat, lon>")


async def execute_service_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_name: str,
    usage_text: str,
) -> None:
    if not await ensure_user_allowed(update, context):
        return

    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    config: TelegramBotConfig = context.application.bot_data["config"]
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]

    if not context.args:
        await message.reply_text(usage_text)
        return

    if not limiter.allow_request(user_id):
        await message.reply_text("Limite de uso excedido. Espera un momento antes de reintentar.")
        return

    if not limiter.try_acquire_job_slot(user_id):
        await message.reply_text("Ya tienes una tarea en curso. Espera a que termine antes de lanzar otra.")
        return

    raw_arguments = list(context.args)
    await message.reply_text("Procesando solicitud...")
    task = asyncio.create_task(
        run_command_job(
            context=context,
            chat_id=message.chat_id,
            user_id=user_id,
            service_name=service_name,
            raw_arguments=raw_arguments,
            long_job_threshold_seconds=config.long_job_threshold_seconds,
        )
    )
    context.chat_data.setdefault("background_tasks", set()).add(task)
    task.add_done_callback(lambda finished: context.chat_data["background_tasks"].discard(finished))


async def run_command_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    service_name: str,
    raw_arguments: list[str],
    long_job_threshold_seconds: int,
) -> None:
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        start = time.perf_counter()
        result = await asyncio.to_thread(call_service, service_name, raw_arguments)
        elapsed = time.perf_counter() - start
        if elapsed >= long_job_threshold_seconds:
            logger.info("Long Telegram job completed", extra={"service": service_name, "user_id": user_id})
        await send_command_result(context, chat_id, result)
    except ValueError as exc:
        await context.bot.send_message(chat_id=chat_id, text=str(exc))
    except Exception:
        logger.exception("Telegram command failed", extra={"service": service_name, "user_id": user_id})
        await context.bot.send_message(
            chat_id=chat_id,
            text="Se produjo un error interno al procesar la solicitud.",
        )
    finally:
        limiter.release_job_slot(user_id)


def call_service(service_name: str, raw_arguments: list[str]) -> CommandResult:
    return dispatch_service(service_name, raw_arguments)


async def send_command_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    result: CommandResult,
) -> None:
    config: TelegramBotConfig = context.application.bot_data["config"]
    payload_bytes = json.dumps(result.payload, ensure_ascii=False, indent=2).encode("utf-8")
    summary = result.summary

    if len(summary) > 3500:
        summary = summary[:3450] + "\n...[resumen truncado]"

    await context.bot.send_message(chat_id=chat_id, text=summary)

    if len(payload_bytes) >= config.result_file_threshold_bytes:
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(payload_bytes), filename=f"{result.filename_prefix}.json"),
            caption="Resultado completo en JSON.",
        )


async def ensure_user_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config: TelegramBotConfig = context.application.bot_data["config"]
    user = update.effective_user
    if user is None:
        return False
    if config.allowed_users and user.id not in config.allowed_users:
        await update.effective_message.reply_text("Este bot no esta habilitado para tu usuario.")
        return False
    return True


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bot de Telegram para OSINT Suite",
        epilog="Requiere TELEGRAM_BOT_TOKEN en el entorno.",
    )
    parser.add_argument("--check-config", action="store_true", help="Valida configuracion y sale")
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    configure_logging()
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    config = TelegramBotConfig.from_env()

    if args.check_config:
        print("Telegram bot configuration OK")
        return

    application = create_application(config)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
