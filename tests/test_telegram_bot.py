import os
import asyncio
from types import SimpleNamespace

import pytest


from osint_suite.telegram_bot import (
    HELP_TEXT,
    TelegramBotConfig,
    InMemoryRateLimiter,
    call_service,
    start_command,
    help_command,
    username_command,
    send_command_result,
    run_command_job,
)
from osint_suite.telegram_services import run_username_lookup
from osint_suite.telegram_services import CommandResult


class FakeMessage:
    def __init__(self, chat_id=100):
        self.chat_id = chat_id
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class FakeBot:
    def __init__(self):
        self.messages = []
        self.documents = []
        self.actions = []

    async def send_message(self, chat_id, text):
        self.messages.append({"chat_id": chat_id, "text": text})

    async def send_document(self, chat_id, document, caption=None):
        self.documents.append({"chat_id": chat_id, "document": document, "caption": caption})

    async def send_chat_action(self, chat_id, action):
        self.actions.append({"chat_id": chat_id, "action": action})


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


def make_update(user_id=42, chat_id=100):
    message = FakeMessage(chat_id=chat_id)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
    )


def test_telegram_config_reads_token_and_limits_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.setenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("TELEGRAM_RATE_LIMIT_PER_HOUR", "33")
    monkeypatch.setenv("TELEGRAM_LONG_JOB_THRESHOLD_SECONDS", "9")

    config = TelegramBotConfig.from_env()

    assert config.bot_token == "token-123"
    assert config.rate_limit_per_minute == 7
    assert config.rate_limit_per_hour == 33
    assert config.long_job_threshold_seconds == 9


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
        filename_prefix="username_john",
    )

    asyncio.run(send_command_result(context, 100, result))

    assert context.bot.messages == [{"chat_id": 100, "text": "Resumen corto"}]
    assert len(context.bot.documents) == 1
    assert context.bot.documents[0]["caption"] == "Resultado completo en JSON."


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
