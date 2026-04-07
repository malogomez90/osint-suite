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
import tempfile
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .telegram_services import (
    CommandResult,
    dispatch_file_service,
    dispatch_service,
    IMAGE_FORMATS,
    DOCUMENT_FORMATS,
    is_supported_document,
    normalize_filename_prefix,
)


logger = logging.getLogger(__name__)


DOCUMENT_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword", "application/x-tika-msoffice"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".xls": {"application/vnd.ms-excel", "application/x-tika-msoffice"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    ".ppt": {"application/vnd.ms-powerpoint", "application/x-tika-msoffice"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
    },
    ".odt": {"application/vnd.oasis.opendocument.text", "application/zip"},
    ".ods": {"application/vnd.oasis.opendocument.spreadsheet", "application/zip"},
    ".odp": {"application/vnd.oasis.opendocument.presentation", "application/zip"},
    ".rtf": {"application/rtf", "text/rtf"},
}


@dataclass
class TelegramBotConfig:
    bot_token: str
    allowed_users: set[int]
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 20
    long_job_threshold_seconds: int = 5
    max_concurrent_jobs: int = 1
    result_file_threshold_bytes: int = 2500
    max_upload_size_bytes: int = 10 * 1024 * 1024
    max_document_upload_size_bytes: int = 10 * 1024 * 1024
    max_image_upload_size_bytes: int = 10 * 1024 * 1024
    analysis_timeout_seconds: float = 30.0
    allowed_document_extensions: set[str] | None = None
    allowed_image_extensions: set[str] | None = None

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
        default_limit = int(os.environ.get("TELEGRAM_MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))
        return cls(
            bot_token=bot_token,
            allowed_users=allowed_users,
            rate_limit_per_minute=int(os.environ.get("TELEGRAM_RATE_LIMIT_PER_MINUTE", "5")),
            rate_limit_per_hour=int(os.environ.get("TELEGRAM_RATE_LIMIT_PER_HOUR", "20")),
            long_job_threshold_seconds=int(os.environ.get("TELEGRAM_LONG_JOB_THRESHOLD_SECONDS", "5")),
            max_concurrent_jobs=int(os.environ.get("TELEGRAM_MAX_CONCURRENT_JOBS", "1")),
            result_file_threshold_bytes=int(os.environ.get("TELEGRAM_RESULT_FILE_THRESHOLD_BYTES", "2500")),
            max_upload_size_bytes=default_limit,
            max_document_upload_size_bytes=int(
                os.environ.get("TELEGRAM_MAX_DOCUMENT_UPLOAD_SIZE_BYTES", str(default_limit))
            ),
            max_image_upload_size_bytes=int(
                os.environ.get("TELEGRAM_MAX_IMAGE_UPLOAD_SIZE_BYTES", str(default_limit))
            ),
            analysis_timeout_seconds=float(os.environ.get("TELEGRAM_ANALYSIS_TIMEOUT_SECONDS", "30")),
            allowed_document_extensions=parse_allowed_extensions(
                os.environ.get("TELEGRAM_ALLOWED_DOCUMENT_EXTENSIONS"),
                DOCUMENT_FORMATS,
            ),
            allowed_image_extensions=parse_allowed_extensions(
                os.environ.get("TELEGRAM_ALLOWED_IMAGE_EXTENSIONS"),
                IMAGE_FORMATS,
            ),
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
    "/social <valor>\n"
    "/breach <valor>\n"
    "\n"
    "Tambien puedes enviar un PDF/documento Office o una imagen para analizar metadatos.\n"
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
    application.bot_data["abuse_signals"] = defaultdict(int)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("username", username_command))
    application.add_handler(CommandHandler("email", email_command))
    application.add_handler(CommandHandler("phone", phone_command))
    application.add_handler(CommandHandler("company", company_command))
    application.add_handler(CommandHandler("geo", geo_command))
    application.add_handler(CommandHandler("social", social_command))
    application.add_handler(CommandHandler("breach", breach_command))
    application.add_handler(MessageHandler(filters.Document.ALL, document_message))
    application.add_handler(MessageHandler(filters.PHOTO, photo_message))
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


async def social_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "social", "Uso: /social <valor>")


async def breach_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "breach", "Uso: /breach <valor>")


