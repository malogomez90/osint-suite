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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .telegram_services import (
    CommandResult,
    ControlledServiceError,
    dispatch_file_service,
    dispatch_service,
    validate_file_upload,
    validate_file_signature,
    IMAGE_FORMATS,
    DOCUMENT_FORMATS,
    is_supported_document,
)
from .telegram_osint import TelegramOSINTPool, pool_from_env


logger = logging.getLogger(__name__)
_WORKER_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="osint_suite_bot")


@dataclass
class TelegramBotConfig:
    bot_token: str
    allowed_users: set[int]
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 20
    long_job_threshold_seconds: int = 10
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
            long_job_threshold_seconds=int(os.environ.get("TELEGRAM_LONG_JOB_THRESHOLD_SECONDS", "10")),
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
    "/username <usuario> - Busca presencia de un usuario en multiples plataformas\n"
    "/email <email> - Analiza validacion, dominio y recomendaciones\n"
    "/phone <numero> [--region XX] - Analiza telefono con region opcional\n"
    "/company <nombre> [--country XX] - Investiga empresa con pais opcional\n"
    "/geo <lat, lon> - Analiza coordenadas geograficas\n"
    "/social <usuario> - Analiza perfiles sociales y referencias cruzadas\n"
    "/breach <email|usuario> - Si envias un email, analiza riesgo; Si envias un usuario, revisa fuentes de brechas\n"
    "/tg <username> - Lookup de usuario de Telegram via MTProto\n"
    "/tggroup <username> - Lookup de grupo o canal de Telegram via MTProto\n"
    "/tginfo <username> - Recon enriquecido de usuario de Telegram via MTProto\n"
    "/tggroupinfo <username> - Recon enriquecido de grupo o canal de Telegram via MTProto\n"
    "/tgresolve <username> - Resuelve cualquier username sin estar en el grupo/canal\n"
    "/tgallchats - Lista todos los chats accesibles de la cuenta userbot\n"
    "/tghealth - Verifica salud, restricciones y sesiones activas de la cuenta\n"
    "\n"
    "Archivos:\n"
    "Documento/PDF - extrae metadatos y analisis de documento\n"
    "Imagen/foto - extrae metadatos y riesgos de privacidad\n"
    "\n"
    "Uso publico con rate limiting por usuario."
)


async def _post_init(application: Application) -> None:
    """Start the userbot pool on bot startup."""
    pool = pool_from_env()
    if pool is not None:
        await pool.start()
    application.bot_data["tg_osint_pool"] = pool


async def _post_shutdown(application: Application) -> None:
    """Stop the userbot pool on bot shutdown."""
    pool = application.bot_data.get("tg_osint_pool")
    if pool is not None:
        await pool.stop()


def create_application(config: TelegramBotConfig) -> Application:
    application = (
        Application.builder()
        .token(config.bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
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
    application.add_handler(CommandHandler("tg", tg_command))
    application.add_handler(CommandHandler("tggroup", tggroup_command))
    application.add_handler(CommandHandler("tginfo", tginfo_command))
    application.add_handler(CommandHandler("tggroupinfo", tggroupinfo_command))
    application.add_handler(CommandHandler("tgresolve", tgresolve_command))
    application.add_handler(CommandHandler("tgallchats", tgallchats_command))
    application.add_handler(CommandHandler("tghealth", tghealth_command))
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
    await execute_service_command(update, context, "username", "Uso: /username <usuario>")


async def email_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "email", "Uso: /email <email>")


async def phone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "phone", "Uso: /phone <numero> [--region XX]")


async def company_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "company", "Uso: /company <nombre> [--country XX]")


async def geo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "geo", "Uso: /geo <lat, lon>")


async def social_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "social", "Uso: /social <usuario>")


async def breach_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_service_command(update, context, "breach", "Uso: /breach <email|usuario>")


async def tg_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_osint_command(update, context, "tg", "Uso: /tg <username>")


async def tggroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_osint_command(update, context, "tggroup", "Uso: /tggroup <username>")


async def tginfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_osint_command(update, context, "tginfo", "Uso: /tginfo <username>")


async def tggroupinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_osint_command(update, context, "tggroupinfo", "Uso: /tggroupinfo <username>")


