from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from inspection_utils.config_common import load_yaml, save_yaml

PASSWORD_HASH_PREFIX = 'pbkdf2_sha256'
DEFAULT_PBKDF2_ITERATIONS = 240_000
DEFAULT_SESSION_TTL_HOURS = 12
DEFAULT_WS_TICKET_TTL_SECONDS = 60
SESSION_COOKIE_NAME = 'inspection_session'
ALLOW_LEGACY_BEARER_RESPONSE_ENV = 'INSPECTION_HMI_ALLOW_LEGACY_BEARER_RESPONSE'
ALLOW_LEGACY_WS_TOKEN_ENV = 'INSPECTION_HMI_ALLOW_LEGACY_WS_TOKEN'
STRICT_USER_CONFIG_ENV = 'INSPECTION_HMI_STRICT_USER_CONFIG'


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def strict_user_config_enabled() -> bool:
    return env_flag(STRICT_USER_CONFIG_ENV, default=False)


def legacy_bearer_response_enabled() -> bool:
    return env_flag(ALLOW_LEGACY_BEARER_RESPONSE_ENV, default=False)


def legacy_ws_token_enabled() -> bool:
    return env_flag(ALLOW_LEGACY_WS_TOKEN_ENV, default=False)


def session_cookie_settings() -> dict[str, Any]:
    same_site = str(os.environ.get('INSPECTION_HMI_COOKIE_SAMESITE', 'lax')).strip().lower() or 'lax'
    if same_site not in {'lax', 'strict', 'none'}:
        same_site = 'lax'
    secure_default = same_site == 'none'
    secure = str(os.environ.get('INSPECTION_HMI_COOKIE_SECURE', '1' if secure_default else '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
    return {
        'key': str(os.environ.get('INSPECTION_HMI_SESSION_COOKIE_NAME', SESSION_COOKIE_NAME)).strip() or SESSION_COOKIE_NAME,
        'httponly': True,
        'secure': secure,
        'samesite': same_site,
        'path': '/',
    }


def hash_password(password: str, *, iterations: int = DEFAULT_PBKDF2_ITERATIONS, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_value.encode('utf-8'), iterations)
    return f'{PASSWORD_HASH_PREFIX}${iterations}${salt_value}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    raw = str(encoded or '')
    if not raw:
        return False
    if not raw.startswith(f'{PASSWORD_HASH_PREFIX}$'):
        return secrets.compare_digest(raw, password)
    try:
        _prefix, raw_iterations, salt, expected = raw.split('$', 3)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(raw_iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


@dataclass(slots=True)
class BootstrapAdminService:
    repository: Any

    def bootstrap_root(self) -> Path:
        return self.repository.path.parent / 'bootstrap'

    def bootstrap_file(self) -> Path:
        return self.bootstrap_root() / 'bootstrap_admin.yaml'

    def bootstrap_secret_file(self) -> Path:
        return self.bootstrap_root() / 'bootstrap_admin.once.txt'

    def bootstrap_env_password(self) -> str:
        return str(os.environ.get('INSPECTION_HMI_BOOTSTRAP_PASSWORD', '')).strip()

    def ensure_bootstrap_admin(self) -> dict[str, dict[str, Any]]:
        bootstrap_path = self.bootstrap_file()
        bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
        if bootstrap_path.exists():
            payload = load_yaml(bootstrap_path)
            if isinstance(payload, dict):
                username = str(payload.get('username', 'admin')).strip() or 'admin'
                password_hash = str(payload.get('password_hash', '')).strip()
                if password_hash:
                    return {
                        username: {
                            'passwordHash': password_hash,
                            'role': 'admin',
                            'displayName': str(payload.get('display_name', '系统管理员')),
                            'bootstrap': True,
                        }
                    }
        username = str(os.environ.get('INSPECTION_HMI_BOOTSTRAP_USERNAME', 'admin')).strip() or 'admin'
        password_plain = self.bootstrap_env_password() or secrets.token_urlsafe(18)
        payload = {
            'username': username,
            'display_name': '系统管理员',
            'password_hash': hash_password(password_plain),
            'created_at': utc_now(),
            'note': '首次启动生成的引导管理员。登录后请立即修改密码或迁移到正式账号配置。',
        }
        save_yaml(bootstrap_path, payload)
        if not self.bootstrap_env_password():
            self.bootstrap_secret_file().write_text(
                f'username: {username}\npassword: {password_plain}\ncreated_at: {payload["created_at"]}\nnote: 此一次性凭证文件应在首次成功登录后自动清理。\n',
                encoding='utf-8',
            )
        return {
            username: {
                'passwordHash': str(payload['password_hash']),
                'role': 'admin',
                'displayName': str(payload['display_name']),
                'bootstrap': True,
            }
        }

    def clear_bootstrap_artifacts(self) -> None:
        for path in (self.bootstrap_file(), self.bootstrap_secret_file()):
            try:
                path.unlink(missing_ok=True)
            except TypeError:
                if path.exists():
                    path.unlink()


@dataclass(slots=True)
class CredentialStore:
    repository: Any
    users_path: Path | None
    bootstrap_admin: BootstrapAdminService
    users: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load(self) -> dict[str, dict[str, Any]]:
        loaded: dict[str, dict[str, Any]] = {}
        invalid_entries: list[str] = []
        explicit_config_present = False
        if self.users_path:
            path = Path(self.users_path)
            if path.exists():
                explicit_config_present = True
                try:
                    payload = load_yaml(path)
                except Exception as exc:
                    if strict_user_config_enabled():
                        raise RuntimeError(f'用户配置加载失败: {path}') from exc
                    payload = {}
                users = payload.get('users', {}) if isinstance(payload, dict) else {}
                if strict_user_config_enabled() and not isinstance(users, dict):
                    raise RuntimeError(f'用户配置格式无效: {path}')
                if isinstance(users, dict):
                    for username, data in users.items():
                        if not isinstance(data, dict):
                            invalid_entries.append(str(username))
                            continue
                        password_hash = str(data.get('password_hash', '')).strip()
                        legacy_password = str(data.get('password', '')).strip()
                        if not password_hash and legacy_password:
                            password_hash = hash_password(legacy_password)
                        if not password_hash:
                            invalid_entries.append(str(username))
                            continue
                        loaded[str(username)] = {
                            'passwordHash': password_hash,
                            'role': str(data.get('role', 'viewer')).lower(),
                            'displayName': str(data.get('display_name', data.get('displayName', username))),
                            'bootstrap': bool(data.get('bootstrap', False)),
                        }
        if loaded:
            self.users = loaded
            return self.users
        if strict_user_config_enabled() and explicit_config_present:
            detail = ', '.join(invalid_entries) if invalid_entries else '未提供任何可用用户'
            raise RuntimeError(f'用户配置无效，无法加载可用账号: {detail}')
        self.users = self.bootstrap_admin.ensure_bootstrap_admin()
        return self.users

    def persist(self) -> None:
        if self.users_path is None:
            return
        payload = {'users': {}}
        for username, data in self.users.items():
            payload['users'][username] = {
                'password_hash': str(data.get('passwordHash', '')),
                'role': str(data.get('role', 'viewer')),
                'display_name': str(data.get('displayName', username)),
                'bootstrap': bool(data.get('bootstrap', False)),
            }
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.users_path, payload)


@dataclass(slots=True)
class SessionService:
    session_repository: Any
    credential_store: CredentialStore
    session_ttl: timedelta
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def login(self, *, username: str, password: str, client_ip: str = '', user_agent: str = '') -> dict[str, Any]:
        user = self.credential_store.users.get(username)
        if not user or not verify_password(password, str(user.get('passwordHash', ''))):
            raise ValueError('用户名或密码错误。')
        issued_at = utc_now()
        expires_at = (parse_ts(issued_at) + self.session_ttl).isoformat(timespec='seconds').replace('+00:00', 'Z')
        token = secrets.token_urlsafe(32)
        session = {
            'token': token,
            'username': username,
            'displayName': str(user.get('displayName', username)),
            'role': str(user.get('role', 'viewer')).lower(),
            'issuedAt': issued_at,
            'expiresAt': expires_at,
            'lastSeenAt': issued_at,
            'clientIp': client_ip,
            'userAgent': user_agent,
            'bootstrap': bool(user.get('bootstrap', False)),
            'mustChangePassword': bool(user.get('bootstrap', False)),
        }
        self.sessions[token] = session
        self.session_repository.upsert(session)
        return dict(session)

    def resolve(self, token: str | None, *, touch: bool = True) -> dict[str, Any] | None:
        if not token:
            return None
        raw_token = str(token)
        session = self.sessions.get(raw_token)
        if session is None:
            session = self.session_repository.get_active(raw_token)
            if session is None:
                return None
            username = str(session.get('username', '')).strip()
            user = self.credential_store.users.get(username, {})
            session['bootstrap'] = bool(user.get('bootstrap', False))
            session['mustChangePassword'] = bool(user.get('bootstrap', False))
            self.sessions[raw_token] = session
        if parse_ts(str(session['expiresAt'])) <= datetime.now(UTC):
            self.revoke(raw_token)
            return None
        if touch:
            session['lastSeenAt'] = utc_now()
            self.session_repository.upsert(session)
        return dict(session)

    def revoke(self, token: str) -> None:
        self.sessions.pop(str(token), None)
        self.session_repository.deactivate(str(token))

    def change_password(self, *, session_token: str, current_password: str, new_password: str, after_change: Callable[[str], None]) -> dict[str, Any]:
        session = self.resolve(session_token, touch=True)
        if session is None:
            raise ValueError('未认证或会话已过期。')
        username = str(session.get('username', '')).strip()
        user = self.credential_store.users.get(username)
        if user is None:
            raise ValueError('当前账号不存在。')
        if not verify_password(current_password, str(user.get('passwordHash', ''))):
            raise ValueError('当前密码不正确。')
        candidate = str(new_password or '')
        if len(candidate) < 10:
            raise ValueError('新密码长度至少为 10 位。')
        user['passwordHash'] = hash_password(candidate)
        user['bootstrap'] = False
        self.credential_store.users[username] = user
        self.credential_store.persist()
        after_change(str(session.get('token', '')))
        return {'passwordChanged': True, 'username': username, 'sessionRevoked': True}


@dataclass(slots=True)
class WsTicketService:
    ticket_ttl: timedelta
    session_resolver: Callable[[str | None, bool], dict[str, Any] | None]
    tickets: dict[str, dict[str, Any]] = field(default_factory=dict)

    def issue(self, session_token: str) -> dict[str, Any]:
        session = self.session_resolver(session_token, True)
        if session is None:
            raise ValueError('未认证或会话已过期。')
        expires_at = (datetime.now(UTC) + self.ticket_ttl).isoformat(timespec='seconds').replace('+00:00', 'Z')
        ticket = secrets.token_urlsafe(24)
        self.tickets[ticket] = {'token': str(session['token']), 'expiresAt': expires_at}
        return {'ticket': ticket, 'expiresAt': expires_at}

    def consume(self, ticket: str | None) -> dict[str, Any] | None:
        if not ticket:
            return None
        payload = self.tickets.pop(str(ticket), None)
        if payload is None:
            return None
        if parse_ts(str(payload['expiresAt'])) <= datetime.now(UTC):
            return None
        return self.session_resolver(str(payload.get('token', '')), True)

    def revoke_token(self, token: str) -> None:
        for ticket, payload in list(self.tickets.items()):
            if str(payload.get('token', '')) == str(token):
                self.tickets.pop(ticket, None)
