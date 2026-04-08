import os
import asyncio
import time
import sys
import io
from pathlib import Path
from types import SimpleNamespace

import pytest


import osint_suite.telegram_bot as telegram_bot_module
import osint_suite.telegram_services as telegram_services
from osint_suite.telegram_bot import (
    HELP_TEXT,
    TelegramBotConfig,
    InMemoryRateLimiter,
    load_dotenv_defaults,
    call_service,
    call_file_service,
    record_abuse_signal,
    start_command,
    help_command,
    username_command,
    tginfo_command,
    tggroupinfo_command,
    tgresolve_command,
    tgallchats_command,
    tghealth_command,
    document_message,
    photo_message,
    send_command_result,
    run_command_job,
    run_file_job,
    create_application,
)
from osint_suite.telegram_services import run_username_lookup
from osint_suite.telegram_services import (
    CommandResult,
    ControlledServiceError,
    FileServiceError,
    format_summary,
    run_document_lookup,
    run_image_lookup,
    dispatch_service,
    dispatch_file_service,
)
from osint_suite.document_analyzer import DocumentAnalyzer


class FakeMessage:
    def __init__(self, chat_id=100, document=None, photo=None):
        self.chat_id = chat_id
        self.document = document
        self.photo = photo or []
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class FakeTelegramFile:
    def __init__(self, payload=b"sample"):
        self.payload = payload

    async def download_to_drive(self, custom_path):
        with open(custom_path, "wb") as handle:
            handle.write(self.payload)


class FakeBot:
    def __init__(self):
        self.messages = []
        self.documents = []
        self.actions = []
        self.files = {}

    async def send_message(self, chat_id, text):
        self.messages.append({"chat_id": chat_id, "text": text})

    async def send_document(self, chat_id, document, caption=None):
        self.documents.append({"chat_id": chat_id, "document": document, "caption": caption})

    async def send_chat_action(self, chat_id, action):
        self.actions.append({"chat_id": chat_id, "action": action})

    async def get_file(self, file_id):
        return self.files[file_id]


class FakeContext:
    def __init__(self, config, rate_limiter=None, args=None):
        self.args = args or []
        self.bot = FakeBot()
        self.application = SimpleNamespace(
            bot_data={
                "config": config,
                "rate_limiter": rate_limiter or InMemoryRateLimiter(5, 20, 1),
            }
        )
        self.chat_data = {}


def get_abuse_signals(context):
    return context.application.bot_data.get("abuse_signals", {})


async def drain_background_tasks(context):
    tasks = list(context.chat_data.get("background_tasks", set()))
    if tasks:
        await asyncio.gather(*tasks)


async def run_handler_and_background(handler, update, context):
    await handler(update, context)
    await drain_background_tasks(context)


def make_update(user_id=42, chat_id=100):
    message = FakeMessage(chat_id=chat_id)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
    )


def fixture_path(name):
    return Path(__file__).resolve().parent / "fixtures" / name


def test_telegram_config_reads_token_and_limits_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("TELEGRAM_RATE_LIMIT_PER_HOUR", "33")
    monkeypatch.setenv("TELEGRAM_LONG_JOB_THRESHOLD_SECONDS", "9")
    monkeypatch.setenv("TELEGRAM_MAX_UPLOAD_SIZE_BYTES", "2048")
    monkeypatch.setenv("TELEGRAM_ANALYSIS_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("TELEGRAM_MAX_DOCUMENT_UPLOAD_SIZE_BYTES", "4096")
    monkeypatch.setenv("TELEGRAM_MAX_IMAGE_UPLOAD_SIZE_BYTES", "1024")
    monkeypatch.setenv("TELEGRAM_ALLOWED_DOCUMENT_EXTENSIONS", ".pdf,.docx")
    monkeypatch.setenv("TELEGRAM_ALLOWED_IMAGE_EXTENSIONS", ".jpg,.png")

    config = TelegramBotConfig.from_env()

    assert config.bot_token == "token-123"
    assert config.rate_limit_per_minute == 7
    assert config.rate_limit_per_hour == 33
    assert config.long_job_threshold_seconds == 9
    assert config.max_upload_size_bytes == 2048
    assert config.analysis_timeout_seconds == 12
    assert config.max_document_upload_size_bytes == 4096
    assert config.max_image_upload_size_bytes == 1024
    assert config.allowed_document_extensions == {".pdf", ".docx"}
    assert config.allowed_image_extensions == {".jpg", ".png"}


def test_telegram_config_requires_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        TelegramBotConfig.from_env()


def test_load_dotenv_defaults_reads_token_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=dotenv-token\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    load_dotenv_defaults()

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "dotenv-token"


def test_load_dotenv_defaults_reads_token_from_utf8_bom_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=dotenv-token\n", encoding="utf-8-sig")
    monkeypatch.chdir(tmp_path)

    load_dotenv_defaults()

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "dotenv-token"


def test_load_dotenv_defaults_keeps_process_env_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "process-token")
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=dotenv-token\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    load_dotenv_defaults()

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "process-token"


def test_load_dotenv_defaults_still_fails_when_token_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)

    load_dotenv_defaults()

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        TelegramBotConfig.from_env()


def test_dispatch_service_suppresses_unicode_stdout_from_underlying_tools(monkeypatch):
    fake_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")

    def noisy_handler(value):
        print("✗ salida interna")
        return CommandResult(summary=f"ok {value}", payload={}, filename_prefix="demo")

    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setitem(telegram_services.SERVICE_HANDLERS, "username", noisy_handler)

    result = dispatch_service("username", ["demo"])

    assert result.summary == "ok demo"


def test_rate_limiter_blocks_when_per_minute_limit_reached():
    limiter = InMemoryRateLimiter(per_minute=2, per_hour=10, max_concurrent_jobs=1)

    assert limiter.allow_request(user_id=42) is True
    assert limiter.allow_request(user_id=42) is True
    assert limiter.allow_request(user_id=42) is False


def test_rate_limiter_limits_one_long_job_per_user():
    limiter = InMemoryRateLimiter(per_minute=10, per_hour=10, max_concurrent_jobs=1)

    assert limiter.try_acquire_job_slot(user_id=7) is True
    assert limiter.try_acquire_job_slot(user_id=7) is False

    limiter.release_job_slot(user_id=7)

    assert limiter.try_acquire_job_slot(user_id=7) is True