async def tgresolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_osint_command(update, context, "tgresolve", "Uso: /tgresolve <username>")


async def tgallchats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_advanced_osint_command(update, context, "tgallchats", "Uso: /tgallchats")


async def tghealth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await execute_advanced_osint_command(update, context, "tghealth", "Uso: /tghealth")


async def document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    document = getattr(message, "document", None)
    if document is None:
        await message.reply_text("No se recibio ningun documento.")
        return
    file_name = getattr(document, "file_name", "") or "document.bin"
    config: TelegramBotConfig = context.application.bot_data["config"]
    if not is_allowed_extension(file_name, config.allowed_document_extensions):
        record_abuse_signal(context, "upload_policy_denied", user_id, file_name, message.chat_id)
        await message.reply_text("Extension de documento no permitida por la politica actual.")
        return
    try:
        validate_file_upload(
            "document",
            file_name,
            file_size=getattr(document, "file_size", None),
            max_upload_size_bytes=config.max_document_upload_size_bytes,
            mime_type=getattr(document, "mime_type", None),
        )
    except ValueError as exc:
        reply_text = str(exc)
        signal_name = "upload_validation_denied"
        if reply_text == "Archivo vacio o sin contenido.":
            signal_name = "empty_upload_denied"
        elif reply_text.startswith("Archivo demasiado grande."):
            signal_name = "upload_size_denied"
        record_abuse_signal(context, signal_name, user_id, file_name, message.chat_id)
        await message.reply_text(reply_text)
        return
    await execute_file_command(
        update=update,
        context=context,
        service_name="document",
        file_id=document.file_id,
        original_name=file_name,
        file_size=getattr(document, "file_size", None),
        mime_type=getattr(document, "mime_type", None),
        max_upload_size_bytes=config.max_document_upload_size_bytes,
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
    try:
        validate_file_upload(
            "image",
            "telegram_photo.jpg",
            file_size=getattr(largest_photo, "file_size", None),
            max_upload_size_bytes=config.max_image_upload_size_bytes,
        )
    except ValueError as exc:
        reply_text = str(exc)
        signal_name = "upload_validation_denied"
        if reply_text == "Archivo vacio o sin contenido.":
            signal_name = "empty_upload_denied"
        elif reply_text.startswith("Archivo demasiado grande."):
            signal_name = "upload_size_denied"
        record_abuse_signal(context, signal_name, user_id, "telegram_photo.jpg", message.chat_id)
        await message.reply_text(reply_text)
        return
    await execute_file_command(
        update=update,
        context=context,
        service_name="image",
        file_id=largest_photo.file_id,
        original_name="telegram_photo.jpg",
        file_size=getattr(largest_photo, "file_size", None),
        max_upload_size_bytes=config.max_image_upload_size_bytes,
        processing_text="Procesando imagen...",
    )


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


def build_flag_list(data: dict[str, object], keys: list[tuple[str, str]]) -> list[str]:
    flags = []
    for field_name, label in keys:
        if data.get(field_name):
            flags.append(label)
    return flags


def build_tg_summary(data: dict[str, object], username: str) -> CommandResult:
    full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "sin nombre"
    flags = build_flag_list(
        data,
        [
            ("verified", "verificado"),
            ("bot", "bot"),
            ("restricted", "restringido"),
            ("scam", "SCAM"),
            ("fake", "FAKE"),
            ("deleted", "eliminado"),
        ],
    )
    flag_str = ", ".join(flags) if flags else "ninguno"
    phone = data.get("phone") or "oculto"
    bio = data.get("bio") or "sin bio"
    summary = (
        f"Perfil Telegram @{data.get('username') or username}\n"
        f"- ID: {data['id']}\n"
        f"- Nombre: {full_name}\n"
        f"- Bio: {bio}\n"
        f"- Telefono: {phone}\n"
        f"- Flags: {flag_str}"
    )
    return CommandResult(
        summary=summary,
        payload=data,
        filename_prefix=f"tg_{username}",
    )


def build_tggroup_summary(data: dict[str, object], username: str) -> CommandResult:
    kind = "canal" if data.get("broadcast") else "supergrupo" if data.get("megagroup") else "grupo"
    members = data.get("participants_count")
    members_str = str(members) if members is not None else "desconocido"
    flags = build_flag_list(
        data,
        [
            ("verified", "verificado"),
            ("scam", "SCAM"),
            ("fake", "FAKE"),
            ("restricted", "restringido"),
        ],
    )
    flag_str = ", ".join(flags) if flags else "ninguno"
    desc = data.get("description") or "sin descripcion"
    summary = (
        f"Telegram {kind} @{data.get('username') or username}\n"
        f"- ID: {data['id']}\n"
        f"- Titulo: {data.get('title', '')}\n"
        f"- Descripcion: {desc}\n"
        f"- Miembros: {members_str}\n"
        f"- Tipo: {kind}\n"
        f"- Flags: {flag_str}\n"
        f"- Creado: {data.get('date', 'desconocido')}"
    )
    return CommandResult(
        summary=summary,
        payload=data,
        filename_prefix=f"tggroup_{username}",
    )


def build_tginfo_summary(data: dict[str, object], username: str) -> CommandResult:
    flags = build_flag_list(
        data,
        [
            ("verified", "verificado"),
            ("bot", "bot"),
            ("premium", "premium"),
            ("restricted", "restringido"),
            ("scam", "SCAM"),
            ("fake", "FAKE"),
            ("deleted", "eliminado"),
        ],
    )
    flag_str = ", ".join(flags) if flags else "ninguno"
    bio = data.get("bio") or "sin bio"
    public_usernames = ", ".join(data.get("public_usernames", []) or []) or "sin aliases"
    common_chats = data.get("common_chats_count")
    common_chats_str = str(common_chats) if common_chats is not None else "desconocido"
    language = data.get("language_code") or "desconocido"
    status_type = data.get("status_type") or "desconocido"
    photo_data = data.get("profile_photo") or {}
    photo_label = "si" if photo_data.get("has_photo") else "no"
    summary = (
        f"Recon Telegram usuario @{data.get('username') or username}\n"
        f"- ID: {data['id']}\n"
        f"- Nombre: {data.get('full_name') or 'sin nombre'}\n"
        f"- Bio: {bio}\n"
        f"- Telefono: {data.get('phone') or 'oculto'}\n"
        f"- Estado: {status_type}\n"
        f"- Idioma: {language}\n"
        f"- Chats en comun: {common_chats_str}\n"
        f"- Foto de perfil: {photo_label}\n"
        f"- Usernames publicos: {public_usernames}\n"
        f"- Flags: {flag_str}"
    )
    return CommandResult(
        summary=summary,
        payload=data,
        filename_prefix=f"tginfo_{username}",
    )


def build_tggroupinfo_summary(data: dict[str, object], username: str) -> CommandResult:
    members = data.get("participants_count")
    members_str = str(members) if members is not None else "desconocido"
    flags = build_flag_list(
        data,
        [
            ("verified", "verificado"),
            ("forum", "foro"),
            ("join_request", "join_request"),
            ("join_to_send", "join_to_send"),
            ("restricted", "restringido"),
            ("scam", "SCAM"),
            ("fake", "FAKE"),
        ],
    )
    flag_str = ", ".join(flags) if flags else "ninguno"
    public_usernames = ", ".join(data.get("public_usernames", []) or []) or "sin aliases"
    linked_chat_id = data.get("linked_chat_id") or "sin enlace"
    slowmode = data.get("slowmode_seconds")
    slowmode_str = str(slowmode) if slowmode is not None else "desactivado"
    photo_data = data.get("chat_photo") or {}
    photo_label = "si" if photo_data.get("has_photo") else "no"
    summary = (
        f"Recon Telegram {data.get('type_label') or 'grupo'} @{data.get('username') or username}\n"
        f"- ID: {data['id']}\n"
        f"- Titulo: {data.get('title', '')}\n"
        f"- Descripcion: {data.get('description') or 'sin descripcion'}\n"
        f"- Miembros: {members_str}\n"
        f"- Tipo: {data.get('type_label') or 'desconocido'}\n"
        f"- Usernames publicos: {public_usernames}\n"
        f"- Chat enlazado: {linked_chat_id}\n"
        f"- Slowmode: {slowmode_str}\n"
        f"- Foto: {photo_label}\n"
        f"- Flags: {flag_str}"
    )
    return CommandResult(
        summary=summary,
        payload=data,
        filename_prefix=f"tggroupinfo_{username}",
    )


def build_tgresolve_summary(data: dict[str, object], username: str) -> CommandResult:
    entity_type = data.get("entity_type", "unknown")
    type_label = "usuario" if entity_type == "user" else "canal" if entity_type == "channel" else "grupo"
    flags = build_flag_list(
        data,
        [
            ("verified", "verificado"),
            ("bot", "bot"),
            ("restricted", "restringido"),
            ("scam", "SCAM"),
            ("fake", "FAKE"),
            ("deleted", "eliminado"),
        ],
    )
    flag_str = ", ".join(flags) if flags else "ninguno"
    if entity_type == "user":
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "sin nombre"
        bio = data.get("bio") or "sin bio"
        phone = data.get("phone") or "oculto"
        summary = (
            f"Resolucion Telegram @{data.get('username') or username}\n"
            f"- Tipo: {type_label}\n"
            f"- ID: {data['id']}\n"
            f"- Nombre: {full_name}\n"
            f"- Bio: {bio}\n"
            f"- Telefono: {phone}\n"
            f"- Flags: {flag_str}"
        )
    else:
        kind = "canal" if data.get("broadcast") else "supergrupo" if data.get("megagroup") else "grupo"
        members = data.get("participants_count")
        members_str = str(members) if members is not None else "desconocido"
        desc = data.get("description") or "sin descripcion"
        summary = (
            f"Resolucion Telegram @{data.get('username') or username}\n"
            f"- Tipo: {kind}\n"
            f"- ID: {data['id']}\n"
            f"- Titulo: {data.get('title', '')}\n"
            f"- Descripcion: {desc}\n"
            f"- Miembros: {members_str}\n"
            f"- Flags: {flag_str}"
        )
    return CommandResult(
        summary=summary,
        payload=data,
        filename_prefix=f"tgresolve_{username}",
    )


def build_tgallchats_summary(data: dict[str, object]) -> CommandResult:
    total = data.get("total_chats", 0)
    groups = data.get("groups", 0)
    channels = data.get("channels", 0)
    summary = (
        f"Chats accesibles de la cuenta userbot\n"
        f"- Total: {total}\n"
        f"- Grupos: {groups}\n"
        f"- Canales: {channels}\n"
        f"Archivo JSON adjunto con lista completa."
    )
    return CommandResult(
        summary=summary,
        payload=data,
        filename_prefix="tgallchats",
    )


def build_tghealth_summary(data: dict[str, object]) -> CommandResult:
    account = data.get("account_label", "desconocida")
    authorized = "si" if data.get("authorized") else "no"
    restrictions = data.get("restrictions", [])
    warnings = data.get("warnings", [])
    sessions = data.get("active_sessions", [])
    current_sessions = [s for s in sessions if s.get("current")]
    summary_lines = [
        f"Salud cuenta userbot: {account}",
        f"- Autorizada: {authorized}",
        f"- User ID: {data.get('user_id', 'N/A')}",
        f"- Username: @{data.get('username', 'sin username')}",
        f"- Restricciones: {len(restrictions)}",
        f"- Advertencias: {len(warnings)}",
        f"- Sesiones activas: {len(sessions)}",
        f"- Sesion actual: {len(current_sessions)}",
    ]
    if restrictions:
        summary_lines.append(f"- ⚠️ Restricciones: {', '.join(restrictions)}")
    if warnings:
        summary_lines.append(f"- ⚠️ Advertencias: {', '.join(warnings)}")
    ttl = data.get("account_ttl_days")
    if ttl is not None:
        summary_lines.append(f"- TTL cuenta: {ttl} dias")
    return CommandResult(
        summary="\n".join(summary_lines),
        payload=data,
        filename_prefix="tghealth",
    )


async def execute_advanced_osint_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str,
    usage_text: str,
) -> None:
    """Handler for advanced userbot commands: /tgallchats, /tghealth."""
    if not await ensure_user_allowed(update, context):
        return

    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    config: TelegramBotConfig = context.application.bot_data["config"]
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]
    pool: TelegramOSINTPool | None = context.application.bot_data.get("tg_osint_pool")

    if pool is None:
        await message.reply_text(
            "Userbot no configurado. Añade TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH "
            "y TELEGRAM_USERBOT_SESSION_1 al entorno."
        )
        return

    if not limiter.allow_request(user_id):
        record_abuse_signal(context, "rate_limit_denied", user_id, command, message.chat_id)
        await message.reply_text("Limite de uso excedido. Espera un momento antes de reintentar.")
        return

    if not limiter.try_acquire_job_slot(user_id):
        record_abuse_signal(context, "concurrent_job_denied", user_id, command, message.chat_id)
        await message.reply_text("Ya tienes una tarea en curso. Espera a que termine.")
        return

    await message.reply_text("Consultando via userbot...")

    try:
        if command == "tgallchats":
            data = await pool.get_all_chats()
            result = build_tgallchats_summary(data)
        elif command == "tghealth":
            data = await pool.check_account_health()
            result = build_tghealth_summary(data)
        else:
            raise ValueError(f"Comando avanzado no reconocido: {command}")

        logger.info(
            "Advanced Telegram OSINT command completed",
            extra={"command": command, "user_id": user_id, "outcome": "success"},
        )
        await send_command_result(context, message.chat_id, result)

    except ValueError as exc:
        record_abuse_signal(context, "command_validation_denied", user_id, command, message.chat_id)
        await message.reply_text(str(exc))
    except ControlledServiceError as exc:
        await message.reply_text(str(exc))
    except Exception:
        logger.exception(
            "Advanced Telegram OSINT command failed",
            extra={"command": command, "user_id": user_id, "outcome": "internal_error"},
        )
        await message.reply_text("Se produjo un error interno al procesar la solicitud.")
    finally:
        limiter.release_job_slot(user_id)


