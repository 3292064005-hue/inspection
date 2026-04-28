from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import AuthService, LEGACY_BEARER_RESPONSE_HEADER, session_cookie_settings
from ..context import GatewayAppContext
from ..dependencies import get_auth_service, get_context, require_session
from ..responses import api_ok
from ..schemas import ChangeGatewayPasswordRequest, LoginGatewaySessionRequest

router = APIRouter(tags=['auth'])


@router.post('/auth/login', operation_id='loginGatewaySession')
async def login(payload: LoginGatewaySessionRequest, request: Request, response: Response, auth_service: AuthService = Depends(get_auth_service), context: GatewayAppContext = Depends(get_context)) -> dict:
    username = str(payload.username).strip()
    password = str(payload.password)
    if not username or not password:
        context.audit(actor=username or 'anonymous', role='viewer', action='AUTH_LOGIN', resource='/auth/login', result='FAILED', details={'reason': 'EMPTY_CREDENTIALS'})
        raise HTTPException(status_code=400, detail='用户名和密码不能为空。')
    try:
        session = auth_service.login(username=username, password=password, client_ip=request.client.host if request.client else '', user_agent=request.headers.get('user-agent', ''))
    except ValueError as exc:
        context.audit(actor=username or 'anonymous', role='viewer', action='AUTH_LOGIN', resource='/auth/login', result='FAILED', details={'reason': str(exc)})
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    cookie_settings = session_cookie_settings()
    response.set_cookie(cookie_settings.pop('key'), session['token'], max_age=auth_service.session_cookie_max_age_seconds(), **cookie_settings)
    legacy_token_response = auth_service.should_return_legacy_bearer_token(request.headers.get(LEGACY_BEARER_RESPONSE_HEADER, ''))
    context.audit(
        actor=session['username'],
        role=session['role'],
        action='AUTH_LOGIN',
        resource='/auth/login',
        details={
            'clientIp': session.get('clientIp', ''),
            'userAgent': session.get('userAgent', ''),
            'mustChangePassword': session.get('mustChangePassword', False),
            'legacyBearerResponse': legacy_token_response,
        },
    )
    meta = {'token': session['token']} if legacy_token_response else None
    return api_ok({k: v for k, v in session.items() if k != 'token'}, meta=meta, message='login_ok')


@router.get('/auth/session', operation_id='getGatewaySession')
async def session_info(session: dict = Depends(require_session)) -> dict:
    return api_ok({k: v for k, v in session.items() if k != 'token'})


@router.post('/auth/logout', operation_id='logoutGatewaySession')
async def logout(response: Response, session: dict = Depends(require_session), auth_service: AuthService = Depends(get_auth_service), context: GatewayAppContext = Depends(get_context)) -> dict:
    auth_service.revoke(str(session.get('token', '')))
    cookie_settings = session_cookie_settings()
    response.delete_cookie(cookie_settings['key'], path='/', samesite=cookie_settings['samesite'], secure=cookie_settings['secure'], httponly=True)
    context.audit(actor=str(session.get('username', 'anonymous')), role=str(session.get('role', 'viewer')), action='AUTH_LOGOUT', resource='/auth/logout')
    return api_ok({'loggedOut': True})


@router.post('/auth/ws-ticket', operation_id='issueGatewayWsTicket')
async def issue_ws_ticket(session: dict = Depends(require_session), auth_service: AuthService = Depends(get_auth_service)) -> dict:
    return api_ok(auth_service.issue_ws_ticket(str(session.get('token', ''))), message='ws_ticket_issued')


@router.post('/auth/change-password', operation_id='changeGatewayPassword')
async def change_password(payload: ChangeGatewayPasswordRequest, response: Response, session: dict = Depends(require_session), auth_service: AuthService = Depends(get_auth_service), context: GatewayAppContext = Depends(get_context)) -> dict:
    current_password = str(payload.currentPassword)
    new_password = str(payload.newPassword)
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail='当前密码和新密码不能为空。')
    try:
        result = auth_service.change_password(session_token=str(session.get('token', '')), current_password=current_password, new_password=new_password)
    except ValueError as exc:
        context.audit(actor=str(session.get('username', 'anonymous')), role=str(session.get('role', 'viewer')), action='AUTH_CHANGE_PASSWORD', resource='/auth/change-password', result='FAILED', details={'reason': str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cookie_settings = session_cookie_settings()
    response.delete_cookie(cookie_settings['key'], path='/', samesite=cookie_settings['samesite'], secure=cookie_settings['secure'], httponly=True)
    context.audit(actor=str(session.get('username', 'anonymous')), role=str(session.get('role', 'viewer')), action='AUTH_CHANGE_PASSWORD', resource='/auth/change-password')
    return api_ok(result, message='password_changed')