def test_username_service_returns_summary_and_payload(monkeypatch):
    class FakeSearcher:
        def __init__(self, delay=1.0):
            self.delay = delay

        def search(self, username, platforms=None, max_workers=5):
            return {
                "username": username,
                "total_checked": 3,
                "found": [
                    {"platform": "GitHub", "profile_url": "https://github.com/testuser"},
                    {"platform": "Reddit", "profile_url": "https://reddit.com/u/testuser"},
                ],
                "not_found": [{"platform": "Instagram"}],
                "errors": [],
            }

    monkeypatch.setattr("osint_suite.telegram_services.UsernameSearcher", FakeSearcher)

    result = run_username_lookup("testuser")

    assert "testuser" in result.summary
    assert "GitHub" in result.summary
    assert result.payload["username"] == "testuser"
    assert result.filename_prefix == "username_testuser"


def test_start_command_replies_with_bot_summary():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config)

    asyncio.run(start_command(update, context))

    assert "OSINT Suite Bot activo." in update.effective_message.replies[0]


def test_help_command_replies_with_help_text():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config)

    asyncio.run(help_command(update, context))

    assert update.effective_message.replies == [HELP_TEXT]


def test_username_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(username_command(update, context))

    assert update.effective_message.replies == ["Uso: /username <usuario>"]


def test_username_command_replies_when_rate_limited():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    limiter = InMemoryRateLimiter(1, 10, 1)
    limiter.allow_request(user_id=42)
    update = make_update()
    context = FakeContext(config, rate_limiter=limiter, args=["john"])

    asyncio.run(username_command(update, context))

    assert update.effective_message.replies == ["Limite de uso excedido. Espera un momento antes de reintentar."]
    assert get_abuse_signals(context)["rate_limit_denied"] == 1


def test_username_command_replies_when_job_slot_is_busy():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    limiter = InMemoryRateLimiter(5, 10, 1)
    limiter.try_acquire_job_slot(user_id=42)
    update = make_update()
    context = FakeContext(config, rate_limiter=limiter, args=["john"])

    asyncio.run(username_command(update, context))

    assert update.effective_message.replies == [
        "Ya tienes una tarea en curso. Espera a que termine antes de lanzar otra."
    ]


def test_help_text_describes_commands_and_uploads():
    assert "/username <usuario>" in HELP_TEXT
    assert "/email <email>" in HELP_TEXT
    assert "/phone <numero> [--region XX]" in HELP_TEXT
    assert "/company <nombre> [--country XX]" in HELP_TEXT
    assert "/geo <lat, lon>" in HELP_TEXT
    assert "/social <usuario>" in HELP_TEXT
    assert "/breach <email|usuario>" in HELP_TEXT
    assert "/tg <username>" in HELP_TEXT
    assert "/tggroup <username>" in HELP_TEXT
    assert "/tginfo <username>" in HELP_TEXT
    assert "/tggroupinfo <username>" in HELP_TEXT
    assert "Busca presencia de un usuario en multiples plataformas" in HELP_TEXT
    assert "Analiza perfiles sociales y referencias cruzadas" in HELP_TEXT
    assert "Si envias un email" in HELP_TEXT
    assert "Si envias un usuario" in HELP_TEXT
    assert "Documento/PDF" in HELP_TEXT
    assert "Imagen/foto" in HELP_TEXT


def test_dispatch_service_supports_social_handler(monkeypatch):
    def fake_social_handler(value):
        return CommandResult(summary=f"social {value}", payload={"value": value}, filename_prefix="social_demo")

    monkeypatch.setitem(telegram_services.SERVICE_HANDLERS, "social", fake_social_handler)

    result = dispatch_service("social", ["demo-user"])

    assert result.summary == "social demo-user"
    assert result.payload == {"value": "demo-user"}


def test_dispatch_service_supports_breach_handler(monkeypatch):
    def fake_breach_handler(value):
        return CommandResult(summary=f"breach {value}", payload={"value": value}, filename_prefix="breach_demo")

    monkeypatch.setitem(telegram_services.SERVICE_HANDLERS, "breach", fake_breach_handler)

    result = dispatch_service("breach", ["demo@example.com"])

    assert result.summary == "breach demo@example.com"
    assert result.payload == {"value": "demo@example.com"}


def test_social_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(telegram_bot_module.social_command(update, context))

    assert update.effective_message.replies == ["Uso: /social <usuario>"]


def test_breach_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(telegram_bot_module.breach_command(update, context))

    assert update.effective_message.replies == ["Uso: /breach <email|usuario>"]


def test_email_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(telegram_bot_module.email_command(update, context))

    assert update.effective_message.replies == ["Uso: /email <email>"]


def test_phone_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(telegram_bot_module.phone_command(update, context))

    assert update.effective_message.replies == ["Uso: /phone <numero> [--region XX]"]


def test_company_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(telegram_bot_module.company_command(update, context))

    assert update.effective_message.replies == ["Uso: /company <nombre> [--country XX]"]


def test_geo_command_requires_argument():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(telegram_bot_module.geo_command(update, context))

    assert update.effective_message.replies == ["Uso: /geo <lat, lon>"]


def test_run_social_lookup_returns_summary_and_payload(monkeypatch):
    class FakeAnalyzer:
        def __init__(self, delay=0.2):
            self.delay = delay

        def cross_reference(self, username):
            return {
                "username": username,
                "platforms_checked": ["instagram", "twitter", "github"],
                "profiles_found": [{"platform": "GitHub"}],
                "profiles_not_found": [{"platform": "Instagram"}],
                "cross_references": [{"platform": "github", "url": "https://github.com/demo"}],
            }

    monkeypatch.setattr("osint_suite.telegram_services.SocialMediaAnalyzer", FakeAnalyzer)

    result = telegram_services.run_social_lookup("demo_user")

    assert result.payload["username"] == "demo_user"
    assert "Analisis social @demo_user" in result.summary
    assert "Plataformas revisadas" in result.summary
    assert result.filename_prefix == "social_demo_user"


def test_run_breach_lookup_returns_email_risk_summary(monkeypatch):
    class FakeChecker:
        def analyze_exposure_risk(self, value):
            return {
                "email": value,
                "risk_level": "medium",
                "risk_factors": [{"type": "free_email"}],
                "recommendations": ["usa 2fa", "usa alias"],
            }

    monkeypatch.setattr("osint_suite.telegram_services.BreachChecker", FakeChecker)

    result = telegram_services.run_breach_lookup("demo@example.com")

    assert result.payload["email"] == "demo@example.com"
    assert "Analisis de brechas demo@example.com" in result.summary
    assert "Nivel de riesgo: medium" in result.summary
    assert result.filename_prefix == "breach_demo_at_example.com"


def test_run_breach_lookup_returns_username_summary(monkeypatch):
    class FakeChecker:
        def check_username_breach(self, value):
            return {
                "username": value,
                "sources_checked": [{"name": "LeakCheck"}, {"name": "IntelX"}],
                "potential_breaches": [],
                "recommendations": ["verificar manualmente"],
            }

    monkeypatch.setattr("osint_suite.telegram_services.BreachChecker", FakeChecker)

    result = telegram_services.run_breach_lookup("demo_user")

    assert result.payload["username"] == "demo_user"
    assert "Analisis de brechas demo_user" in result.summary
    assert "Fuentes revisadas: 2" in result.summary
    assert result.filename_prefix == "breach_demo_user"