async def execute_osint_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str,
    usage_text: str,
) -> None:
    """Handler for /tg and /tggroup — calls the userbot pool directly (async)."""
    if not await ensure_user_allowed(update, context):
        return

    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    config: TelegramBotConfig = context.application.bot_data["config"]
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]
    pool: TelegramOSINTPool | None = context.application.bot_data.get("tg_osint_pool")

    if pool is None:
        await message.reply_text(
            "Userbot no configurado. Añade TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH "
            "y TELEGRAM_USERBOT_SESSION_1 al entorno."
        )
        return

    if not context.args:
        await message.reply_text(usage_text)
        return

    if not limiter.allow_request(user_id):
        record_abuse_signal(context, "rate_limit_denied", user_id, command, message.chat_id)
        await message.reply_text("Limite de uso excedido. Espera un momento antes de reintentar.")
        return

    if not limiter.try_acquire_job_slot(user_id):
        record_abuse_signal(context, "concurrent_job_denied", user_id, command, message.chat_id)
        await message.reply_text("Ya tienes una tarea en curso. Espera a que termine.")
        return

    username = context.args[0].strip().lstrip("@")
    await message.reply_text("Consultando via userbot...")

    try:
        if command == "tg":
            data = await pool.lookup_user(username)
            result = build_tg_summary(data, username)
        elif command == "tggroup":
            data = await pool.lookup_channel(username)
            result = build_tggroup_summary(data, username)
        elif command == "tginfo":
            data = await pool.lookup_user_info(username)
            result = build_tginfo_summary(data, username)
        elif command == "tggroupinfo":
            data = await pool.lookup_channel_info(username)
            result = build_tggroupinfo_summary(data, username)
        elif command == "tgresolve":
            data = await pool.resolve_username(username)
            result = build_tgresolve_summary(data, username)
        else:
            raise ValueError(f"Comando userbot no reconocido: {command}")

        logger.info(
            "Telegram OSINT command completed",
            extra={"command": command, "user_id": user_id, "outcome": "success"},
        )
        await send_command_result(context, message.chat_id, result)

    except ValueError as exc:
        record_abuse_signal(context, "command_validation_denied", user_id, command, message.chat_id)
        await message.reply_text(str(exc))
    except ControlledServiceError as exc:
        await message.reply_text(str(exc))
    except Exception:
        logger.exception(
            "Telegram OSINT command failed",
            extra={"command": command, "user_id": user_id, "outcome": "internal_error"},
        )
        await message.reply_text("Se produjo un error interno al procesar la solicitud.")
    finally:
        limiter.release_job_slot(user_id)


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
    file_size: int | None,
    max_upload_size_bytes: int,
    mime_type: str | None = None,
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
            file_size=file_size,
            max_upload_size_bytes=max_upload_size_bytes,
            mime_type=mime_type,
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
        result = await run_blocking_in_worker(
            call_service,
            service_name,
            raw_arguments,
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
            await context.bot.send_message(
                chat_id=chat_id,
                text="La solicitud tardo mas de lo habitual. Resultado listo.",
            )
        await send_command_result(context, chat_id, result)
    except ValueError as exc:
        record_abuse_signal(context, "command_validation_denied", user_id, service_name, chat_id)
        logger.info(
            "Telegram command validation failed",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "validation"},
        )
        await context.bot.send_message(chat_id=chat_id, text=str(exc))
    except ControlledServiceError as exc:
        logger.warning(
            "Telegram command controlled failure",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "controlled_failure"},
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


