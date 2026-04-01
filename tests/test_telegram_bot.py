import os

import pytest


from osint_suite.telegram_bot import TelegramBotConfig, InMemoryRateLimiter
from osint_suite.telegram_services import run_username_lookup


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