def test_create_application_registers_all_service_commands():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())

    application = telegram_bot_module.create_application(config)

    registered_commands = {
        next(iter(handler.commands))
        for group in application.handlers.values()
        for handler in group
        if hasattr(handler, "commands")
    }

    expected_commands = {
        "start",
        "help",
        "username",
        "email",
        "phone",
        "company",
        "geo",
        "social",
        "breach",
        "tg",
        "tggroup",
        "tginfo",
        "tggroupinfo",
    }

    assert expected_commands.issubset(registered_commands)


def test_tginfo_command_replies_when_userbot_is_not_configured():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])

    asyncio.run(tginfo_command(update, context))

    assert update.effective_message.replies == [
        "Userbot no configurado. Añade TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH y TELEGRAM_USERBOT_SESSION_1 al entorno."
    ]


def test_tginfo_command_requires_argument_when_pool_exists():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])
    context.application.bot_data["tg_osint_pool"] = object()

    asyncio.run(tginfo_command(update, context))

    assert update.effective_message.replies == ["Uso: /tginfo <username>"]


def test_tginfo_command_returns_summary_and_json(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=10)
    update = make_update()
    context = FakeContext(config, args=["demo_user"])

    class FakePool:
        async def lookup_user_info(self, username):
            assert username == "demo_user"
            return {
                "id": 123,
                "username": "demo_user",
                "full_name": "Demo User",
                "bio": "investigator",
                "phone": None,
                "status_type": "UserStatusOnline",
                "language_code": "es",
                "common_chats_count": 2,
                "profile_photo": {"has_photo": True},
                "public_usernames": ["demo_user", "demo_alias"],
                "verified": True,
                "premium": True,
                "bot": False,
                "restricted": False,
                "scam": False,
                "fake": False,
                "deleted": False,
                "payload_padding": "x" * 100,
            }

    context.application.bot_data["tg_osint_pool"] = FakePool()

    asyncio.run(tginfo_command(update, context))

    assert update.effective_message.replies == ["Consultando via userbot..."]
    assert len(context.bot.messages) == 1
    assert "Recon Telegram usuario @demo_user" in context.bot.messages[0]["text"]
    assert "Idioma: es" in context.bot.messages[0]["text"]
    assert len(context.bot.documents) == 1
    assert context.bot.documents[0]["document"].filename == "tginfo_demo_user.json"


def test_tggroupinfo_command_returns_summary(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["demo_group"])

    class FakePool:
        async def lookup_channel_info(self, username):
            assert username == "demo_group"
            return {
                "id": 999,
                "username": "demo_group",
                "title": "Demo Group",
                "description": "public intel",
                "participants_count": 321,
                "type_label": "supergrupo",
                "public_usernames": ["demo_group"],
                "linked_chat_id": 444,
                "slowmode_seconds": 30,
                "chat_photo": {"has_photo": False},
                "verified": True,
                "forum": True,
                "join_request": False,
                "join_to_send": True,
                "restricted": False,
                "scam": False,
                "fake": False,
            }

    context.application.bot_data["tg_osint_pool"] = FakePool()

    asyncio.run(tggroupinfo_command(update, context))

    assert update.effective_message.replies == ["Consultando via userbot..."]
    assert len(context.bot.messages) == 1
    assert "Recon Telegram supergrupo @demo_group" in context.bot.messages[0]["text"]
    assert "Slowmode: 30" in context.bot.messages[0]["text"]


def test_tginfo_command_surfaces_validation_error_from_pool():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["wrongtarget"])

    class FakePool:
        async def lookup_user_info(self, username):
            raise ValueError("Ese username corresponde a un grupo o canal. Usa /tggroupinfo.")

    context.application.bot_data["tg_osint_pool"] = FakePool()

    asyncio.run(tginfo_command(update, context))

    assert update.effective_message.replies == [
        "Consultando via userbot...",
        "Ese username corresponde a un grupo o canal. Usa /tggroupinfo.",
    ]
    assert get_abuse_signals(context)["command_validation_denied"] == 1


def test_tggroupinfo_command_surfaces_validation_error_from_pool():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["person"])

    class FakePool:
        async def lookup_channel_info(self, username):
            raise ValueError("Ese username corresponde a un usuario. Usa /tginfo.")

    context.application.bot_data["tg_osint_pool"] = FakePool()

    asyncio.run(tggroupinfo_command(update, context))

    assert update.effective_message.replies == [
        "Consultando via userbot...",
        "Ese username corresponde a un usuario. Usa /tginfo.",
    ]
    assert get_abuse_signals(context)["command_validation_denied"] == 1


def test_tginfo_command_surfaces_controlled_failure():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["demo"])

    class FakePool:
        async def lookup_user_info(self, username):
            raise ControlledServiceError("Userbot en espera por flood limit. Reintenta en unos minutos.")

    context.application.bot_data["tg_osint_pool"] = FakePool()

    asyncio.run(tginfo_command(update, context))

    assert update.effective_message.replies == [
        "Consultando via userbot...",
        "Userbot en espera por flood limit. Reintenta en unos minutos.",
    ]


def test_all_service_handlers_have_command_or_file_registration():
    command_names = {"username", "email", "phone", "company", "geo", "social", "breach"}
    file_service_names = {"document", "image"}

    assert command_names == set(telegram_services.SERVICE_HANDLERS.keys())
    assert file_service_names == set(telegram_services.FILE_HANDLERS.keys())


def test_send_command_result_attaches_json_when_payload_is_large():
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=20)
    context = FakeContext(config)
    result = CommandResult(
        summary="Resumen corto",
        payload={"data": "x" * 100},
        filename_prefix="User Name/John.Doe",
    )

    asyncio.run(send_command_result(context, 100, result))

    assert context.bot.messages == [{"chat_id": 100, "text": "Resumen corto"}]
    assert len(context.bot.documents) == 1
    assert context.bot.documents[0]["caption"] == "Resultado completo en JSON."
    assert context.bot.documents[0]["document"].filename == "user_name_john_doe.json"


def test_command_result_exposes_normalized_contract_fields():
    result = CommandResult(
        summary="  Resumen consistente  ",
        payload={"ok": True},
        filename_prefix="User Name/John.Doe",
    )

    assert result.summary_text == "Resumen consistente"
    assert result.json_filename == "user_name_john_doe.json"


