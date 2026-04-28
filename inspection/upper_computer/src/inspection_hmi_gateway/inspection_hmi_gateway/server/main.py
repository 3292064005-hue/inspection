from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from inspection_utils.io_common import resolve_under_root

from .bootstrap import build_gateway_context
from .context import set_request_id
from .responses import api_error, api_ok, utc_now
from .dependencies import require_role
from .runtime_assets import resolve_gateway_paths
from .websocket_transport import handle_gateway_websocket
from .routers import actions, auth, audit, diagnostics, exports, health, internal_actions, recipes, replay, results, station, telemetry


LOGGER = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    raw = os.environ.get(
        'INSPECTION_HMI_CORS_ORIGINS',
        'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8080,http://localhost:8080',
    )
    return [item.strip() for item in raw.split(',') if item.strip()]


def _install_versioned_routers(app: FastAPI) -> None:
    for router in (health.router, auth.router, station.router, results.router, recipes.router, diagnostics.router, exports.router, replay.router, actions.router, telemetry.router, audit.router):
        app.include_router(router, prefix='/api/v1')
    app.include_router(internal_actions.router, prefix='/api/internal')


def create_app(
    *,
    log_root: str = 'logs/runtime',
    recipe_root: str = 'config/recipes',
    frontend_dist: str = 'frontend/dist',
    users_path: str = 'config/system/hmi_users.yaml',
    runtime_factory: Any | None = None,
    require_frontend_dist: bool | None = None,
) -> FastAPI:
    """Create the FastAPI gateway application.

    Args:
        log_root: Runtime log root containing artifacts and result data.
        recipe_root: Recipe repository path.
        frontend_dist: Built frontend directory served by the gateway.
        users_path: YAML user database path.
        runtime_factory: Optional runtime factory used by tests or alternate deployment modes.
        require_frontend_dist: Optional strictness flag for release deployments.

    Returns:
        Configured FastAPI application instance.
    """
    resolved_paths = resolve_gateway_paths(log_root=log_root, recipe_root=recipe_root, frontend_dist=frontend_dist, users_path=users_path, require_frontend_dist=require_frontend_dist)
    log_root_path = resolved_paths.log_root
    recipe_root_path = resolved_paths.recipe_root
    frontend_dist_path = resolved_paths.frontend_dist
    users_path_resolved = resolved_paths.users_path
    if runtime_factory is not None:
        runtime = runtime_factory()
    else:
        from ..gateway_runtime import GatewayRuntime

        runtime = GatewayRuntime(log_root=str(log_root_path), recipe_root=str(recipe_root_path))
    context = build_gateway_context(
        runtime=runtime,
        log_root=log_root_path,
        recipe_root=recipe_root_path,
        frontend_dist=frontend_dist_path,
        users_path=users_path_resolved,
    )
    auth_service = context.auth_service

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if hasattr(runtime, 'start'):
            runtime.start()
        event_bus = getattr(runtime, 'event_bus', None)
        if event_bus is not None:
            event_bus.attach_loop(asyncio.get_running_loop())
        app.state.gateway_context = context
        try:
            yield
        finally:
            context.close()
            if hasattr(runtime, 'stop'):
                runtime.stop()

    app = FastAPI(title='Inspection HMI Gateway', version='1.0.0', lifespan=lifespan)

    @app.middleware('http')
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get('x-request-id', '') or os.urandom(8).hex()
        request.state.request_id = request_id
        set_request_id(request_id)
        response = await call_next(request)
        response.headers['X-Request-Id'] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, 'request_id', '')
        detail = exc.detail
        message = 'Request failed.'
        if isinstance(detail, dict):
            payload_message = detail.get('message')
            if isinstance(payload_message, str) and payload_message.strip():
                message = payload_message
            else:
                message = str(detail) if detail else 'Request failed.'
        elif detail:
            message = str(detail)
        headers = {str(key): str(value) for key, value in dict(getattr(exc, 'headers', {}) or {}).items()}
        if request_id:
            headers['X-Request-Id'] = request_id
        return JSONResponse(
            status_code=exc.status_code,
            content=api_error(
                message,
                code=f'HTTP_{exc.status_code}',
                detail=detail,
                status_code=exc.status_code,
                request_id=request_id,
            ),
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, 'request_id', '')
        try:
            detail = exc.errors(include_url=False)
        except TypeError:
            detail = exc.errors()
        return JSONResponse(
            status_code=422,
            content=api_error('请求参数校验失败。', code='VALIDATION_ERROR', detail=detail, status_code=422, request_id=request_id),
            headers={'X-Request-Id': request_id} if request_id else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, 'request_id', '')
        LOGGER.exception('Unhandled gateway exception. request_id=%s path=%s', request_id, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=api_error('服务器内部错误。', code='INTERNAL_SERVER_ERROR', detail={'requestId': request_id} if request_id else None, status_code=500, request_id=request_id),
            headers={'X-Request-Id': request_id} if request_id else None,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    log_root_path.mkdir(parents=True, exist_ok=True)
    _install_versioned_routers(app)

    @app.get('/artifacts/{artifact_path:path}')
    async def read_artifact(artifact_path: str, _session: dict = Depends(require_role('viewer'))) -> FileResponse:
        try:
            target = resolve_under_root(log_root_path, artifact_path)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail='Artifact not found') from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail='Artifact not found')
        return FileResponse(target)

    @app.get('/api/health')
    async def legacy_health() -> dict[str, Any]:
        runtime_health = runtime.health() if hasattr(runtime, 'health') and callable(runtime.health) else {'runtimeReady': getattr(runtime, 'node', None) is not None}
        return api_ok({'version': '1.0.0', 'runtime': runtime_health})

    @app.websocket('/ws')
    @app.websocket('/ws/v1')
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await handle_gateway_websocket(
            websocket=websocket,
            auth_service=auth_service,
            event_bus=getattr(runtime, 'event_bus', None),
            context=context,
        )

    if frontend_dist_path.exists():
        app.mount('/assets', StaticFiles(directory=str(frontend_dist_path / 'assets'), check_dir=False), name='frontend-assets')

        @app.get('/')
        async def index() -> FileResponse:
            return FileResponse(frontend_dist_path / 'index.html')

        @app.get('/{full_path:path}')
        async def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith('api/') or full_path.startswith('artifacts/') or full_path.startswith('assets/') or full_path.startswith('ws'):
                raise HTTPException(status_code=404, detail='Not found')
            return FileResponse(frontend_dist_path / 'index.html')
    else:
        @app.get('/')
        async def index() -> JSONResponse:
            return JSONResponse(
                {
                    'message': 'Inspection HMI Gateway is running.',
                    'hint': '前端源码已整合到 workspace/frontend，可执行 npm run dev:real 或 npm run build:real 后由网关静态托管。',
                }
            )

    return app
