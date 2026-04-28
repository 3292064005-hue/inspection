from __future__ import annotations

import ast
import json
from pathlib import Path

from inspection_hmi_gateway.read_model_repository import ReadModelRepository, ReadModelSyncRequiredError
from inspection_hmi_gateway.result_store import ResultStore


REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_module(relative_path: str) -> ast.Module:
    return ast.parse((REPO_ROOT / relative_path).read_text(encoding='utf-8'))


def _class_methods(module: ast.Module, class_name: str) -> set[str]:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    raise AssertionError(f'class {class_name} not found')


def _module_level_functions(module: ast.Module) -> set[str]:
    return {node.name for node in module.body if isinstance(node, ast.FunctionDef)}


def test_vision_processor_callbacks_are_class_methods() -> None:
    module = _parse_module('src/vision_processing/vision_processing/processor_node.py')
    methods = _class_methods(module, 'VisionProcessorNode')
    module_functions = _module_level_functions(module)

    expected = {
        'on_capture_request',
        'on_typed_capture_request',
        '_build_output_name',
        '_close_artifact_writer',
        '_empty_writer_snapshot',
        '_persist_artifact',
        '_process_bound',
    }
    assert expected.issubset(methods)
    assert expected.isdisjoint(module_functions)


def test_logger_callbacks_are_class_methods() -> None:
    module = _parse_module('src/inspection_logger/inspection_logger/logger_node.py')
    methods = _class_methods(module, 'LoggerNode')
    module_functions = _module_level_functions(module)

    expected = {
        'on_capture_request',
        'on_typed_capture_request',
        'on_result',
        'on_decision_output',
        'on_sort_request',
        'on_stats',
        'on_fault',
        'on_station',
    }
    assert expected.issubset(methods)
    assert expected.isdisjoint(module_functions)


def test_fsm_runtime_callbacks_and_services_are_class_methods() -> None:
    module = _parse_module('src/inspection_fsm/inspection_fsm/fsm_node.py')
    methods = _class_methods(module, 'FSMNode')
    module_functions = _module_level_functions(module)

    expected = {
        'on_station_state',
        'on_result',
        'on_decision_output',
        'on_event_message',
        'on_control_message',
        'on_typed_control_message',
        'on_start',
        'on_reset_fault',
    }
    assert expected.issubset(methods)
    assert expected.isdisjoint(module_functions)


def test_station_bridge_runtime_callbacks_are_class_methods() -> None:
    module = _parse_module('src/station_bridge/station_bridge/station_bridge_node.py')
    methods = _class_methods(module, 'StationBridgeNode')
    module_functions = _module_level_functions(module)

    expected = {
        'on_feed_request',
        'on_sort_request',
        'on_reset_request',
    }
    assert expected.issubset(methods)
    assert expected.isdisjoint(module_functions)


def _prepare_runtime_logs(root: Path) -> None:
    results = root / 'results'
    traces = root / 'traces'
    results.mkdir(parents=True, exist_ok=True)
    traces.mkdir(parents=True, exist_ok=True)
    (results / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-04-01T08:00:00Z,TRACE-CACHE,BATCH-1,1,recipe-a,OK,NONE,0.99,1,QR-1,1,red,0.8,images/raw.png,images/ann.png,"{\"\"trace_id\"\": \"\"TRACE-CACHE\"\"}"\n',
        encoding='utf-8',
    )
    (results / 'cycle_summary.jsonl').write_text(json.dumps({'trace_id': 'TRACE-CACHE', 'decision': 'OK', 'cycle_time_sec': 0.1}) + '\n', encoding='utf-8')
    (results / 'replay_manifest.jsonl').write_text(json.dumps({'trace_id': 'TRACE-CACHE'}) + '\n', encoding='utf-8')
    (results / 'artifact_index.jsonl').write_text('', encoding='utf-8')
    (traces / 'TRACE-CACHE.jsonl').write_text(json.dumps({'type': 'capture_request', 'trace_id': 'TRACE-CACHE'}) + '\n', encoding='utf-8')


def test_read_model_repository_uses_cached_sync_state_without_trace_scan(tmp_path: Path) -> None:
    runtime = tmp_path / 'runtime'
    _prepare_runtime_logs(runtime)

    repository = ReadModelRepository(runtime)
    repository.repair()

    def fail_trace_scan() -> str:
        raise AssertionError('trace scan should not be needed once sync state is present')

    repository._trace_token = fail_trace_scan  # type: ignore[method-assign]
    rows = repository.list_results()
    assert len(rows) == 1
    assert rows[0]['traceId'] == 'TRACE-CACHE'


