from __future__ import annotations

from pathlib import Path

from inspection_hmi_gateway.action_execution_runtime import ActionExecutionRuntime


class _Metadata:
    def __init__(self):
        self.export_jobs = []
    def record_export_job(self, payload):
        self.export_jobs.append(dict(payload))


class _Node:
    def __init__(self):
        self.commands = []
        self.recipe_store = type('RecipeStore', (), {'load_by_id': lambda self, recipe_id: {'id': recipe_id}, 'activate': lambda self, recipe_id, operator: {'recipeId': recipe_id, 'operator': operator}})()
    def new_batch(self):
        return 'B-NEW'
    def call_start(self, *args, **kwargs):
        return True, 'started'
    def publish_control(self, command):
        self.commands.append(command)
    def reset_fault(self):
        return True, 'reset'
    def refresh_recipes(self):
        return None


class _Replay:
    def get_trace(self, trace_id):
        return {'traceId': trace_id, 'status': 'READY'}
    def compare_trace(self, trace_id):
        return {'traceId': trace_id, 'match': True}


class _ExportArtifacts:
    def __init__(self, path: Path):
        self.export_path = path
        self.item_count = 1
        self.trace_count = 1


class _Export:
    def __init__(self, root: Path):
        self.root = root
    def export_batch(self, batch_id):
        path = self.root / 'exports' / f'{batch_id}.zip'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('zip', encoding='utf-8')
        return _ExportArtifacts(path)


class _Context:
    def __init__(self, root: Path):
        self.log_root = root
        self.metadata_repository = _Metadata()
        self._node = _Node()
        self._replay = _Replay()
        self._export = _Export(root)
        self.audits = []
    def node(self):
        return self._node
    def replay_service(self):
        return self._replay
    def export_service(self):
        return self._export
    def audit(self, **payload):
        self.audits.append(payload)


def test_action_execution_runtime_runs_export_independently(tmp_path: Path) -> None:
    context = _Context(tmp_path)
    runtime = ActionExecutionRuntime(context, max_workers=1)
    updates = []

    def update(job_id, **fields):
        updates.append((job_id, fields))

    runtime.submit('job-1', 'export_batch', payload={'batchId': 'B-1'}, actor={'username': 'operator', 'role': 'operator'}, update=update)
    runtime.executor.shutdown(wait=True)
    assert any(fields.get('status') == 'COMPLETED' for _, fields in updates)
    assert context.metadata_repository.export_jobs
