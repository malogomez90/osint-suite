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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from telethon import TelegramClient
    from telethon import functions
    from telethon.errors import (
        ChannelPrivateError,
        FloodWaitError,
        UserDeactivatedError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
        AuthKeyUnregisteredError,
        SessionPasswordNeededError,
    )
    from telethon.tl.types import Channel, Chat, User, PeerUser, PeerChannel, PeerChat

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

    def __init__(
        self,
        session_path: str,
        proxy: dict | None = None,
        account_label: str = "",
    ) -> None:
        self.session_path = session_path
        self.proxy = proxy
        self.account_label = account_label or session_path
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

    Supports MTProto/SOCKS5 proxies and multi-account rotation.

    Usage
    -----
    pool = TelegramOSINTPool(api_id, api_hash, [
        {"session_path": "/path/to/session1", "proxy": {"proxy_type": "socks5", "addr": "1.2.3.4", "port": 1080}},
        {"session_path": "/path/to/session2", "proxy": {"proxy_type": "mtproto", "addr": "5.6.7.8", "port": 80, "secret": "xxx"}},
    ])
    await pool.start()
    info = await pool.lookup_user("someusername")
    await pool.stop()
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_paths: List[str] | List[Dict[str, Any]],
    ) -> None:
        if not _TELETHON_AVAILABLE:
            raise RuntimeError(
                "telethon is not installed. Run: pip install 'telethon>=1.28'"
            )
        self._api_id = api_id
        self._api_hash = api_hash

        # Support both simple string paths and dict configs with proxy
        self._sessions: List[_SessionState] = []
        for item in session_paths:
            if isinstance(item, dict):
                path = item.get("session_path", "")
                proxy = item.get("proxy")
                label = item.get("account_label", path)
            else:
                path = item
                proxy = None
                label = path
            if path:
                self._sessions.append(_SessionState(
                    session_path=path,
                    proxy=proxy,
                    account_label=label,
                ))
        self._result_cache: Dict[str, Tuple[Any, float]] = {}
        self._round_robin_index = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect all sessions. Called once on bot startup."""
        for state in self._sessions:
            client_kwargs = {
                "session": state.session_path,
                "api_id": self._api_id,
                "api_hash": self._api_hash,
            }
            if state.proxy:
                client_kwargs["proxy"] = state.proxy

            client = TelegramClient(**client_kwargs)
            await client.connect()
            state.client = client
            authorized = await client.is_user_authorized()
            if authorized:
                logger.info(
                    "Userbot session connected",
                    extra={
                        "session": state.account_label,
                        "authorized": True,
                        "proxy": bool(state.proxy),
                    },
                )
            else:
                logger.error(
                    "Userbot session NOT authorized — session file may be invalid",
                    extra={"session": state.account_label},
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

    async def lookup_user_info(self, username: str) -> Dict[str, Any]:
        """
        Extended public recon for a Telegram user.

        Keeps the lightweight lookup contract intact while adding extra public
        metadata when MTProto exposes it safely in read-only mode.
        """
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("Username de Telegram invalido.")

        cache_key = f"user_info:{username.lower()}"
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            logger.info("Telegram user recon (cache hit)", extra={"username": username})
            return cached

        entity = await self._resolve_entity(username)

        if _TELETHON_AVAILABLE and isinstance(entity, (Channel, Chat)):
            raise ValueError(
                "Ese username corresponde a un grupo o canal. Usa /tggroupinfo."
            )
        if _TELETHON_AVAILABLE and not isinstance(entity, User):
            raise ValueError("Entidad no reconocida para este username.")

        full_response = await self._fetch_full_user(entity, username)
        full_user = getattr(full_response, "full_user", None) if full_response is not None else None
        result = _extract_user_info(entity)
        result.update(_extract_user_recon_info(entity, full_user))
        self._cache_result(cache_key, result)
        logger.info(
            "Telegram user recon completed",
            extra={"username": username, "outcome": "success"},
        )
        return result

    async def lookup_channel_info(self, username: str) -> Dict[str, Any]:
        """
        Extended public recon for a Telegram channel or group.

        Adds public entity signals without reading messages or members.
        """
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("Username de Telegram invalido.")

        cache_key = f"channel_info:{username.lower()}"
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            logger.info("Telegram channel recon (cache hit)", extra={"username": username})
            return cached

        entity = await self._resolve_entity(username, expect_channel=True)

        if _TELETHON_AVAILABLE and isinstance(entity, User):
            raise ValueError(
                "Ese username corresponde a un usuario. Usa /tginfo."
            )
        if _TELETHON_AVAILABLE and not isinstance(entity, (Channel, Chat)):
            raise ValueError("Entidad no reconocida para este username.")

        full_response = await self._fetch_full_channel(entity, username)
        full_chat = getattr(full_response, "full_chat", None) if full_response is not None else None
        result = _extract_channel_info(entity)
        result.update(_extract_channel_recon_info(entity, full_chat))
        self._cache_result(cache_key, result)
        logger.info(
            "Telegram channel recon completed",
            extra={"username": username, "outcome": "success"},
        )
        return result

    async def resolve_username(self, username: str) -> Dict[str, Any]:
        """
        Resolve any Telegram username without being in the same group.

        Uses ResolveUsernameRequest which works even if you don't share
        groups with the target. Returns user or channel info.
        """
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("Username de Telegram invalido.")

        cache_key = f"resolve:{username.lower()}"
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            logger.info("Username resolve (cache hit)", extra={"username": username})
            return cached

        result = await self._run_read_query(
            target=username,
            invalid_message="Username no encontrado en Telegram.",
            query=lambda client: client(
                functions.contacts.ResolveUsernameRequest(username)
            ),
        )

        if isinstance(result, User):
            data = _extract_user_info(result)
            data["entity_type"] = "user"
        elif isinstance(result, (Channel, Chat)):
            data = _extract_channel_info(result)
            data["entity_type"] = "channel" if isinstance(result, Channel) else "chat"
        else:
            raise ValueError("Entidad no reconocida para este username.")

        self._cache_result(cache_key, data)
        logger.info(
            "Username resolved",
            extra={"username": username, "entity_type": data["entity_type"], "outcome": "success"},
        )
        return data

    async def get_all_chats(self) -> Dict[str, Any]:
        """
        Get all chats accessible by the userbot account.

        Uses GetAllChatsRequest to retrieve every group, channel, and chat
        the account has access to — not just where the bot is a member.
        """
        state = self._pick_session()
        if state is None:
            raise _all_sessions_unavailable()

        async with state.lock:
            await asyncio.sleep(random.uniform(_MIN_DELAY_SECONDS, _MAX_DELAY_SECONDS))
            state.record_request(time.monotonic())
            try:
                result = await state.client(
                    functions.messages.GetAllChatsRequest(except_ids=[])
                )
            except Exception as exc:
                raise _all_sessions_unavailable()

        chats = []
        groups = 0
        channels = 0
        users = 0

        for chat in getattr(result, "chats", []):
            if isinstance(chat, Channel):
                channels += 1
                chats.append({
                    "id": chat.id,
                    "title": getattr(chat, "title", ""),
                    "username": getattr(chat, "username", None),
                    "type": "canal" if getattr(chat, "broadcast", False) else "supergrupo" if getattr(chat, "megagroup", False) else "grupo",
                    "verified": bool(getattr(chat, "verified", False)),
                    "scam": bool(getattr(chat, "scam", False)),
                    "participants_count": getattr(chat, "participants_count", None),
                })
            elif isinstance(chat, Chat):
                groups += 1
                chats.append({
                    "id": chat.id,
                    "title": getattr(chat, "title", ""),
                    "type": "grupo",
                    "members_count": getattr(chat, "participants_count", None),
                })
            elif isinstance(chat, User):
                users += 1

        data = {
            "total_chats": len(chats),
            "groups": groups,
            "channels": channels,
            "users": users,
            "chats": chats,
        }
        logger.info(
            "All chats retrieved",
            extra={"total": len(chats), "groups": groups, "channels": channels},
        )
        return data

    async def check_account_health(self) -> Dict[str, Any]:
        """
        Check the health and restrictions of the userbot account.

        Returns account status, restrictions, active sessions, and
        warning signals that indicate potential ban risk.
        """
        state = self._pick_session()
        if state is None:
            raise _all_sessions_unavailable()

        health: Dict[str, Any] = {
            "account_label": state.account_label,
            "session_path": state.session_path,
            "proxy_used": bool(state.proxy),
            "connected": state.client is not None,
            "authorized": False,
            "restrictions": [],
            "active_sessions": [],
            "warnings": [],
        }

        async with state.lock:
            if not state.client:
                health["warnings"].append("Session not connected")
                return health

            # Check authorization
            health["authorized"] = await state.client.is_user_authorized()
            if not health["authorized"]:
                health["warnings"].append("Session not authorized — re-login required")
                return health

            # Get current user info
            try:
                me = await state.client.get_me()
                health["user_id"] = me.id
                health["username"] = getattr(me, "username", None)
                health["first_name"] = getattr(me, "first_name", None)
                health["phone"] = getattr(me, "phone", None)

                # Check restriction flags
                if getattr(me, "restricted", False):
                    health["restrictions"].append("Account is restricted by Telegram")
                if getattr(me, "scam", False):
                    health["restrictions"].append("Account flagged as scam")
                if getattr(me, "fake", False):
                    health["restrictions"].append("Account flagged as fake")
                if getattr(me, "bot", False):
                    health["warnings"].append("Account is a bot — limited API access")

                # Check if phone is visible (privacy setting)
                if not getattr(me, "phone", None):
                    health["warnings"].append("Phone number hidden — privacy setting active")

            except Exception as exc:
                health["warnings"].append(f"Could not retrieve user info: {type(exc).__name__}")

            # Get active sessions
            try:
                auths = await state.client(
                    functions.account.GetAuthorizationsRequest()
                )
                for auth in getattr(auths, "authorizations", []):
                    session_info = {
                        "app_name": getattr(auth, "app_name", ""),
                        "device_model": getattr(auth, "device_model", ""),
                        "platform": getattr(auth, "platform", ""),
                        "system_version": getattr(auth, "system_version", ""),
                        "ip": getattr(auth, "ip", ""),
                        "country": getattr(auth, "country", ""),
                        "date_created": str(getattr(auth, "date_created", "")),
                        "date_active": str(getattr(auth, "date_active", "")),
                        "official": bool(getattr(auth, "official", False)),
                        "current": bool(getattr(auth, "current", False)),
                    }
                    health["active_sessions"].append(session_info)

                # Warn about suspicious sessions
                non_official = [
                    s for s in health["active_sessions"] if not s["official"]
                ]
                if non_official:
                    health["warnings"].append(
                        f"{len(non_official)} non-official session(s) detected"
                    )

            except Exception as exc:
                health["warnings"].append(f"Could not retrieve sessions: {type(exc).__name__}")

            # Check account TTL
            try:
                ttl = await state.client(
                    functions.account.GetAccountTTLRequest()
                )
                health["account_ttl_days"] = getattr(ttl, "days", None)
                if getattr(ttl, "days", 0) and ttl.days < 30:
                    health["warnings"].append(
                        f"Account self-destruct in {ttl.days} days"
                    )
            except Exception as exc:
                health["warnings"].append(f"Could not check TTL: {type(exc).__name__}")

        logger.info(
            "Account health check completed",
            extra={
                "account": state.account_label,
                "restrictions": len(health["restrictions"]),
                "warnings": len(health["warnings"]),
                "sessions": len(health["active_sessions"]),
            },
        )
        return health

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

    async def _run_read_query(
        self,
        *,
        target: str,
        invalid_message: str,
        query: Callable[[Any], Awaitable[Any]],
        private_message: str | None = None,
    ) -> Any:
        state = self._pick_session()
        if state is None:
            raise _all_sessions_unavailable()

        async with state.lock:
            await asyncio.sleep(random.uniform(_MIN_DELAY_SECONDS, _MAX_DELAY_SECONDS))
            state.record_request(time.monotonic())
            try:
                return await query(state.client)
            except FloodWaitError as exc:
                state.set_flood_wait(exc.seconds, time.monotonic())
                logger.warning(
                    "FloodWaitError — rotating to fallback session",
                    extra={"target": target, "wait_seconds": exc.seconds},
                )
            except (UsernameInvalidError, UsernameNotOccupiedError):
                raise ValueError(invalid_message)
            except ChannelPrivateError:
                raise ValueError(private_message or "Este canal o grupo es privado y no es accesible.")
            except UserDeactivatedError:
                raise ValueError("Esta cuenta de Telegram ha sido eliminada.")

        fallback = self._pick_fallback_session(exclude=state)
        if fallback is None:
            raise _all_sessions_unavailable()

        async with fallback.lock:
            await asyncio.sleep(random.uniform(_MIN_DELAY_SECONDS, _MAX_DELAY_SECONDS))
            fallback.record_request(time.monotonic())
            try:
                return await query(fallback.client)
            except FloodWaitError as exc:
                fallback.set_flood_wait(exc.seconds, time.monotonic())
                raise _all_sessions_unavailable()
            except (UsernameInvalidError, UsernameNotOccupiedError):
                raise ValueError(invalid_message)
            except ChannelPrivateError:
                raise ValueError(private_message or "Este canal o grupo es privado y no es accesible.")
            except UserDeactivatedError:
                raise ValueError("Esta cuenta de Telegram ha sido eliminada.")

    async def _fetch_full_user(self, entity: Any, username: str) -> Any:
        if not _TELETHON_AVAILABLE:
            return None
        return await self._run_read_query(
            target=username,
            invalid_message="Usuario de Telegram no encontrado o username invalido.",
            query=lambda client: client(functions.users.GetFullUserRequest(id=entity)),
        )

    async def _fetch_full_channel(self, entity: Any, username: str) -> Any:
        if not _TELETHON_AVAILABLE:
            return None
        return await self._run_read_query(
            target=username,
            invalid_message="Grupo o canal no encontrado o username invalido.",
            private_message="Este canal o grupo es privado y no es accesible.",
            query=lambda client: client(functions.channels.GetFullChannelRequest(channel=entity)),
        )

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


def _extract_user_recon_info(user: Any, full_user: Any | None) -> Dict[str, Any]:
    full_name = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip() or None
    photo = getattr(user, "photo", None)
    status = getattr(user, "status", None)
    return {
        "full_name": full_name,
        "language_code": getattr(user, "lang_code", None),
        "premium": _optional_bool(user, "premium"),
        "mutual_contact": _optional_bool(user, "mutual_contact"),
        "contact": _optional_bool(user, "contact"),
        "support": _optional_bool(user, "support"),
        "status_type": type(status).__name__ if status is not None else None,
        "profile_photo": {
            "has_photo": photo is not None,
            "photo_id": getattr(photo, "photo_id", None),
            "dc_id": getattr(photo, "dc_id", None),
        },
        "public_usernames": _extract_public_usernames(user),
        "common_chats_count": getattr(full_user, "common_chats_count", None),
        "blocked": _optional_bool(full_user, "blocked"),
        "settings_available": _optional_bool(full_user, "settings"),
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


def _extract_channel_recon_info(channel: Any, full_chat: Any | None) -> Dict[str, Any]:
    chat_photo = getattr(channel, "photo", None)
    location = getattr(full_chat, "location", None) if full_chat is not None else None
    call = getattr(full_chat, "call", None) if full_chat is not None else None
    return {
        "type_label": "canal" if getattr(channel, "broadcast", False) else "supergrupo" if getattr(channel, "megagroup", False) else "grupo",
        "forum": _optional_bool(channel, "forum"),
        "gigagroup": _optional_bool(channel, "gigagroup"),
        "join_to_send": _optional_bool(channel, "join_to_send"),
        "join_request": _optional_bool(channel, "join_request"),
        "noforwards": _optional_bool(channel, "noforwards"),
        "participants_hidden": _optional_bool(channel, "participants_hidden"),
        "public_usernames": _extract_public_usernames(channel),
        "linked_chat_id": getattr(full_chat, "linked_chat_id", None),
        "available_min_id": getattr(full_chat, "available_min_id", None),
        "available_length": getattr(full_chat, "available_length", None),
        "can_view_participants": _optional_bool(full_chat, "can_view_participants"),
        "can_set_username": _optional_bool(full_chat, "can_set_username"),
        "hidden_prehistory": _optional_bool(full_chat, "hidden_prehistory"),
        "slowmode_seconds": getattr(full_chat, "slowmode_seconds", None),
        "ttl_period": getattr(full_chat, "ttl_period", None),
        "location": {
            "available": location is not None,
            "address": getattr(location, "address", None),
        },
        "chat_photo": {
            "has_photo": chat_photo is not None,
            "dc_id": getattr(chat_photo, "dc_id", None),
        },
        "call_active": call is not None,
    }


def _optional_bool(value: Any, attr: str) -> bool | None:
    if value is None or not hasattr(value, attr):
        return None
    return bool(getattr(value, attr))


def _extract_public_usernames(entity: Any) -> list[str]:
    usernames = getattr(entity, "usernames", None) or []
    results: list[str] = []
    for item in usernames:
        username = getattr(item, "username", None)
        if username:
            results.append(username)
    primary_username = getattr(entity, "username", None)
    if primary_username and primary_username not in results:
        results.insert(0, primary_username)
    return results


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

    Proxy support (per account):
        TELEGRAM_PROXY_1_TYPE     — socks5, mtproto, http
        TELEGRAM_PROXY_1_ADDR     — proxy IP or hostname
        TELEGRAM_PROXY_1_PORT     — proxy port
        TELEGRAM_PROXY_1_SECRET   — MTProto secret (only for mtproto type)
        TELEGRAM_PROXY_1_USERNAME — SOCKS5 username (optional)
        TELEGRAM_PROXY_1_PASSWORD — SOCKS5 password (optional)
        (Same pattern for _2, _3, etc.)

    Account labels:
        TELEGRAM_ACCOUNT_LABEL_1  — friendly name for account 1

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

    session_configs: List[Dict[str, Any]] = []
    for i in (1, 2, 3, 4, 5):
        path = os.environ.get(f"TELEGRAM_USERBOT_SESSION_{i}", "").strip()
        if not path:
            continue
        if not os.path.exists(path):
            logger.warning(
                "Userbot session file not found — skipping",
                extra={"index": i, "path": path},
            )
            continue

        config: Dict[str, Any] = {
            "session_path": path,
            "account_label": os.environ.get(f"TELEGRAM_ACCOUNT_LABEL_{i}", f"account_{i}"),
        }

        # Check for proxy config
        proxy_type = os.environ.get(f"TELEGRAM_PROXY_{i}_TYPE", "").strip().lower()
        proxy_addr = os.environ.get(f"TELEGRAM_PROXY_{i}_ADDR", "").strip()
        proxy_port = os.environ.get(f"TELEGRAM_PROXY_{i}_PORT", "").strip()

        if proxy_type and proxy_addr and proxy_port:
            proxy: Dict[str, Any] = {
                "proxy_type": proxy_type,
                "addr": proxy_addr,
                "port": int(proxy_port),
            }
            if proxy_type == "mtproto":
                secret = os.environ.get(f"TELEGRAM_PROXY_{i}_SECRET", "").strip()
                if secret:
                    proxy["secret"] = secret
            else:
                username = os.environ.get(f"TELEGRAM_PROXY_{i}_USERNAME", "").strip()
                password = os.environ.get(f"TELEGRAM_PROXY_{i}_PASSWORD", "").strip()
                if username:
                    proxy["username"] = username
                if password:
                    proxy["password"] = password
            config["proxy"] = proxy
            logger.info(
                "Proxy configured for account",
                extra={"index": i, "type": proxy_type, "addr": proxy_addr},
            )

        session_configs.append(config)
        logger.info(
            "Userbot session found",
            extra={"index": i, "path": path, "has_proxy": "proxy" in config},
        )

    if not session_configs:
        logger.info("No valid userbot session files found — pool disabled")
        return None

    logger.info(
        "TelegramOSINTPool created",
        extra={"session_count": len(session_configs)},
    )
    return TelegramOSINTPool(api_id=api_id, api_hash=api_hash, session_paths=session_configs)