def test_result_store_detail_requires_explicit_repair_after_trace_changes(tmp_path: Path) -> None:
    runtime = tmp_path / 'runtime'
    _prepare_runtime_logs(runtime)
    trace_path = runtime / 'traces' / 'TRACE-CACHE.jsonl'

    store = ResultStore(runtime)
    detail = store.get_result('TRACE-CACHE')
    assert detail is not None
    assert int(detail['traceBundle']['eventCount']) == 1

    trace_path.write_text(
        json.dumps({'type': 'capture_request', 'trace_id': 'TRACE-CACHE'}) + '\n' + json.dumps({'type': 'inspection_result', 'trace_id': 'TRACE-CACHE'}) + '\n',
        encoding='utf-8',
    )

    try:
        store.get_result('TRACE-CACHE')
    except ReadModelSyncRequiredError:
        pass
    else:
        raise AssertionError('trace changes must require explicit repair')

    store.repair_read_model()
    refreshed = store.get_result('TRACE-CACHE')
    assert refreshed is not None
    assert int(refreshed['traceBundle']['eventCount']) == 2


def test_read_model_repository_detects_structured_source_file_changes_after_cached_repair(tmp_path: Path) -> None:
    runtime = tmp_path / 'runtime'
    _prepare_runtime_logs(runtime)

    repository = ReadModelRepository(runtime)
    repository.repair()

    result_csv = runtime / 'results' / 'result_log.csv'
    result_csv.write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-04-01T08:00:00Z,TRACE-CACHE,BATCH-1,1,recipe-a,OK,NONE,0.99,1,QR-1,1,red,0.8,images/raw.png,images/ann.png,"{\"trace_id\": \"TRACE-CACHE\"}"\n'
        '2026-04-01T08:05:00Z,TRACE-NEW,BATCH-2,2,recipe-b,NG,DEFECT,0.20,0,QR-2,0,blue,0.2,images/raw2.png,images/ann2.png,"{\"trace_id\": \"TRACE-NEW\"}"\n',
        encoding='utf-8',
    )

    readiness = repository.readiness()
    assert readiness['stale'] is True


def test_result_store_requires_explicit_repair_for_projection_field_updates(tmp_path: Path) -> None:
    runtime = tmp_path / 'runtime'
    _prepare_runtime_logs(runtime)
    artifact_index = runtime / 'results' / 'artifact_index.jsonl'
    trace_path = runtime / 'traces' / 'TRACE-CACHE.jsonl'

    store = ResultStore(runtime)
    detail = store.get_result('TRACE-CACHE')
    assert detail is not None
    baseline_artifact_count = int(detail['artifactCount'])

    artifact_index.write_text(json.dumps({
        'trace_id': 'TRACE-CACHE',
        'kind': 'annotated_image',
        'path': 'images/annotated/cache.png',
        'batch_id': 'BATCH-1',
        'item_id': 1,
        'source': 'vision_processor',
    }) + '\n', encoding='utf-8')
    trace_path.write_text(
        json.dumps({'type': 'capture_request', 'trace_id': 'TRACE-CACHE'}) + '\n'
        + json.dumps({'type': 'artifact_recorded', 'trace_id': 'TRACE-CACHE'}) + '\n',
        encoding='utf-8',
    )

    try:
        store.get_result('TRACE-CACHE')
    except ReadModelSyncRequiredError:
        pass
    else:
        raise AssertionError('projection field changes must require explicit repair')

    store.repair_read_model()
    refreshed = store.get_result('TRACE-CACHE')
    assert refreshed is not None
    assert int(refreshed['artifactCount']) >= baseline_artifact_count + 1
    assert int(refreshed['traceBundle']['artifactCount']) >= baseline_artifact_count + 1


def test_fsm_start_and_reset_services_guard_inactive_managed_runtime() -> None:
    text = (REPO_ROOT / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_node.py').read_text(encoding='utf-8')
    assert "if self._runtime_service_blocked('/inspection/start'):" in text
    assert "if self._runtime_service_blocked('/inspection/reset_fault'):" in text
    assert "response.message = 'runtime is not active'" in text
