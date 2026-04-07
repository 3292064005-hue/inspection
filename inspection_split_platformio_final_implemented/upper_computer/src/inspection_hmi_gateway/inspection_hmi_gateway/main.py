from __future__ import annotations

import os
import uvicorn

from .app import create_app


def main() -> None:
    host = os.environ.get('INSPECTION_HMI_HOST', '0.0.0.0')
    port = int(os.environ.get('INSPECTION_HMI_PORT', '8080'))
    log_root = os.environ.get('INSPECTION_HMI_LOG_ROOT', 'logs/runtime')
    recipe_root = os.environ.get('INSPECTION_HMI_RECIPE_ROOT', 'config/recipes')
    frontend_dist = os.environ.get('INSPECTION_HMI_FRONTEND_DIST', 'frontend/dist')
    users_path = os.environ.get('INSPECTION_HMI_USERS_PATH', 'config/system/hmi_users.yaml')
    strict_frontend = os.environ.get('INSPECTION_HMI_REQUIRE_FRONTEND_DIST', '').strip()
    app = create_app(log_root=log_root, recipe_root=recipe_root, frontend_dist=frontend_dist, users_path=users_path, require_frontend_dist=(None if not strict_frontend else strict_frontend.lower() in {'1', 'true', 'yes', 'on'}))
    uvicorn.run(app, host=host, port=port)