async def document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    document = getattr(message, "document", None)
    if document is None:
        await message.reply_text("No se recibio ningun documento.")
        return
    file_name = getattr(document, "file_name", "") or "document.bin"
    if not is_supported_document(file_name):
        await message.reply_text("Formato de documento no soportado. Envia PDF u Office/OpenDocument.")
        return
    config: TelegramBotConfig = context.application.bot_data["config"]
    if not is_allowed_extension(file_name, config.allowed_document_extensions):
        record_abuse_signal(context, "upload_policy_denied", user_id, file_name, message.chat_id)
        await message.reply_text("Extension de documento no permitida por la politica actual.")
        return
    if is_empty_file(getattr(document, "file_size", None)):
        record_abuse_signal(context, "empty_upload_denied", user_id, file_name, message.chat_id)
        await message.reply_text("Archivo vacio o sin contenido.")
        return
    if not is_allowed_document_mime_type(file_name, getattr(document, "mime_type", None)):
        record_abuse_signal(context, "upload_validation_denied", user_id, file_name, message.chat_id)
        await message.reply_text("Tipo MIME de documento no soportado para este archivo.")
        return
    if is_file_too_large(getattr(document, "file_size", None), config.max_document_upload_size_bytes):
        record_abuse_signal(context, "upload_size_denied", user_id, file_name, message.chat_id)
        await message.reply_text(
            f"Archivo demasiado grande. Limite actual: {config.max_document_upload_size_bytes} bytes."
        )
        return
    await execute_file_command(
        update=update,
        context=context,
        service_name="document",
        file_id=document.file_id,
        original_name=file_name,
        processing_text="Procesando documento...",
    )


async def photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    photos = list(getattr(message, "photo", []) or [])
    if not photos:
        await message.reply_text("No se recibio ninguna imagen.")
        return
    config: TelegramBotConfig = context.application.bot_data["config"]
    largest_photo = photos[-1]
    if not is_allowed_extension("telegram_photo.jpg", config.allowed_image_extensions):
        record_abuse_signal(context, "upload_policy_denied", user_id, "telegram_photo.jpg", message.chat_id)
        await message.reply_text("Extension de imagen no permitida por la politica actual.")
        return
    if is_empty_file(getattr(largest_photo, "file_size", None)):
        record_abuse_signal(context, "empty_upload_denied", user_id, "telegram_photo.jpg", message.chat_id)
        await message.reply_text("Archivo vacio o sin contenido.")
        return
    if is_file_too_large(getattr(largest_photo, "file_size", None), config.max_image_upload_size_bytes):
        record_abuse_signal(context, "upload_size_denied", user_id, "telegram_photo.jpg", message.chat_id)
        await message.reply_text(
            f"Archivo demasiado grande. Limite actual: {config.max_image_upload_size_bytes} bytes."
        )
        return
    await execute_file_command(
        update=update,
        context=context,
        service_name="image",
        file_id=largest_photo.file_id,
        original_name="telegram_photo.jpg",
        processing_text="Procesando imagen...",
    )


def is_file_too_large(file_size: int | None, max_upload_size_bytes: int) -> bool:
    return file_size is not None and file_size > max_upload_size_bytes


def is_empty_file(file_size: int | None) -> bool:
    return file_size is not None and file_size <= 0


def is_allowed_document_mime_type(file_name: str, mime_type: str | None) -> bool:
    if not mime_type:
        return True
    allowed = DOCUMENT_MIME_TYPES.get(Path(file_name).suffix.lower())
    if not allowed:
        return True
    return mime_type in allowed


def parse_allowed_extensions(raw_value: str | None, default_extensions: Sequence[str]) -> set[str]:
    if not raw_value:
        return {extension.lower() for extension in default_extensions}
    extensions = set()
    for item in raw_value.split(","):
        value = item.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        extensions.add(value)
    return extensions or {extension.lower() for extension in default_extensions}


