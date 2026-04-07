"""
Telegram OSINT via MTProto userbot pool.

Anti-ban design
---------------
- Two Telethon sessions (Eustacio + Sócrates) with round-robin + automatic failover.
- FloodWaitError: wait exactly the indicated seconds + 5 s jitter, then rotate session.
- Rate limit per session: max 3 req/min, 20 req/hour (token bucket).
- Pre-request random delay: 1.0–4.0 s (uniform, not fixed — avoids pattern detection).
- Entity cache: 10 min TTL — avoids re-resolving the same username in the same session.
- Result cache: 5 min TTL — deduplicates repeated bot requests for the same target.
- Exclusive asyncio.Lock per session — no concurrent MTProto calls on the same session.
- Read-only: get_entity only. No send_message, no join_channel, no write operations.
- Graceful degradation: raises ControlledServiceError when all sessions unavailable.
- Session files and credentials loaded from environment — never hardcoded.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from telethon import TelegramClient
    from telethon.errors import (
        ChannelPrivateError,
        FloodWaitError,
        UserDeactivatedError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
    )
    from telethon.tl.types import Channel, Chat, User

    _TELETHON_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TELETHON_AVAILABLE = False


# Anti-ban tuning constants
_RATE_LIMIT_PER_MINUTE = 3
_RATE_LIMIT_PER_HOUR = 20
_MIN_DELAY_SECONDS = 1.0
_MAX_DELAY_SECONDS = 4.0
_FLOOD_EXTRA_BUFFER_SECONDS = 5
_ENTITY_CACHE_TTL_SECONDS = 600   # 10 min
_RESULT_CACHE_TTL_SECONDS = 300   # 5 min


class _SessionState:
    """Mutable per-session state. Lock is created lazily inside the event loop."""

    def __init__(self, session_path: str) -> None:
        self.session_path = session_path
        self.client: Any = None
        self._lock: Optional[asyncio.Lock] = None
        self._flood_wait_until: float = 0.0
        self._minute_bucket: List[float] = []
        self._hour_bucket: List[float] = []
        self._entity_cache: Dict[str, Tuple[Any, float]] = {}

    @property
    def lock(self) -> asyncio.Lock:
        # Lazily created so it belongs to the running event loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def is_in_flood_wait(self, now: float) -> bool:
        return now < self._flood_wait_until

    def set_flood_wait(self, seconds: int, now: float) -> None:
        wait = seconds + _FLOOD_EXTRA_BUFFER_SECONDS
        self._flood_wait_until = now + wait
        logger.warning(
            "Userbot flood wait activated",
            extra={"session": self.session_path, "wait_seconds": wait},
        )

    def can_make_request(self, now: float) -> bool:
        if self.is_in_flood_wait(now):
            return False
        self._minute_bucket = [t for t in self._minute_bucket if now - t < 60]
        self._hour_bucket = [t for t in self._hour_bucket if now - t < 3600]
        return (
            len(self._minute_bucket) < _RATE_LIMIT_PER_MINUTE
            and len(self._hour_bucket) < _RATE_LIMIT_PER_HOUR
        )

    def record_request(self, now: float) -> None:
        self._minute_bucket.append(now)
        self._hour_bucket.append(now)

    def get_cached_entity(self, username: str, now: float) -> Any:
        entry = self._entity_cache.get(username.lower())
        if entry and now - entry[1] < _ENTITY_CACHE_TTL_SECONDS:
            return entry[0]
        return None

    def cache_entity(self, username: str, entity: Any, now: float) -> None:
        self._entity_cache[username.lower()] = (entity, now)


class TelegramOSINTPool:
    """
    Pool of Telethon userbot sessions with anti-ban protection.

    Usage
    -----
    pool = TelegramOSINTPool(api_id, api_hash, [session1_path, session2_path])
    await pool.start()
    info = await pool.lookup_user("someusername")
    await pool.stop()
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_paths: List[str],
    ) -> None:
        if not _TELETHON_AVAILABLE:
            raise RuntimeError(
                "telethon is not installed. Run: pip install 'telethon>=1.28'"
            )
        self._api_id = api_id
        self._api_hash = api_hash
        self._sessions: List[_SessionState] = [
            _SessionState(session_path=p) for p in session_paths
        ]
        self._result_cache: Dict[str, Tuple[Any, float]] = {}
        self._round_robin_index = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect all sessions. Called once on bot startup."""
        for state in self._sessions:
            client = TelegramClient(
                state.session_path,
                self._api_id,
                self._api_hash,
            )
            await client.connect()
            state.client = client
            authorized = await client.is_user_authorized()
            if authorized:
                logger.info(
                    "Userbot session connected",
                    extra={"session": state.session_path, "authorized": True},
                )
            else:
                logger.error(
                    "Userbot session NOT authorized — session file may be invalid",
                    extra={"session": state.session_path},
                )

    async def stop(self) -> None:
        """Disconnect all sessions cleanly. Called on bot shutdown."""
        for state in self._sessions:
            if state.client:
                try:
                    await state.client.disconnect()
                    logger.info(
                        "Userbot session disconnected",
                        extra={"session": state.session_path},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Error disconnecting userbot session",
                        extra={"session": state.session_path, "error": str(exc)},
                    )

    # ------------------------------------------------------------------
    # Public lookup API
    # ------------------------------------------------------------------

    async def lookup_user(self, username: str) -> Dict[str, Any]:
        """
        Look up a Telegram user by username.

        Returns a dict with: id, first_name, last_name, username, phone,
        bio, verified, bot, restricted, scam, fake, deleted.

        Raises
        ------
        ValueError  — username not found, invalid, or entity is a channel.
        ControlledServiceError — all sessions unavailable (flood wait / rate limit).
        """
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("Username de Telegram invalido.")

        cache_key = f"user:{username.lower()}"
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            logger.info("Telegram user lookup (cache hit)", extra={"username": username})
            return cached

        entity = await self._resolve_entity(username)

        if _TELETHON_AVAILABLE and isinstance(entity, (Channel, Chat)):
            raise ValueError(
                "Ese username corresponde a un grupo o canal. Usa /tggroup."
            )
        if _TELETHON_AVAILABLE and not isinstance(entity, User):
            raise ValueError("Entidad no reconocida para este username.")

        result = _extract_user_info(entity)
        self._cache_result(cache_key, result)
        logger.info(
            "Telegram user lookup completed",
            extra={"username": username, "outcome": "success"},
        )
        return result

    async def lookup_channel(self, username: str) -> Dict[str, Any]:
        """
        Look up a Telegram channel or group by username.

        Returns a dict with: id, title, username, description,
        participants_count, verified, restricted, scam, fake,
        megagroup, broadcast, date.

        Raises
        ------
        ValueError  — not found, private, or entity is a user.
        ControlledServiceError — all sessions unavailable.
        """
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("Username de Telegram invalido.")

        cache_key = f"channel:{username.lower()}"
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            logger.info(
                "Telegram channel lookup (cache hit)", extra={"username": username}
            )
            return cached

        entity = await self._resolve_entity(username, expect_channel=True)

        if _TELETHON_AVAILABLE and isinstance(entity, User):
            raise ValueError(
                "Ese username corresponde a un usuario. Usa /tg."
            )
        if _TELETHON_AVAILABLE and not isinstance(entity, (Channel, Chat)):
            raise ValueError("Entidad no reconocida para este username.")

        result = _extract_channel_info(entity)
        self._cache_result(cache_key, result)
        logger.info(
            "Telegram channel lookup completed",
            extra={"username": username, "outcome": "success"},
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_cached_result(self, key: str) -> Any:
        entry = self._result_cache.get(key)
        if entry and time.monotonic() - entry[1] < _RESULT_CACHE_TTL_SECONDS:
            return entry[0]
        return None

    def _cache_result(self, key: str, value: Any) -> None:
        self._result_cache[key] = (value, time.monotonic())

    def _pick_session(self) -> Optional[_SessionState]:
        """Round-robin session selection, skipping unavailable ones."""
        now = time.monotonic()
        n = len(self._sessions)
        for i in range(n):
            idx = (self._round_robin_index + i) % n
            state = self._sessions[idx]
            if state.client and state.can_make_request(now):
                self._round_robin_index = (idx + 1) % n
                return state
        return None

    def _pick_fallback_session(self, exclude: _SessionState) -> Optional[_SessionState]:
        """Pick any available session that is not the excluded one."""
        now = time.monotonic()
        for state in self._sessions:
            if state is not exclude and state.client and state.can_make_request(now):
                return state
        return None

    async def _resolve_entity(
        self, username: str, expect_channel: bool = False
    ) -> Any:
        """
        Resolve a Telegram entity with anti-ban protection.

        1. Pre-request random delay to avoid pattern detection.
        2. Acquire exclusive lock for the chosen session.
        3. On FloodWaitError: wait + rotate to fallback session.
        4. Cache resolved entity in the session state.
        """
        state = self._pick_session()
        if state is None:
            raise _all_sessions_unavailable()

        async with state.lock:
            now = time.monotonic()

            # Check entity cache before making the network call.
            cached_entity = state.get_cached_entity(username, now)
            if cached_entity is not None:
                return cached_entity

            # Random delay — key anti-ban measure.
            await asyncio.sleep(random.uniform(_MIN_DELAY_SECONDS, _MAX_DELAY_SECONDS))

            state.record_request(time.monotonic())
            try:
                entity = await state.client.get_entity(username)
                state.cache_entity(username, entity, time.monotonic())
                return entity

            except FloodWaitError as exc:
                state.set_flood_wait(exc.seconds, time.monotonic())
                logger.warning(
                    "FloodWaitError — rotating to fallback session",
                    extra={"username": username, "wait_seconds": exc.seconds},
                )
                # Fall through to fallback session below.

            except (UsernameInvalidError, UsernameNotOccupiedError):
                if expect_channel:
                    raise ValueError(
                        "Grupo o canal no encontrado o username invalido."
                    )
                raise ValueError(
                    "Usuario de Telegram no encontrado o username invalido."
                )

            except ChannelPrivateError:
                raise ValueError("Este canal o grupo es privado y no es accesible.")

            except UserDeactivatedError:
                raise ValueError("Esta cuenta de Telegram ha sido eliminada.")

        # Fallback: try the other session after flood wait on the first.
        fallback = self._pick_fallback_session(exclude=state)
        if fallback is None:
            raise _all_sessions_unavailable()

        async with fallback.lock:
            cached_entity = fallback.get_cached_entity(username, time.monotonic())
            if cached_entity is not None:
                return cached_entity

            await asyncio.sleep(random.uniform(_MIN_DELAY_SECONDS, _MAX_DELAY_SECONDS))
            fallback.record_request(time.monotonic())
            try:
                entity = await fallback.client.get_entity(username)
                fallback.cache_entity(username, entity, time.monotonic())
                return entity

            except FloodWaitError as exc:
                fallback.set_flood_wait(exc.seconds, time.monotonic())
                raise _all_sessions_unavailable()

            except (UsernameInvalidError, UsernameNotOccupiedError):
                if expect_channel:
                    raise ValueError(
                        "Grupo o canal no encontrado o username invalido."
                    )
                raise ValueError(
                    "Usuario de Telegram no encontrado o username invalido."
                )

            except ChannelPrivateError:
                raise ValueError("Este canal o grupo es privado y no es accesible.")

            except UserDeactivatedError:
                raise ValueError("Esta cuenta de Telegram ha sido eliminada.")


# ------------------------------------------------------------------
# Entity data extractors
# ------------------------------------------------------------------

def _extract_user_info(user: Any) -> Dict[str, Any]:
    return {
        "id": user.id,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "username": user.username or "",
        "phone": user.phone or None,
        "bio": getattr(user, "about", None),
        "verified": bool(getattr(user, "verified", False)),
        "bot": bool(getattr(user, "bot", False)),
        "restricted": bool(getattr(user, "restricted", False)),
        "scam": bool(getattr(user, "scam", False)),
        "fake": bool(getattr(user, "fake", False)),
        "deleted": bool(getattr(user, "deleted", False)),
    }


def _extract_channel_info(channel: Any) -> Dict[str, Any]:
    return {
        "id": channel.id,
        "title": getattr(channel, "title", ""),
        "username": getattr(channel, "username", "") or "",
        "description": getattr(channel, "about", None),
        "participants_count": getattr(channel, "participants_count", None),
        "verified": bool(getattr(channel, "verified", False)),
        "restricted": bool(getattr(channel, "restricted", False)),
        "scam": bool(getattr(channel, "scam", False)),
        "fake": bool(getattr(channel, "fake", False)),
        "megagroup": bool(getattr(channel, "megagroup", False)),
        "broadcast": bool(getattr(channel, "broadcast", False)),
        "date": str(getattr(channel, "date", None)),
    }


def _all_sessions_unavailable() -> Exception:
    from .telegram_services import ControlledServiceError  # avoid circular import

    return ControlledServiceError(
        "Userbot en espera por flood limit. Reintenta en unos minutos."
    )


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def pool_from_env() -> Optional[TelegramOSINTPool]:
    """
    Build a TelegramOSINTPool from environment variables.

    Required env vars:
        TELEGRAM_APP_API_ID
        TELEGRAM_APP_API_HASH

    Optional (at least one must be set for the pool to be useful):
        TELEGRAM_USERBOT_SESSION_1  — absolute path to .session file
        TELEGRAM_USERBOT_SESSION_2  — absolute path to .session file

    Returns None if not configured (bot continues without userbot features).
    """
    if not _TELETHON_AVAILABLE:
        logger.info("telethon not installed — userbot pool disabled")
        return None

    api_id_str = os.environ.get("TELEGRAM_APP_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_APP_API_HASH", "").strip()

    if not api_id_str or not api_hash:
        logger.info("Userbot credentials not configured — pool disabled")
        return None

    try:
        api_id = int(api_id_str)
    except ValueError:
        logger.warning("TELEGRAM_APP_API_ID is not a valid integer — pool disabled")
        return None

    session_paths: List[str] = []
    for i in (1, 2):
        path = os.environ.get(f"TELEGRAM_USERBOT_SESSION_{i}", "").strip()
        if not path:
            continue
        if os.path.exists(path):
            session_paths.append(path)
            logger.info("Userbot session found", extra={"index": i, "path": path})
        else:
            logger.warning(
                "Userbot session file not found — skipping",
                extra={"index": i, "path": path},
            )

    if not session_paths:
        logger.info("No valid userbot session files found — pool disabled")
        return None

    logger.info(
        "TelegramOSINTPool created",
        extra={"session_count": len(session_paths)},
    )
    return TelegramOSINTPool(api_id=api_id, api_hash=api_hash, session_paths=session_paths)