def test_send_command_result_chunks_long_summary_before_json_fallback():
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=1000)
    context = FakeContext(config)
    long_line = "A" * 2000
    result = CommandResult(
        summary=f"{long_line}\n{long_line}\n{long_line}",
        payload={"kind": "small"},
        filename_prefix="chunk_test",
    )

    asyncio.run(send_command_result(context, 100, result))

    assert len(context.bot.messages) >= 2
    assert all(len(item["text"]) <= 3500 for item in context.bot.messages)
    assert context.bot.documents == []


def test_send_command_result_chunks_summary_and_still_attaches_json_for_large_payload():
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=40)
    context = FakeContext(config)
    long_summary = ("Bloque largo " * 400).strip()
    result = CommandResult(
        summary=long_summary,
        payload={"data": "x" * 200},
        filename_prefix="chunk_big",
    )

    asyncio.run(send_command_result(context, 100, result))

    assert len(context.bot.messages) >= 2
    assert len(context.bot.documents) == 1
    assert context.bot.documents[0]["document"].filename == "chunk_big.json"


def test_send_command_result_uses_command_result_contract_for_summary_and_json():
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=40)
    context = FakeContext(config)
    result = CommandResult(
        summary="  Resumen por contrato  ",
        payload={"data": "x" * 200},
        filename_prefix="Result Contract",
    )

    asyncio.run(send_command_result(context, 100, result))

    assert context.bot.messages == [{"chat_id": 100, "text": "Resumen por contrato"}]
    assert len(context.bot.documents) == 1
    assert context.bot.documents[0]["document"].filename == "result_contract.json"


def test_format_summary_uses_bulleted_lines_for_scanability():
    summary = format_summary(
        "Analisis de ejemplo",
        [
            ("Campo A", "valor"),
            ("Campo B", "otro"),
        ],
    )

    assert summary == "Analisis de ejemplo\n- Campo A: valor\n- Campo B: otro"


def test_run_command_job_returns_sanitized_internal_error(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)

    def fail_call_service(service_name, raw_arguments):
        raise RuntimeError("sensitive backend trace")

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", fail_call_service)

    asyncio.run(
        run_command_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="username",
            raw_arguments=["john"],
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "Se produjo un error interno al procesar la solicitud."}
    ]


def test_run_command_job_logs_operator_facing_success_fields(monkeypatch, caplog):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)

    def successful_call_service(service_name, raw_arguments):
        return CommandResult(summary="ok", payload={}, filename_prefix="ok")

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", successful_call_service)

    with caplog.at_level("INFO"):
        asyncio.run(
            run_command_job(
                context,
                chat_id=100,
                user_id=42,
                service_name="username",
                raw_arguments=["john"],
                long_job_threshold_seconds=30,
            )
        )

    success_record = next(record for record in caplog.records if record.message == "Telegram command completed")
    assert success_record.service == "username"
    assert success_record.user_id == 42
    assert success_record.chat_id == 100
    assert success_record.outcome == "success"
    assert success_record.elapsed_seconds >= 0


def test_run_command_job_sends_long_job_notice_before_result(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)

    def successful_call_service(service_name, raw_arguments):
        return CommandResult(summary="Resumen largo", payload={}, filename_prefix="ok")

    perf_counter_values = iter([10.0, 16.5])

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", successful_call_service)
    monkeypatch.setattr("osint_suite.telegram_bot.time.perf_counter", lambda: next(perf_counter_values))

    asyncio.run(
        run_command_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="username",
            raw_arguments=["john"],
            long_job_threshold_seconds=5,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "La solicitud tardo mas de lo habitual. Resultado listo."},
        {"chat_id": 100, "text": "Resumen largo"},
    ]


def test_run_command_job_replies_when_analysis_times_out(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), analysis_timeout_seconds=0.01)
    context = FakeContext(config)

    def slow_call_service(service_name, raw_arguments):
        time.sleep(0.05)
        return CommandResult(summary="late", payload={}, filename_prefix="late")

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", slow_call_service)

    asyncio.run(
        run_command_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="username",
            raw_arguments=["john"],
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "La solicitud excedio el tiempo maximo de analisis."}
    ]


def test_run_command_job_replies_with_validation_error_and_releases_slot(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)
    limiter = context.application.bot_data["rate_limiter"]
    assert limiter.try_acquire_job_slot(user_id=42) is True

    def fail_call_service(service_name, raw_arguments):
        raise ValueError("Parametro invalido")

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", fail_call_service)

    asyncio.run(
        run_command_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="username",
            raw_arguments=["john"],
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [{"chat_id": 100, "text": "Parametro invalido"}]
    assert get_abuse_signals(context)["command_validation_denied"] == 1
    assert limiter.try_acquire_job_slot(user_id=42) is True


def test_run_command_job_releases_slot_after_internal_error(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)
    limiter = context.application.bot_data["rate_limiter"]
    assert limiter.try_acquire_job_slot(user_id=42) is True

    def fail_call_service(service_name, raw_arguments):
        raise RuntimeError("boom")

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", fail_call_service)

    asyncio.run(
        run_command_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="username",
            raw_arguments=["john"],
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "Se produjo un error interno al procesar la solicitud."}
    ]
    assert limiter.try_acquire_job_slot(user_id=42) is True


def test_record_abuse_signal_logs_signal_details_for_operator_visibility(caplog):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)

    with caplog.at_level("WARNING"):
        record_abuse_signal(
            context,
            "rate_limit_denied",
            user_id=42,
            detail="username",
            chat_id=100,
        )

    warning_record = next(record for record in caplog.records if record.message == "Telegram abuse signal recorded")
    assert warning_record.signal == "rate_limit_denied"
    assert warning_record.user_id == 42
    assert warning_record.chat_id == 100
    assert warning_record.detail == "username"
    assert warning_record.outcome == "abuse_signal"


def test_call_service_parses_phone_region_option(monkeypatch):
    captured = {}

    def fake_phone_lookup(phone_number, region="US"):
        captured["phone_number"] = phone_number
        captured["region"] = region
        return CommandResult(summary="ok", payload={}, filename_prefix="phone")

    monkeypatch.setattr("osint_suite.telegram_services.run_phone_lookup", fake_phone_lookup)

    result = call_service("phone", ["--region", "ES", "+34", "612", "345", "678"])

    assert result.summary == "ok"
    assert captured == {"phone_number": "+34 612 345 678", "region": "ES"}


def test_call_service_parses_company_country_option(monkeypatch):
    captured = {}

    def fake_company_lookup(company_name, country_code=None):
        captured["company_name"] = company_name
        captured["country_code"] = country_code
        return CommandResult(summary="ok", payload={}, filename_prefix="company")

    monkeypatch.setattr("osint_suite.telegram_services.run_company_lookup", fake_company_lookup)

    result = call_service("company", ["--country", "ES", "Acme", "Labs"])

    assert result.summary == "ok"
    assert captured == {"company_name": "Acme Labs", "country_code": "ES"}


