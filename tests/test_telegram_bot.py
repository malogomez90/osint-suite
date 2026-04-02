import os
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


from osint_suite.telegram_bot import (
    HELP_TEXT,
    TelegramBotConfig,
    InMemoryRateLimiter,
    call_service,
    call_file_service,
    start_command,
    help_command,
    username_command,
    document_message,
    photo_message,
    send_command_result,
    run_command_job,
    run_file_job,
)
from osint_suite.telegram_services import run_username_lookup
from osint_suite.telegram_services import (
    CommandResult,
    format_summary,
    run_document_lookup,
    run_image_lookup,
)


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

    assert update.effective_message.replies == ["Uso: /username <valor>"]


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

    def fake_file_service(service_name, file_path, original_name):
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
    assert context.bot.messages == [{"chat_id": 100, "text": "Documento analizado"}]
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

    def fake_file_service(service_name, file_path, original_name):
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
    assert context.bot.messages == [{"chat_id": 100, "text": "Imagen analizada"}]
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
