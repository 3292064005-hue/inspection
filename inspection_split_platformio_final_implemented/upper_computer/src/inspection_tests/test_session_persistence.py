from __future__ import annotations

from datetime import UTC, datetime, timedelta
from inspection_hmi_gateway.server.auth import AuthService, hash_password, utc_now
from inspection_hmi_gateway.server.persistence import MetadataRepository
from inspection_utils.config import save_yaml


def _build_users_file(tmp_path):
    users_path = tmp_path / 'users.yaml'
    save_yaml(
        users_path,
        {
            'users': {
                'operator': {
                    'password_hash': hash_password('secret'),
                    'role': 'operator',
                    'display_name': '操作员',
                }
            }
        },
    )
    return users_path


def test_auth_service_resolves_persisted_session_after_restart(tmp_path) -> None:
    users_path = _build_users_file(tmp_path)
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=users_path)
    session = service.login(username='operator', password='secret')

    restarted = AuthService(repository, users_path=users_path)
    resolved = restarted.resolve(session['token'], touch=False)

    assert resolved is not None
    assert resolved['username'] == 'operator'
    assert resolved['token'] == session['token']


def test_resolve_touch_updates_repository_and_memory_cache(tmp_path) -> None:
    users_path = _build_users_file(tmp_path)
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=users_path)
    session = service.login(username='operator', password='secret')

    restarted = AuthService(repository, users_path=users_path)
    resolved = restarted.resolve(session['token'], touch=True)

    assert resolved is not None
    cached = restarted.sessions[session['token']]
    assert cached['lastSeenAt'] == resolved['lastSeenAt']
    persisted = repository.get_active_session(session['token'])
    assert persisted is not None
    assert persisted['lastSeenAt'] == resolved['lastSeenAt']


def test_resolve_expired_persisted_session_returns_none_and_revokes_it(tmp_path) -> None:
    users_path = _build_users_file(tmp_path)
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=users_path)
    session = service.login(username='operator', password='secret')

    expired = dict(session)
    expired['expiresAt'] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat(timespec='seconds').replace('+00:00', 'Z')
    expired['lastSeenAt'] = utc_now()
    repository.upsert_session(expired)

    restarted = AuthService(repository, users_path=users_path)
    assert restarted.resolve(session['token'], touch=False) is None
    assert repository.get_active_session(session['token']) is None



def test_metadata_repository_tolerates_malformed_action_job_payloads(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    with repository.connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO action_job(
                job_id, kind, status, progress, message, created_at, started_at, completed_at,
                requested_by, requested_role, cancellable, action_topic, action_type,
                payload_json, result_json, error_json, feedback_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'job-bad', 'replay', 'RUNNING', 'oops', 'bad row', '2026-01-01T00:00:00Z', '', '',
                'tester', 'admin', 'not-bool', '/inspection/actions/replay', 'ReplayAction',
                '{bad-json', '{still-bad', '{oops', '{feedback'
            ),
        )
    restored = repository.get_action_job('job-bad')
    assert restored is not None
    assert restored['progress'] == 0
    assert restored['cancellable'] is False
    assert restored['payload'] == {}
    assert restored['result'] == {}
    assert restored['error'] == {}
    assert restored['feedback'] == {}