@pytest.mark.parametrize(
    ("service_name", "raw_arguments", "expected_message"),
    [
        ("username", [], "Solicitud invalida. Usa /username <usuario>."),
        ("email", [], "Solicitud invalida. Usa /email <email>."),
        ("phone", [], "Solicitud invalida. Usa /phone <numero> [--region XX]."),
        ("company", [], "Solicitud invalida. Usa /company <nombre> [--country XX]."),
        ("geo", [], "Solicitud invalida. Usa /geo <lat, lon>."),
        ("social", [], "Solicitud invalida. Usa /social <usuario>."),
        ("breach", [], "Solicitud invalida. Usa /breach <email|usuario>."),
    ],
)
def test_call_service_normalizes_missing_arguments_per_command(service_name, raw_arguments, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        call_service(service_name, raw_arguments)


@pytest.mark.parametrize(
    ("service_name", "raw_arguments", "expected_message"),
    [
        ("email", ["not-an-email"], "Solicitud invalida. Revisa los parametros e intenta de nuevo."),
        ("phone", ["--region", "ES"], "Solicitud invalida. Usa /phone <numero> [--region XX]."),
        (
            "phone",
            ["+34", "600123123", "--region", "ES"],
            "Solicitud invalida. Usa /phone <numero> [--region XX].",
        ),
        (
            "company",
            ["Acme", "Labs", "--country", "ES"],
            "Solicitud invalida. Usa /company <nombre> [--country XX].",
        ),
        ("geo", ["north", "west"], "Solicitud invalida. Revisa los parametros e intenta de nuevo."),
    ],
)
def test_call_service_normalizes_malformed_or_unsupported_argument_shapes(
    service_name,
    raw_arguments,
    expected_message,
):
    with pytest.raises(ValueError, match=expected_message):
        call_service(service_name, raw_arguments)


@pytest.mark.parametrize(
    ("service_name", "raw_arguments"),
    [
        ("username", ["demo"]),
        ("email", ["demo@example.com"]),
        ("geo", ["40.4168,", "-3.7038"]),
        ("social", ["demo"]),
        ("breach", ["demo"]),
    ],
)
def test_call_service_normalizes_controlled_tool_failures_across_current_telegram_capabilities(
    monkeypatch,
    service_name,
    raw_arguments,
):
    def controlled_failure(value):
        raise RuntimeError("backend detail should not leak")

    monkeypatch.setitem(telegram_services.SERVICE_HANDLERS, service_name, controlled_failure)

    with pytest.raises(
        RuntimeError,
        match="No se pudo completar la solicitud con la capacidad solicitada. Reintenta mas tarde.",
    ):
        call_service(service_name, raw_arguments)


def test_run_command_job_uses_same_controlled_failure_message_for_phone(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)

    def controlled_failure(service_name, raw_arguments):
        raise ControlledServiceError("No se pudo completar la solicitud con la capacidad solicitada. Reintenta mas tarde.")

    monkeypatch.setattr("osint_suite.telegram_bot.call_service", controlled_failure)

    asyncio.run(
        run_command_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="phone",
            raw_arguments=["+34", "600123123"],
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {
            "chat_id": 100,
            "text": "No se pudo completar la solicitud con la capacidad solicitada. Reintenta mas tarde.",
        }
    ]


def test_document_message_downloads_temp_file_and_cleans_it(monkeypatch, tmp_path):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(file_id="doc-1", file_name="report.pdf"),
        ),
    )
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"%PDF-1.4")
    captured = {}

    def fake_file_service(service_name, file_path, original_name, **kwargs):
        captured["service_name"] = service_name
        captured["original_name"] = original_name
        captured["file_path"] = file_path
        captured["exists_during_call"] = os.path.exists(file_path)
        with open(file_path, "rb") as handle:
            captured["payload"] = handle.read()
        return CommandResult(
            summary="Documento analizado",
            payload={"status": "ok"},
            filename_prefix="document_report",
        )

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fake_file_service)

    asyncio.run(run_handler_and_background(document_message, update, context))

    assert update.effective_message.replies == ["Procesando documento..."]
    assert context.bot.messages[-1] == {"chat_id": 100, "text": "Documento analizado"}
    assert captured["service_name"] == "document"
    assert captured["original_name"] == "report.pdf"
    assert captured["exists_during_call"] is True
    assert captured["payload"] == b"%PDF-1.4"
    assert os.path.exists(captured["file_path"]) is False


def test_document_message_rejects_unsupported_extension():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(file_id="doc-1", file_name="payload.exe"),
        ),
    )
    context = FakeContext(config)

    asyncio.run(document_message(update, context))

    assert update.effective_message.replies == [
        "Formato de documento no soportado. Envia PDF u Office/OpenDocument."
    ]
    assert context.bot.messages == []


def test_document_message_rejects_disallowed_extension_from_policy():
    config = TelegramBotConfig(
        bot_token="token",
        allowed_users=set(),
        allowed_document_extensions={".pdf"},
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(file_id="doc-1", file_name="report.docx"),
        ),
    )
    context = FakeContext(config)

    asyncio.run(document_message(update, context))

    assert update.effective_message.replies == [
        "Extension de documento no permitida por la politica actual."
    ]
    assert context.chat_data == {}
    assert get_abuse_signals(context)["upload_policy_denied"] == 1


def test_document_message_rejects_invalid_mime_type_before_background_job():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(
                file_id="doc-1",
                file_name="report.pdf",
                mime_type="application/x-msdownload",
            ),
        ),
    )
    context = FakeContext(config)

    asyncio.run(document_message(update, context))

    assert update.effective_message.replies == [
        "Tipo MIME de documento no soportado para este archivo."
    ]
    assert context.chat_data == {}


def test_document_message_rejects_empty_upload_before_background_job():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(file_id="doc-1", file_name="report.pdf", file_size=0),
        ),
    )
    context = FakeContext(config)

    asyncio.run(document_message(update, context))

    assert update.effective_message.replies == ["Archivo vacio o sin contenido."]
    assert context.chat_data == {}


def test_document_message_rejects_oversized_upload_before_background_job():
    config = TelegramBotConfig(
        bot_token="token",
        allowed_users=set(),
        max_upload_size_bytes=1000,
        max_document_upload_size_bytes=100,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(file_id="doc-1", file_name="report.pdf", file_size=101),
        ),
    )
    context = FakeContext(config)

    asyncio.run(document_message(update, context))

    assert update.effective_message.replies == [
        "Archivo demasiado grande. Limite actual: 100 bytes."
    ]
    assert context.chat_data == {}


