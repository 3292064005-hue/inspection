from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import AuthService, SESSION_COOKIE_NAME, session_cookie_settings
from .context import GatewayAppContext

http_bearer = HTTPBearer(auto_error=False)


def get_context(request: Request) -> GatewayAppContext:
    context = getattr(request.app.state, 'gateway_context', None)
    if context is None:
        raise HTTPException(status_code=503, detail='Gateway context is not ready.')
    return context


def get_auth_service(context: GatewayAppContext = Depends(get_context)) -> AuthService:
    return context.auth_service


def get_optional_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any] | None:
    cookie_key = str(session_cookie_settings().get('key', SESSION_COOKIE_NAME)) or SESSION_COOKIE_NAME
    session_cookie = request.cookies.get(cookie_key) or request.cookies.get(SESSION_COOKIE_NAME)
    token = credentials.credentials if credentials else session_cookie
    return auth_service.resolve(token)


def require_session(session: dict[str, Any] | None = Depends(get_optional_session)) -> dict[str, Any]:
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='未认证或会话已过期。')
    return session


def require_role(minimum_role: str):
    def _dependency(
        session: dict[str, Any] = Depends(require_session),
        auth_service: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        if not auth_service.has_role(str(session.get('role', 'viewer')), minimum_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'当前账号缺少 {minimum_role} 权限。')
        return session

    return _dependency


def get_node(context: GatewayAppContext = Depends(get_context)) -> Any:
    try:
        return context.node()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
