from inspection_hmi_gateway.projection_boundary import projection_boundary_catalog
from inspection_hmi_gateway.result_store import ResultStore


def test_projection_boundary_catalog_describes_runtime_and_query_owners() -> None:
    catalog = projection_boundary_catalog()
    assert catalog['runtime']['owner'] == 'inspection_hmi_gateway.runtime_projection'
    assert catalog['query']['owner'] == 'inspection_logger.read_model_writer'
    assert catalog['runtime']['querySurface'] == 'websocket_runtime_snapshot'
    assert catalog['query']['repairStrategy'] == 'explicit_read_model_repair'


def test_result_store_status_exposes_projection_boundary_metadata(tmp_path) -> None:
    store = ResultStore(log_root=tmp_path)
    status = store.read_model_status(refresh=False)
    assert 'projectionBoundaries' in status
    assert status['projectionBoundaries']['runtime']['owner'] == 'inspection_hmi_gateway.runtime_projection'
    assert status['projectionBoundaries']['query']['querySurface'] == 'http_query_projection'