def test_document_message_rejects_corrupt_payload_before_service_call(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            document=SimpleNamespace(
                file_id="doc-1",
                file_name="report.pdf",
                mime_type="application/pdf",
                file_size=12,
            ),
        ),
    )
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"not-a-pdf")
    called = {"value": False}

    def fake_file_service(service_name, file_path, original_name):
        called["value"] = True
        return CommandResult(summary="should not run", payload={}, filename_prefix="bad")

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fake_file_service)

    asyncio.run(run_handler_and_background(document_message, update, context))

    assert update.effective_message.replies == ["Procesando documento..."]
    assert context.bot.messages == [
        {"chat_id": 100, "text": "Archivo corrupto o no coincide con el tipo esperado."}
    ]
    assert called["value"] is False


def test_photo_message_downloads_largest_variant(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            photo=[
                SimpleNamespace(file_id="photo-small"),
                SimpleNamespace(file_id="photo-large"),
            ],
        ),
    )
    context = FakeContext(config)
    context.bot.files["photo-large"] = FakeTelegramFile(payload=b"\xff\xd8\xff\xe0jpeg")
    captured = {}

    def fake_file_service(service_name, file_path, original_name, **kwargs):
        captured["service_name"] = service_name
        captured["original_name"] = original_name
        with open(file_path, "rb") as handle:
            captured["payload"] = handle.read()
        return CommandResult(
            summary="Imagen analizada",
            payload={"status": "ok"},
            filename_prefix="image_photo",
        )

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fake_file_service)

    asyncio.run(run_handler_and_background(photo_message, update, context))

    assert update.effective_message.replies == ["Procesando imagen..."]
    assert context.bot.messages[-1] == {"chat_id": 100, "text": "Imagen analizada"}
    assert captured["service_name"] == "image"
    assert captured["original_name"] == "telegram_photo.jpg"
    assert captured["payload"] == b"\xff\xd8\xff\xe0jpeg"


def test_photo_message_rejects_oversized_upload_before_background_job():
    config = TelegramBotConfig(
        bot_token="token",
        allowed_users=set(),
        max_upload_size_bytes=500,
        max_image_upload_size_bytes=50,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            photo=[
                SimpleNamespace(file_id="photo-small", file_size=20),
                SimpleNamespace(file_id="photo-large", file_size=51),
            ],
        ),
    )
    context = FakeContext(config)

    asyncio.run(photo_message(update, context))

    assert update.effective_message.replies == [
        "Archivo demasiado grande. Limite actual: 50 bytes."
    ]
    assert context.chat_data == {}


def test_photo_message_rejects_disallowed_extension_from_policy():
    config = TelegramBotConfig(
        bot_token="token",
        allowed_users=set(),
        allowed_image_extensions={".png"},
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            photo=[SimpleNamespace(file_id="photo-large", file_size=10)],
        ),
    )
    context = FakeContext(config)

    asyncio.run(photo_message(update, context))

    assert update.effective_message.replies == [
        "Extension de imagen no permitida por la politica actual."
    ]
    assert context.chat_data == {}


def test_photo_message_rejects_corrupt_payload_before_service_call(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=FakeMessage(
            chat_id=100,
            photo=[SimpleNamespace(file_id="photo-large", file_size=9)],
        ),
    )
    context = FakeContext(config)
    context.bot.files["photo-large"] = FakeTelegramFile(payload=b"notimage")
    called = {"value": False}

    def fake_file_service(service_name, file_path, original_name):
        called["value"] = True
        return CommandResult(summary="should not run", payload={}, filename_prefix="bad")

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fake_file_service)

    asyncio.run(run_handler_and_background(photo_message, update, context))

    assert update.effective_message.replies == ["Procesando imagen..."]
    assert context.bot.messages == [
        {"chat_id": 100, "text": "Archivo corrupto o no coincide con el tipo esperado."}
    ]
    assert called["value"] is False


def test_run_image_lookup_reports_gps_and_privacy_risk(monkeypatch):
    class FakeExtractor:
        def analyze_image(self, image_path):
            return {
                "file_name": "photo.jpg",
                "format": "JPEG",
                "width": 1200,
                "height": 800,
                "gps_info": {"latitude_decimal": 40.4, "longitude_decimal": -3.7},
                "privacy_analysis": {"risk_count": 2},
            }

    monkeypatch.setattr("osint_suite.telegram_services.ImageMetadataExtractor", FakeExtractor)

    result = run_image_lookup("dummy.jpg", "photo.jpg")

    assert "GPS: si" in result.summary
    assert "Riesgos privacidad: 2" in result.summary
    assert result.filename_prefix == "image_photo"


def test_run_image_lookup_with_real_gps_fixture():
    result = run_image_lookup(str(fixture_path("image_with_gps.jpg")), "image_with_gps.jpg")

    assert "GPS: si" in result.summary
    assert result.payload["gps_info"]["latitude_decimal"] == 40.4
    assert result.payload["gps_info"]["longitude_decimal"] == -3.7


def test_run_image_lookup_reports_no_exif_or_gps(monkeypatch):
    class FakeExtractor:
        def analyze_image(self, image_path):
            return {
                "file_name": "plain.jpg",
                "format": "JPEG",
                "width": 640,
                "height": 480,
                "gps_info": None,
                "privacy_analysis": {"risk_count": 0},
            }

    monkeypatch.setattr("osint_suite.telegram_services.ImageMetadataExtractor", FakeExtractor)

    result = run_image_lookup("dummy.jpg", "plain.jpg")

    assert "GPS: no" in result.summary
    assert "Riesgos privacidad: 0" in result.summary


def test_run_image_lookup_with_real_no_exif_fixture():
    result = run_image_lookup(str(fixture_path("image_no_exif.jpg")), "image_no_exif.jpg")

    assert "GPS: no" in result.summary
    assert result.payload["gps_info"] is None


def test_run_document_lookup_reports_partial_non_fatal_error(monkeypatch):
    class FakeAnalyzer:
        supported_formats = {".pdf": "PDF"}

        def analyze_document(self, file_path):
            return {
                "file_name": "report.pdf",
                "file_type": "PDF",
                "file_stats": {"size_bytes": 2048, "modified": "2026-04-01T10:00:00"},
                "error": "Metadatos XMP no disponibles",
            }

    monkeypatch.setattr("osint_suite.telegram_services.DocumentAnalyzer", FakeAnalyzer)

    result = run_document_lookup("dummy.pdf", "report.pdf")

    assert "Tipo: PDF" in result.summary
    assert "Error: Metadatos XMP no disponibles" in result.summary
    assert result.filename_prefix == "document_report"


def test_run_document_lookup_with_real_minimal_pdf_fixture():
    result = run_document_lookup(str(fixture_path("document_minimal.pdf")), "document_minimal.pdf")

    assert "Tipo: PDF" in result.summary
    assert result.payload["file_name"] == "document_minimal.pdf"
    assert "error" in result.payload


