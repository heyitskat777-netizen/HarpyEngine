"""Discord OAuth and private test-guild sessions for the local Activity lab."""

import json
import logging
import math
import re
import secrets
from dataclasses import dataclass, field, replace
from hashlib import sha256
from http import HTTPStatus
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCOPES = frozenset({"identify", "guilds.members.read"})
MEMBERSHIP_CACHE_SECONDS = 20
logger = logging.getLogger("harpy_activity.discord")
_provider_cooldowns = {}
_provider_lock = Lock()


@dataclass(frozen=True)
class DiscordConfig:
    client_id: str
    client_secret: str = field(repr=False)
    guild_id: str
    invited_user_id: str | None = None
    other_user_id: str | None = None
    allow_dm: bool = False
    handler_user_id: str | None = None
    tester_role_ids: frozenset[str] = frozenset()

    @property
    def origin(self) -> str:
        return f"https://{self.client_id}.discordsays.com"

    @classmethod
    def load(cls, environ, *, allow_dm: bool = False, campaign_roles_only: bool = False):
        names = {
            "client_id": "CLIENT_ID",
            "client_secret": "CLIENT_SECRET",
            "guild_id": "GUILD_ID",
            "invited_user_id": "INVITED_USER_ID",
            "other_user_id": "OTHER_USER_ID",
            "handler_user_id": "HANDLER_USER_ID",
        }
        values = {
            key: environ.get(f"GIRLFRAME_ACTIVITY_DISCORD_{env_name}", "").strip()
            for key, env_name in names.items()
        }
        if campaign_roles_only:
            for key in ("invited_user_id", "other_user_id", "handler_user_id"):
                values[key] = None
        missing = [
            f"GIRLFRAME_ACTIVITY_DISCORD_{names[key]}"
            for key, value in values.items()
            if not value
            and key not in (
                "other_user_id",
                "handler_user_id",
                *(("invited_user_id",) if campaign_roles_only else ()),
            )
        ]
        if missing:
            raise ValueError(
                "Missing development Discord configuration: " + ", ".join(missing)
            )
        if any(
            not re.fullmatch(r"[0-9]{17,20}", value)
            for key, value in values.items()
            if value and key != "client_secret"
        ):
            raise ValueError(
                "Use numeric Discord application, server and test account IDs."
            )
        accounts = [
            value for key, value in values.items() if key.endswith("_user_id") and value
        ]
        if len(set(accounts)) != len(accounts):
            raise ValueError(
                "Use distinct Discord accounts for pilots and the Handler."
            )
        for key in ("invited_user_id", "other_user_id", "handler_user_id"):
            values[key] = values[key] or None
        roles = frozenset() if campaign_roles_only else frozenset(
            environ.get("GIRLFRAME_ACTIVITY_DISCORD_TESTER_ROLE_IDS", "").split()
        )
        if any(
            role == values["guild_id"] or not re.fullmatch(r"[1-9][0-9]{16,19}", role)
            for role in roles
        ):
            raise ValueError(
                "Use individual Girl or Frame role IDs from the private test server."
            )
        return cls(**values, allow_dm=allow_dm, tester_role_ids=roles)