def call_file_service(
    service_name: str,
    file_path: str,
    original_name: str,
    *,
    file_size: int | None = None,
    max_upload_size_bytes: int | None = None,
    mime_type: str | None = None,
) -> CommandResult:
    return dispatch_file_service(
        service_name,
        file_path,
        original_name,
        file_size=file_size,
        max_upload_size_bytes=max_upload_size_bytes,
        mime_type=mime_type,
    )


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
    file_size: int | None = None,
    max_upload_size_bytes: int | None = None,
    mime_type: str | None = None,
) -> None:
    limiter: InMemoryRateLimiter = context.application.bot_data["rate_limiter"]
    config: TelegramBotConfig = context.application.bot_data["config"]
    temp_path = ""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        temp_path = await download_file_to_temp_path(context, file_id, original_name)
        validate_file_signature(service_name, temp_path, original_name)
        start = time.perf_counter()
        call_kwargs = {}
        if file_size is not None:
            call_kwargs["file_size"] = file_size
        if max_upload_size_bytes is not None:
            call_kwargs["max_upload_size_bytes"] = max_upload_size_bytes
        if mime_type is not None:
            call_kwargs["mime_type"] = mime_type
        result = await run_blocking_in_worker(
            call_file_service,
            service_name,
            temp_path,
            original_name,
            timeout=config.analysis_timeout_seconds,
            **call_kwargs,
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
            await context.bot.send_message(
                chat_id=chat_id,
                text="La solicitud tardo mas de lo habitual. Resultado listo.",
            )
        await send_command_result(context, chat_id, result)
    except ValueError as exc:
        record_abuse_signal(context, "file_validation_denied", user_id, service_name, chat_id)
        logger.info(
            "Telegram file validation failed",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "validation"},
        )
        await context.bot.send_message(chat_id=chat_id, text=str(exc))
    except ControlledServiceError as exc:
        logger.warning(
            "Telegram file controlled failure",
            extra={"service": service_name, "user_id": user_id, "chat_id": chat_id, "outcome": "controlled_failure"},
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


async def run_blocking_in_worker(
    func,
    *args,
    timeout: float,
    **kwargs,
):
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(_WORKER_EXECUTOR, lambda: func(*args, **kwargs)),
        timeout=timeout,
    )


async def send_command_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    result: CommandResult,
) -> None:
    config: TelegramBotConfig = context.application.bot_data["config"]
    def _default(obj):
        if isinstance(obj, bytes):
            return obj.hex()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    payload_bytes = json.dumps(result.payload, ensure_ascii=False, indent=2, default=_default).encode("utf-8")
    for chunk in split_text_chunks(result.summary_text):
        await context.bot.send_message(chat_id=chat_id, text=chunk)

    if len(payload_bytes) >= config.result_file_threshold_bytes:
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(payload_bytes), filename=result.json_filename),
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
    logging.getLogger("httpx").setLevel(logging.WARNING)


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