def test_run_document_lookup_with_real_corrupt_pdf_fixture():
    result = run_document_lookup(str(fixture_path("document_corrupt.pdf")), "document_corrupt.pdf")

    assert "Tipo: PDF" in result.summary
    assert "Error:" in result.summary


def test_document_analyzer_keeps_pdf_result_when_preview_extraction_fails(monkeypatch, tmp_path):
    class FakePage:
        def extract_text(self):
            raise ValueError("preview unavailable")

    class FakeReader:
        def __init__(self, file_path):
            self.metadata = None
            self.pages = [FakePage()]
            self.is_encrypted = False

        def get_fields(self):
            return None

    fake_module = SimpleNamespace(PdfReader=FakeReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_module)

    pdf_path = tmp_path / "preview_failure.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n")

    result = DocumentAnalyzer().analyze_pdf(str(pdf_path))

    assert result["error"] is None
    assert result["structure_info"]["num_pages"] == 1
    assert "first_page_preview" not in result["structure_info"]


def test_send_command_result_attaches_json_for_large_file_analysis_payload():
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=40)
    context = FakeContext(config)
    result = CommandResult(
        summary="Analisis de imagen\n- GPS: si",
        payload={"metadata": "x" * 200, "kind": "image"},
        filename_prefix="image_photo",
    )

    asyncio.run(send_command_result(context, 100, result))

    assert context.bot.messages == [{"chat_id": 100, "text": "Analisis de imagen\n- GPS: si"}]
    assert len(context.bot.documents) == 1
    assert context.bot.documents[0]["document"].filename == "image_photo.json"


def test_run_file_job_sends_same_long_job_notice_before_result(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"%PDF-1.4")

    def successful_file_service(service_name, file_path, original_name, **kwargs):
        return CommandResult(summary="Resumen largo", payload={}, filename_prefix="ok")

    perf_counter_values = iter([20.0, 25.5])

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", successful_file_service)
    monkeypatch.setattr("osint_suite.telegram_bot.time.perf_counter", lambda: next(perf_counter_values))

    asyncio.run(
        run_file_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="document",
            file_id="doc-1",
            original_name="report.pdf",
            long_job_threshold_seconds=5,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "La solicitud tardo mas de lo habitual. Resultado listo."},
        {"chat_id": 100, "text": "Resumen largo"},
    ]


def test_run_file_job_replies_when_analysis_times_out(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), analysis_timeout_seconds=0.01)
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"%PDF-1.4")

    def slow_file_service(service_name, file_path, original_name):
        time.sleep(0.05)
        return CommandResult(summary="late", payload={}, filename_prefix="late")

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", slow_file_service)

    asyncio.run(
        run_file_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="document",
            file_id="doc-1",
            original_name="report.pdf",
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "La solicitud excedio el tiempo maximo de analisis."}
    ]


def test_run_file_job_replies_with_validation_error_and_releases_slot(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"%PDF-1.4")
    limiter = context.application.bot_data["rate_limiter"]
    assert limiter.try_acquire_job_slot(user_id=42) is True

    def fail_file_service(service_name, file_path, original_name, **kwargs):
        raise ValueError("Archivo invalido")

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fail_file_service)

    asyncio.run(
        run_file_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="document",
            file_id="doc-1",
            original_name="report.pdf",
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [{"chat_id": 100, "text": "Archivo invalido"}]
    assert get_abuse_signals(context)["file_validation_denied"] == 1
    assert limiter.try_acquire_job_slot(user_id=42) is True


@pytest.mark.parametrize(
    ("service_name", "file_name", "file_size", "mime_type", "payload", "expected_message"),
    [
        (
            "document",
            "payload.exe",
            10,
            "application/octet-stream",
            b"MZ...",
            "Formato de documento no soportado. Envia PDF u Office/OpenDocument.",
        ),
        (
            "document",
            "report.pdf",
            0,
            "application/pdf",
            b"",
            "Archivo vacio o sin contenido.",
        ),
        (
            "document",
            "report.pdf",
            101,
            "application/pdf",
            b"%PDF-1.4",
            "Archivo demasiado grande. Limite actual: 100 bytes.",
        ),
        (
            "document",
            "report.pdf",
            12,
            "application/pdf",
            b"not-a-pdf",
            "Archivo corrupto o no coincide con el tipo esperado.",
        ),
        (
            "image",
            "telegram_photo.jpg",
            9,
            "image/jpeg",
            b"notimage",
            "Archivo corrupto o no coincide con el tipo esperado.",
        ),
    ],
)
def test_dispatch_file_service_normalizes_upload_validation_failures(
    tmp_path,
    service_name,
    file_name,
    file_size,
    mime_type,
    payload,
    expected_message,
):
    file_path = tmp_path / file_name
    file_path.write_bytes(payload)

    with pytest.raises(FileServiceError, match=expected_message):
        dispatch_file_service(
            service_name,
            str(file_path),
            file_name,
            file_size=file_size,
            max_upload_size_bytes=100,
            mime_type=mime_type,
        )


def test_run_file_job_replies_with_controlled_service_error_and_releases_slot(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"%PDF-1.4")
    limiter = context.application.bot_data["rate_limiter"]
    assert limiter.try_acquire_job_slot(user_id=42) is True

    def fail_file_service(service_name, file_path, original_name, **kwargs):
        raise ControlledServiceError("No se pudo completar la solicitud con la capacidad solicitada. Reintenta mas tarde.")

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fail_file_service)

    asyncio.run(
        run_file_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="document",
            file_id="doc-1",
            original_name="report.pdf",
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {
            "chat_id": 100,
            "text": "No se pudo completar la solicitud con la capacidad solicitada. Reintenta mas tarde.",
        }
    ]
    assert limiter.try_acquire_job_slot(user_id=42) is True


def test_run_file_job_returns_sanitized_internal_error_and_releases_slot(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    context = FakeContext(config)
    context.bot.files["doc-1"] = FakeTelegramFile(payload=b"%PDF-1.4")
    limiter = context.application.bot_data["rate_limiter"]
    assert limiter.try_acquire_job_slot(user_id=42) is True

    def fail_file_service(service_name, file_path, original_name):
        raise RuntimeError("sensitive file backend trace")

    monkeypatch.setattr("osint_suite.telegram_bot.call_file_service", fail_file_service)

    asyncio.run(
        run_file_job(
            context,
            chat_id=100,
            user_id=42,
            service_name="document",
            file_id="doc-1",
            original_name="report.pdf",
            long_job_threshold_seconds=1,
        )
    )

    assert context.bot.messages == [
        {"chat_id": 100, "text": "Se produjo un error interno al procesar la solicitud."}
    ]
    assert limiter.try_acquire_job_slot(user_id=42) is True


# ------------------------------------------------------------------
# Phase D: Advanced userbot commands
# ------------------------------------------------------------------

def test_create_application_registers_advanced_userbot_commands():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    app = telegram_bot_module.create_application(config)
    registered_commands = {
        next(iter(handler.commands))
        for group in app.handlers.values()
        for handler in group
        if hasattr(handler, "commands")
    }
    assert "tgresolve" in registered_commands
    assert "tgallchats" in registered_commands
    assert "tghealth" in registered_commands


def test_help_text_includes_advanced_commands():
    assert "/tgresolve" in HELP_TEXT
    assert "/tgallchats" in HELP_TEXT
    assert "/tghealth" in HELP_TEXT


def test_tgresolve_command_requires_argument_when_pool_exists():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])
    context.application.bot_data["tg_osint_pool"] = object()
    asyncio.run(tgresolve_command(update, context))
    assert update.effective_message.replies == ["Uso: /tgresolve <username>"]