class SignInError(Exception):
    def __init__(self, status: HTTPStatus, message: str, *, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def relay_limited(delay):
    seconds = math.ceil(delay)
    return SignInError(
        HTTPStatus.TOO_MANY_REQUESTS,
        f"The identity relay is rate-limiting this connection. Retry in {seconds} seconds.",
        retry_after=seconds,
    )


def discord_request(path, *, token=None, form=None):
    route = ("route", path)
    auth_route = ("user", path, sha256(token.encode()).digest()) if token else route
    with _provider_lock:
        now = monotonic()
        for key, deadline in tuple(_provider_cooldowns.items()):
            if deadline <= now:
                del _provider_cooldowns[key]
        deadline = max(_provider_cooldowns.get(key, 0) for key in ("*", route, auth_route))
    if deadline > now:
        raise relay_limited(deadline - now)
    headers = {"User-Agent": "GIRLFRAME Activity Lab (Discord OAuth)"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = urlencode(form).encode() if form is not None else None
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(f"https://discord.com/api/v10{path}", data=body, headers=headers)
    operation = (
        "token exchange"
        if form is not None
        else ("identity" if path == "/users/@me" else "membership")
    )
    # A Discord authorization code is single-use. Retry only provider reads.
    attempts = 1 if form is not None else 3
    for attempt in range(attempts):
        delay = 0.25 * (attempt + 1)
        try:
            with urlopen(request, timeout=8 if form is not None else 3) as response:
                value = json.load(response)
                if not isinstance(value, dict):
                    raise TypeError("Unexpected Discord API response.")
                return value
        except HTTPError as error:
            status = error.code
            retry_after = error.headers.get("Retry-After", "")
            rate_scope = error.headers.get("X-RateLimit-Scope", "").lower()
            limited = {}
            if status == 429:
                try:
                    limited = json.load(error)
                    if not isinstance(limited, dict):
                        limited = {}
                except (ValueError, TypeError):
                    pass
            error.close()
            logger.warning("Discord %s returned HTTP %s", operation, status)
            if status in (400, 401, 403, 404):
                raise SignInError(
                    HTTPStatus.FORBIDDEN,
                    "Identity or duty-group clearance was denied.",
                ) from None
            if status == 429:
                try:
                    delay = max(1, float(limited.get("retry_after", retry_after or 5)))
                    if not math.isfinite(delay):
                        delay = 5
                except (ValueError, TypeError):
                    delay = 5
                with _provider_lock:
                    scope = "*" if limited.get("global") is True or rate_scope == "global" else (
                        auth_route if rate_scope == "user" else route
                    )
                    _provider_cooldowns[scope] = max(_provider_cooldowns.get(scope, 0), monotonic() + delay)
                raise relay_limited(delay) from None
            elif status not in (500, 502, 503, 504):
                break
        except (URLError, TimeoutError, TypeError, ValueError) as error:
            logger.warning("Discord %s failed (%s)", operation, type(error).__name__)
        if attempt + 1 == attempts or delay > 2:
            break
        sleep(delay)
    raise SignInError(
        HTTPStatus.SERVICE_UNAVAILABLE,
        f"The identity relay {operation} is temporarily unavailable.",
    )


@dataclass(frozen=True)
class VerifiedSession:
    role: str
    discord_id: str
    expires: float
    role_ids: frozenset[str]
    oauth_token: str | None = field(default=None, repr=False, compare=False)
    membership_checked_at: float = field(default=float("-inf"), compare=False)
    membership_lock: Lock = field(default_factory=Lock, repr=False, compare=False)


class DiscordSessions:
    def __init__(self, config: DiscordConfig, request=discord_request):
        self.config = config
        self.request = request
        self.roles = {config.invited_user_id: "invited"} if config.invited_user_id else {}
        if config.other_user_id:
            self.roles[config.other_user_id] = "other"
        if config.handler_user_id:
            self.roles[config.handler_user_id] = "handler"
        self.challenges: dict[str, float] = {}
        self.sessions: dict[str, VerifiedSession] = {}
        self.lock = Lock()
        self.managed_roles = lambda: frozenset()
        self.campaign_roles_only = False

    def can_use_default(self, session):
        if self.campaign_roles_only:
            return False
        return session.role != "role_tester" or bool(
            self.config.tester_role_ids & session.role_ids
        )

    def challenge(self) -> str:
        nonce = secrets.token_urlsafe(32)
        now = monotonic()
        with self.lock:
            self.challenges = {
                key: expiry for key, expiry in self.challenges.items() if expiry > now
            }
            if len(self.challenges) >= 128:
                raise SignInError(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    "Too many pending sign-ins. Try shortly.",
                )
            self.challenges[nonce] = now + 180
        return nonce

    def exchange(self, code: str, nonce: str, guild_id: str | None) -> dict:
        with self.lock:
            expiry = self.challenges.pop(nonce, 0)
        if expiry <= monotonic():
            raise SignInError(HTTPStatus.BAD_REQUEST, "Start a fresh Discord sign-in.")
        if guild_id != self.config.guild_id and not (
            guild_id is None and self.config.allow_dm
        ):
            raise SignInError(
                HTTPStatus.FORBIDDEN, "Launch from the configured campaign server."
            )
        tokens = self.request(
            "/oauth2/token",
            form={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "grant_type": "authorization_code",
                "code": code,
            },
        )
        access = tokens.get("access_token")
        seconds = tokens.get("expires_in")
        scopes = tokens.get("scope", "")
        if (
            not isinstance(access, str)
            or not access
            or type(seconds) is not int
            or seconds <= 0
            or not isinstance(scopes, str)
            or not SCOPES.issubset(scopes.split())
        ):
            raise SignInError(
                HTTPStatus.FORBIDDEN,
                "Present identity and campaign membership credentials.",
            )
        expires = monotonic() + min(seconds, 3600)
        user = self.request("/users/@me", token=access)
        discord_id = user.get("id")
        if not isinstance(discord_id, str) or not re.fullmatch(
            r"[1-9][0-9]{16,19}", discord_id
        ):
            raise SignInError(
                HTTPStatus.FORBIDDEN, "The identity relay did not verify a personnel identifier."
            )
        role = self.roles.get(discord_id)
        if (
            not self.campaign_roles_only
            and role is None
            and not (self.config.tester_role_ids or self.managed_roles())
        ):
            raise SignInError(
                HTTPStatus.FORBIDDEN,
                "This Discord account is outside the private test roster.",
            )
        roles = self._discord_roles(discord_id, access)
        session = VerifiedSession(
            "campaign_member" if self.campaign_roles_only else role or "role_tester",
            discord_id,
            expires,
            roles,
            access,
            monotonic(),
        )
        if not self.can_use_default(session) and not self.managed_roles().intersection(
            session.role_ids
        ):
            raise SignInError(
                HTTPStatus.FORBIDDEN,
                "The Discord role assigned to a campaign is required."
                if self.campaign_roles_only
                else "An approved Girl or Frame role or a bound campaign role is required.",
            )
        handle = secrets.token_urlsafe(32)
        with self.lock:
            now = monotonic()
            if session.expires <= now:
                raise SignInError(HTTPStatus.UNAUTHORIZED, "Sign in to the Activity.")
            self.sessions = {
                key: value
                for key, value in self.sessions.items()
                if value.expires > now
            }
            if len(self.sessions) >= 256:
                raise SignInError(
                    HTTPStatus.TOO_MANY_REQUESTS, "Too many active Activity sessions."
                )
            self.sessions[handle] = session
        return {
            "access_token": access,
            "session": handle,
            "discord_user_id": discord_id,
        }

    def _discord_roles(self, discord_id: str, access: str) -> frozenset[str]:
        member = self.request(
            f"/users/@me/guilds/{self.config.guild_id}/member",
            token=access,
        )
        user = member.get("user")
        if member.get("pending") is True or (
            user is not None
            and (not isinstance(user, dict) or user.get("id") != discord_id)
        ):
            raise SignInError(
                HTTPStatus.FORBIDDEN,
                "Active membership in the campaign server is required.",
            )
        roles = member.get("roles")
        return (
            frozenset(roles)
            if isinstance(roles, list) and all(isinstance(role, str) for role in roles)
            else frozenset()
        )

    def resolve(self, authorization: str, *, fresh: bool = False, force: bool = False) -> VerifiedSession:
        scheme, _, handle = authorization.partition(" ")
        with self.lock:
            session = self.sessions.get(handle) if scheme == "Bearer" else None
        if session is None or session.expires <= monotonic():
            raise SignInError(HTTPStatus.UNAUTHORIZED, "Sign in to the Activity.")
        if fresh or force:
            with session.membership_lock:
                with self.lock:
                    session = self.sessions.get(handle)
                now = monotonic()
                if session is None or session.expires <= now:
                    raise SignInError(HTTPStatus.UNAUTHORIZED, "Sign in to the Activity.")
                if not force and now - session.membership_checked_at < MEMBERSHIP_CACHE_SECONDS:
                    return session
                if session.oauth_token is None:
                    raise SignInError(HTTPStatus.UNAUTHORIZED, "Sign in to refresh campaign clearance.")
                try:
                    roles = self._discord_roles(session.discord_id, session.oauth_token)
                except SignInError as error:
                    if error.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                        with self.lock:
                            self.sessions.pop(handle, None)
                    raise
                now = monotonic()
                with self.lock:
                    if handle not in self.sessions or session.expires <= now:
                        raise SignInError(HTTPStatus.UNAUTHORIZED, "Sign in to the Activity.")
                    session = replace(session, role_ids=roles, membership_checked_at=now)
                    self.sessions[handle] = session
        return session
