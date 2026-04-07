from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

try:
    from ament_index_python.packages import get_package_share_directory  # type: ignore
except Exception:  # pragma: no cover
    get_package_share_directory = None  # type: ignore

WORKSPACE_MARKERS = ('src', 'config', 'frontend')
_RUNTIME_ROOT_ENV = 'INSPECTION_RUNTIME_ROOT'
_STATE_HOME_ENV = 'XDG_STATE_HOME'
_ROS_HOME_ENV = 'ROS_HOME'


def _existing_candidates(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _origin_dir(start: str | os.PathLike | None = None) -> Path:
    origin = Path(start) if start is not None else Path(__file__).resolve()
    current = origin.resolve() if origin.exists() else origin.expanduser()
    return current if current.is_dir() else current.parent


def _is_workspace_root(candidate: Path) -> bool:
    return all((candidate / marker).exists() for marker in WORKSPACE_MARKERS)


def repo_root(start: str | os.PathLike | None = None) -> Path:
    """Locate the workspace root for development-mode relative paths.

    Args:
        start: Optional anchor file or directory used to begin the search.

    Returns:
        Workspace root when the repository markers are found. Falls back to the
        current working directory when running outside the checked-out workspace.
    """
    current = _origin_dir(start)
    for candidate in (current, *current.parents):
        if _is_workspace_root(candidate):
            return candidate
    return Path.cwd()


def package_share(package_name: str) -> Path | None:
    """Resolve the package share directory when the ROS ament index is available."""
    if get_package_share_directory is None:
        return None
    try:
        return Path(get_package_share_directory(package_name)).resolve()
    except Exception:
        return None


def resource_roots(*, package_name: str | None = None, start: str | os.PathLike | None = None) -> list[Path]:
    """Return candidate roots for read-only resources.

    The share directory is preferred for installed deployments. The repository
    root remains a fallback for source-workspace execution and tests.
    """
    roots: list[Path] = []
    if package_name:
        share = package_share(package_name)
        if share is not None:
            roots.append(share)
    workspace = repo_root(start)
    if _is_workspace_root(workspace):
        roots.append(workspace)
    origin_dir = _origin_dir(start)
    roots.append(origin_dir)
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def default_runtime_root(*, start: str | os.PathLike | None = None) -> Path:
    """Resolve the writable runtime root used for logs, state, and generated files.

    Args:
        start: Optional anchor used to detect whether the code is executing from a
            development workspace.

    Returns:
        Writable runtime root. Development workspaces default to the repository
        root so legacy relative paths like ``logs/runtime`` remain stable. When
        no workspace is detected, the path falls back to ``INSPECTION_RUNTIME_ROOT``,
        ``ROS_HOME/inspection``, or the XDG state directory.
    """
    override = os.environ.get(_RUNTIME_ROOT_ENV, '').strip()
    if override:
        return Path(override).expanduser()
    workspace = repo_root(start)
    if _is_workspace_root(workspace):
        return workspace
    ros_home = os.environ.get(_ROS_HOME_ENV, '').strip()
    if ros_home:
        return Path(ros_home).expanduser() / 'inspection'
    state_home = os.environ.get(_STATE_HOME_ENV, '').strip()
    if state_home:
        return Path(state_home).expanduser() / 'inspection'
    return Path.home() / '.local' / 'state' / 'inspection'


def resolve_resource_path(path: str | os.PathLike, *, package_name: str | None = None, start: str | os.PathLike | None = None) -> Path:
    """Resolve a read-only resource path without requiring the target to already exist.

    Args:
        path: Absolute or relative resource path.
        package_name: Optional ROS package used to search the installed share tree.
        start: Optional anchor file or directory.

    Returns:
        Absolute path to the preferred resource location. Existing matches are
        preferred; otherwise the path is projected under the first candidate root.
    """
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve() if candidate.exists() else candidate
    if candidate.exists():
        return candidate.resolve()
    roots = resource_roots(package_name=package_name, start=start)
    resolved = _existing_candidates(root / candidate for root in roots)
    if resolved is not None:
        return resolved
    return (roots[0] / candidate) if roots else candidate


def resolve_runtime_path(path: str | os.PathLike, *, start: str | os.PathLike | None = None) -> Path:
    """Resolve a writable runtime path for logs, caches, and generated artifacts.

    Args:
        path: Absolute or relative runtime path.
        start: Optional anchor file or directory used for development-workspace detection.

    Returns:
        Absolute runtime path. Relative paths are anchored under the resolved
        runtime root even when the target does not yet exist. Environment
        overrides such as ``INSPECTION_RUNTIME_ROOT`` take precedence over the
        development workspace fallback.
    """
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return default_runtime_root(start=start) / candidate


def resolve_workspace_path(path: str | os.PathLike, *, package_name: str | None = None, start: str | os.PathLike | None = None) -> Path:
    """Backward-compatible alias for resource-path resolution.

    Existing callers historically used this helper for read-only workspace paths.
    New runtime-state paths should use :func:`resolve_runtime_path` instead.
    """
    return resolve_resource_path(path, package_name=package_name, start=start)


_SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')


def sanitize_path_segment(value: str, *, default: str = 'item') -> str:
    raw = str(value or '').strip()
    cleaned = _SAFE_SEGMENT_RE.sub('_', raw).strip('._')
    return cleaned or default


def sanitize_trace_id(trace_id: str, *, item_id: int | None = None, default_prefix: str = 'TRACE') -> str:
    fallback = f'{default_prefix}-{int(item_id):05d}' if item_id is not None else default_prefix
    return sanitize_path_segment(trace_id or fallback, default=fallback)


def resolve_under_root(root: str | os.PathLike, relative_path: str | os.PathLike) -> Path:
    root_path = Path(root).resolve()
    target = (root_path / Path(relative_path)).resolve()
    if target != root_path and root_path not in target.parents:
        raise ValueError(f'Path escapes root: {relative_path}')
    return target


def resolve_log_artifact_path(log_root: str | os.PathLike, raw_path: str | os.PathLike) -> Path:
    """Resolve an artifact path while enforcing that it remains under the runtime log root.

    Args:
        log_root: Runtime log root used as the trust boundary for artifact access.
        raw_path: Absolute or relative artifact path persisted by runtime components.

    Returns:
        Resolved artifact path under ``log_root``. The returned path may point to a non-existent file.

    Raises:
        ValueError: If the artifact path is empty or escapes ``log_root``.
    """
    root_path = Path(log_root).resolve()
    candidate = Path(raw_path)
    if not str(candidate).strip():
        raise ValueError('Artifact path is empty.')
    if candidate.is_absolute():
        target = candidate.resolve()
        if target != root_path and root_path not in target.parents:
            raise ValueError(f'Artifact path is outside log root: {raw_path}')
        return target
    return resolve_under_root(root_path, candidate)


def relative_artifact_path(log_root: str | os.PathLike, absolute_or_relative: str | os.PathLike) -> str:
    log_root_path = Path(log_root).resolve()
    candidate = Path(absolute_or_relative)
    target = candidate.resolve() if candidate.is_absolute() else (log_root_path / candidate).resolve()
    if target != log_root_path and log_root_path not in target.parents:
        raise ValueError(f'Artifact path is outside log root: {absolute_or_relative}')
    return target.relative_to(log_root_path).as_posix()
