from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from .auth_components import (
    ALLOW_LEGACY_BEARER_RESPONSE_ENV,
    ALLOW_LEGACY_WS_TOKEN_ENV,
    DEFAULT_SESSION_TTL_HOURS,
    DEFAULT_WS_TICKET_TTL_SECONDS,
    PASSWORD_HASH_PREFIX,
    SESSION_COOKIE_NAME,
    STRICT_USER_CONFIG_ENV,
    BootstrapAdminService,
    CredentialStore,
    SessionService,
    WsTicketService,
    env_flag as _env_flag,
    hash_password,
    legacy_bearer_response_enabled,
    legacy_ws_token_enabled,
    session_cookie_settings,
    strict_user_config_enabled,
    utc_now,
    verify_password,
)
from .persistence import MetadataRepository

ROLE_ORDER = {
    'viewer': 0,
    'operator': 1,
    'maintainer': 2,
    'process_engineer': 3,
    'admin': 4,
}
LEGACY_BEARER_RESPONSE_HEADER = 'x-inspection-return-token'


class AuthService:
    """Gateway authentication façade with split credential/session/ticket services."""

    def __init__(self, repository: MetadataRepository, *, users_path: str | Path | None = None, session_ttl_hours: int = DEFAULT_SESSION_TTL_HOURS, ws_ticket_ttl_seconds: int = DEFAULT_WS_TICKET_TTL_SECONDS) -> None:
        self.repository = repository
        self.session_repository = repository.session_repository
        self.users_path = Path(users_path) if users_path else None
        self.bootstrap_admin = BootstrapAdminService(repository)
        self.credential_store = CredentialStore(repository=repository, users_path=self.users_path, bootstrap_admin=self.bootstrap_admin)
        self.users = self.credential_store.load()
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.ws_ticket_ttl = timedelta(seconds=ws_ticket_ttl_seconds)
        self.session_service = SessionService(self.session_repository, self.credential_store, self.session_ttl)
        self.sessions = self.session_service.sessions
        self.ws_ticket_service = WsTicketService(self.ws_ticket_ttl, self.resolve)
        self.ws_tickets = self.ws_ticket_service.tickets

    def _clear_bootstrap_artifacts(self) -> None:
        self.bootstrap_admin.clear_bootstrap_artifacts()

    def change_password(self, *, session_token: str, current_password: str, new_password: str) -> dict[str, Any]:
        result = self.session_service.change_password(
            session_token=session_token,
            current_password=current_password,
            new_password=new_password,
            after_change=self._after_password_change,
        )
        return result

    def _after_password_change(self, token: str) -> None:
        self.credential_store.persist()
        self._clear_bootstrap_artifacts()
        self.revoke(token)

    def login(self, *, username: str, password: str, client_ip: str = '', user_agent: str = '') -> dict[str, Any]:
        return self.session_service.login(username=username, password=password, client_ip=client_ip, user_agent=user_agent)

    def resolve(self, token: str | None, touch: bool = True) -> dict[str, Any] | None:
        return self.session_service.resolve(token, touch=touch)

    def revoke(self, token: str) -> None:
        self.session_service.revoke(token)
        self.ws_ticket_service.revoke_token(token)

    def has_role(self, role: str, minimum: str) -> bool:
        return ROLE_ORDER.get(str(role).lower(), -1) >= ROLE_ORDER.get(str(minimum).lower(), 0)

    def session_cookie_max_age_seconds(self) -> int:
        return int(self.session_ttl.total_seconds())

    def should_return_legacy_bearer_token(self, request_header_value: str | None) -> bool:
        return legacy_bearer_response_enabled() and str(request_header_value or '').strip().lower() in {'1', 'true', 'yes', 'on'}

    def resolve_websocket_session(self, *, ticket: str | None, token: str | None = None) -> dict[str, Any] | None:
        session = self.consume_ws_ticket(ticket)
        if session is not None:
            return session
        if legacy_ws_token_enabled():
            return self.resolve(token, touch=True)
        return None

    def issue_ws_ticket(self, session_token: str) -> dict[str, Any]:
        return self.ws_ticket_service.issue(session_token)

    def consume_ws_ticket(self, ticket: str | None) -> dict[str, Any] | None:
        return self.ws_ticket_service.consume(ticket)