def is_allowed_extension(file_name: str, allowed_extensions: set[str] | None) -> bool:
    if not allowed_extensions:
        return True
    return Path(file_name).suffix.lower() in allowed_extensions


def record_abuse_signal(
    context: ContextTypes.DEFAULT_TYPE,
    signal_name: str,
    user_id: int,
    detail: str | None = None,
    chat_id: int | None = None,
) -> None:
    abuse_signals = context.application.bot_data.setdefault("abuse_signals", defaultdict(int))
    abuse_signals[signal_name] += 1
    logger.warning(
        "Telegram abuse signal recorded",
        extra={
            "signal": signal_name,
            "user_id": user_id,
            "chat_id": chat_id,
            "detail": detail,
            "outcome": "abuse_signal",
        },
    )


def validate_downloaded_upload(service_name: str, temp_path: str, original_name: str) -> None:
    with open(temp_path, "rb") as handle:
        header = handle.read(16)

    if not header:
        raise ValueError("Archivo vacio o sin contenido.")

    if service_name == "document" and not is_valid_document_signature(original_name, header):
        raise ValueError("Archivo corrupto o no coincide con el tipo esperado.")
    if service_name == "image" and not is_valid_image_signature(original_name, header):
        raise ValueError("Archivo corrupto o no coincide con el tipo esperado.")


def is_valid_document_signature(file_name: str, header: bytes) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return header.startswith(b"%PDF")
    if suffix in {".doc", ".xls", ".ppt"}:
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if suffix in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}:
        return header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if suffix == ".rtf":
        return header.startswith(b"{\\rtf")
    return True


def is_valid_image_signature(file_name: str, header: bytes) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".bmp":
        return header.startswith(b"BM")
    if suffix in {".tif", ".tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    if suffix == ".webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    return True


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
        record_abuse_signal(context, "rate_limit_denied", user_id, service_name, message.chat_id)
        await message.reply_text("Limite de uso excedido. Espera un momento antes de reintentar.")
        return

    if not limiter.try_acquire_job_slot(user_id):
        record_abuse_signal(context, "concurrent_job_denied", user_id, service_name, message.chat_id)
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


async def execute_file_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_name: str,
    file_id: str,
    original_name: str,
    processing_text: str,
) -> None:
    if not await ensure_user_allowed(update, context):
        return

    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    config: TelegramBotConfig = context.application.bot_data["config"]
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]

    if not limiter.allow_request(user_id):
        record_abuse_signal(context, "rate_limit_denied", user_id, service_name, message.chat_id)
        await message.reply_text("Limite de uso excedido. Espera un momento antes de reintentar.")
        return

    if not limiter.try_acquire_job_slot(user_id):
        record_abuse_signal(context, "concurrent_job_denied", user_id, service_name, message.chat_id)
        await message.reply_text("Ya tienes una tarea en curso. Espera a que termine antes de lanzar otra.")
        return

    await message.reply_text(processing_text)
    task = asyncio.create_task(
        run_file_job(
            context=context,
            chat_id=message.chat_id,
            user_id=user_id,
            service_name=service_name,
            file_id=file_id,
            original_name=original_name,
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
    config: TelegramBotConfig = context.application.bot_data["config"]
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        start = time.perf_counter()
        result = await asyncio.wait_for(
            asyncio.to_thread(call_service, service_name, raw_arguments),
            timeout=config.analysis_timeout_seconds,
        )
        elapsed = time.perf_counter() - start
        logger.info(
            "Telegram command completed",
            extra={
                "service": service_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "outcome": "success",
                "elapsed_seconds": elapsed,
            },
        )
        if elapsed >= long_job_threshold_seconds:
            logger.info(
                "Long Telegram job completed",
                extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "success"},
            )
        await send_command_result(context, chat_id, result)
    except ValueError as exc:
        record_abuse_signal(context, "command_validation_denied", user_id, service_name, chat_id)
        logger.info(
            "Telegram command validation failed",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "validation"},
        )
        await context.bot.send_message(chat_id=chat_id, text=str(exc))
    except asyncio.TimeoutError:
        logger.warning(
            "Telegram command timed out",
            extra={
                "service": service_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "outcome": "timeout",
                "timeout_seconds": config.analysis_timeout_seconds,
            },
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="La solicitud excedio el tiempo maximo de analisis.",
        )
    except Exception:
        logger.exception(
            "Telegram command failed",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "internal_error"},
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Se produjo un error interno al procesar la solicitud.",
        )
    finally:
        limiter.release_job_slot(user_id)