def test_tgresolve_command_replies_when_userbot_is_not_configured():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["someuser"])
    asyncio.run(tgresolve_command(update, context))
    assert update.effective_message.replies == [
        "Userbot no configurado. Añade TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH y TELEGRAM_USERBOT_SESSION_1 al entorno."
    ]


def test_tgresolve_command_returns_summary_and_json(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=10)
    update = make_update()
    context = FakeContext(config, args=["elonmusk"])

    class FakePool:
        async def resolve_username(self, username):
            assert username == "elonmusk"
            return {
                "id": 123,
                "first_name": "Elon",
                "last_name": "Musk",
                "username": "elonmusk",
                "phone": None,
                "bio": "CEO",
                "verified": True,
                "bot": False,
                "restricted": False,
                "scam": False,
                "fake": False,
                "deleted": False,
                "entity_type": "user",
                "payload_padding": "x" * 100,
            }

    context.application.bot_data["tg_osint_pool"] = FakePool()
    asyncio.run(tgresolve_command(update, context))
    assert update.effective_message.replies == ["Consultando via userbot..."]
    assert len(context.bot.messages) == 1
    assert "Resolucion Telegram @elonmusk" in context.bot.messages[0]["text"]


def test_tgresolve_command_surfaces_validation_error_from_pool(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["nonexistent_user_xyz"])

    class FakePool:
        async def resolve_username(self, username):
            raise ValueError("Username no encontrado en Telegram.")

    context.application.bot_data["tg_osint_pool"] = FakePool()
    asyncio.run(tgresolve_command(update, context))
    assert update.effective_message.replies == [
        "Consultando via userbot...",
        "Username no encontrado en Telegram.",
    ]


def test_tgresolve_command_surfaces_controlled_failure(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=["flooded_user"])

    class FakePool:
        async def resolve_username(self, username):
            raise ControlledServiceError("Userbot en espera por flood limit. Reintenta en unos minutos.")

    context.application.bot_data["tg_osint_pool"] = FakePool()
    asyncio.run(tgresolve_command(update, context))
    assert any("flood limit" in r for r in update.effective_message.replies)


def test_tgallchats_command_replies_when_userbot_is_not_configured():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])
    asyncio.run(tgallchats_command(update, context))
    assert update.effective_message.replies == [
        "Userbot no configurado. Añade TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH y TELEGRAM_USERBOT_SESSION_1 al entorno."
    ]


def test_tgallchats_command_returns_summary_and_json(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=10)
    update = make_update()
    context = FakeContext(config, args=[])

    class FakePool:
        async def get_all_chats(self):
            return {
                "total_chats": 15,
                "groups": 8,
                "channels": 7,
                "users": 0,
                "chats": [
                    {"id": 1, "title": "Group A", "type": "grupo"},
                    {"id": 2, "title": "Channel B", "type": "canal"},
                ],
                "payload_padding": "x" * 100,
            }

    context.application.bot_data["tg_osint_pool"] = FakePool()
    asyncio.run(tgallchats_command(update, context))
    assert update.effective_message.replies == ["Consultando via userbot..."]
    assert len(context.bot.messages) == 1
    assert "Chats accesibles de la cuenta userbot" in context.bot.messages[0]["text"]
    assert "Total: 15" in context.bot.messages[0]["text"]


def test_tghealth_command_replies_when_userbot_is_not_configured():
    config = TelegramBotConfig(bot_token="token", allowed_users=set())
    update = make_update()
    context = FakeContext(config, args=[])
    asyncio.run(tghealth_command(update, context))
    assert update.effective_message.replies == [
        "Userbot no configurado. Añade TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH y TELEGRAM_USERBOT_SESSION_1 al entorno."
    ]


def test_tghealth_command_returns_summary_and_json(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=10)
    update = make_update()
    context = FakeContext(config, args=[])

    class FakePool:
        async def check_account_health(self):
            return {
                "account_label": "account_1",
                "user_id": 987654,
                "username": "testuser",
                "first_name": "Test",
                "phone": "+1234567890",
                "authorized": True,
                "restrictions": [],
                "warnings": [],
                "active_sessions": [
                    {"app_name": "Telegram Desktop", "current": True, "official": True},
                ],
                "account_ttl_days": 365,
                "payload_padding": "x" * 100,
            }

    context.application.bot_data["tg_osint_pool"] = FakePool()
    asyncio.run(tghealth_command(update, context))
    assert update.effective_message.replies == ["Consultando via userbot..."]
    assert len(context.bot.messages) == 1
    assert "Salud cuenta userbot: account_1" in context.bot.messages[0]["text"]
    assert "Autorizada: si" in context.bot.messages[0]["text"]


def test_tghealth_command_surfaces_warnings(monkeypatch):
    config = TelegramBotConfig(bot_token="token", allowed_users=set(), result_file_threshold_bytes=10)
    update = make_update()
    context = FakeContext(config, args=[])

    class FakePool:
        async def check_account_health(self):
            return {
                "account_label": "suspicious_account",
                "user_id": 111,
                "username": None,
                "first_name": "Suspicious",
                "phone": None,
                "authorized": True,
                "restrictions": ["Account is restricted by Telegram"],
                "warnings": ["2 non-official session(s) detected"],
                "active_sessions": [
                    {"app_name": "Unknown App", "current": False, "official": False},
                ],
                "account_ttl_days": 10,
                "payload_padding": "x" * 100,
            }

    context.application.bot_data["tg_osint_pool"] = FakePool()
    asyncio.run(tghealth_command(update, context))
    assert update.effective_message.replies == ["Consultando via userbot..."]
    assert len(context.bot.messages) == 1
    msg_text = context.bot.messages[0]["text"]
    assert "Restricciones: 1" in msg_text
    assert "Advertencias: 1" in msg_text
    assert "TTL cuenta: 10 dias" in msg_text