def call_service(service_name: str, raw_arguments: list[str]) -> CommandResult:
    return dispatch_service(service_name, raw_arguments)


def call_file_service(service_name: str, file_path: str, original_name: str) -> CommandResult:
    return dispatch_file_service(service_name, file_path, original_name)


def split_text_chunks(text: str, max_chunk_length: int = 3500) -> list[str]:
    if len(text) <= max_chunk_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chunk_length:
        split_at = remaining.rfind("\n", 0, max_chunk_length)
        if split_at <= 0:
            split_at = max_chunk_length
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def download_file_to_temp_path(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    original_name: str,
) -> str:
    suffix = Path(original_name).suffix or ".bin"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=temp_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return temp_path


async def run_file_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    service_name: str,
    file_id: str,
    original_name: str,
    long_job_threshold_seconds: int,
) -> None:
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]
    config: TelegramBotConfig = context.application.bot_data["config"]
    temp_path = ""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        temp_path = await download_file_to_temp_path(context, file_id, original_name)
        validate_downloaded_upload(service_name, temp_path, original_name)
        start = time.perf_counter()
        result = await asyncio.wait_for(
            asyncio.to_thread(call_file_service, service_name, temp_path, original_name),
            timeout=config.analysis_timeout_seconds,
        )
        elapsed = time.perf_counter() - start
        logger.info(
            "Telegram file job completed",
            extra={
                "service": service_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "outcome": "success",
                "elapsed_seconds": elapsed,
            },
        )
        if elapsed >= long_job_threshold_seconds:
            logger.info(
                "Long Telegram file job completed",
                extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "success"},
            )
        await send_command_result(context, chat_id, result)
    except ValueError as exc:
        record_abuse_signal(context, "file_validation_denied", user_id, service_name, chat_id)
        logger.info(
            "Telegram file validation failed",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "validation"},
        )
        await context.bot.send_message(chat_id=chat_id, text=str(exc))
    except asyncio.TimeoutError:
        logger.warning(
            "Telegram file job timed out",
            extra={
                "service": service_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "outcome": "timeout",
                "timeout_seconds": config.analysis_timeout_seconds,
            },
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="La solicitud excedio el tiempo maximo de analisis.",
        )
    except Exception:
        logger.exception(
            "Telegram file command failed",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "internal_error"},
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Se produjo un error interno al procesar la solicitud.",
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        limiter.release_job_slot(user_id)


async def send_command_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    result: CommandResult,
) -> None:
    config: TelegramBotConfig = context.application.bot_data["config"]
    payload_bytes = json.dumps(result.payload, ensure_ascii=False, indent=2).encode("utf-8")
    for chunk in split_text_chunks(result.summary):
        await context.bot.send_message(chat_id=chat_id, text=chunk)

    if len(payload_bytes) >= config.result_file_threshold_bytes:
        normalized_filename = f"{normalize_filename_prefix(result.filename_prefix)}.json"
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(payload_bytes), filename=normalized_filename),
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


def load_dotenv_defaults(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if not key or key in os.environ:
            continue
        value = value.strip().strip("'\"")
        os.environ[key] = value


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
    load_dotenv_defaults()
    config = TelegramBotConfig.from_env()

    if args.check_config:
        print("Telegram bot configuration OK")
        return

    application = create_application(config)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
