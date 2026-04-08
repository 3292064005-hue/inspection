from pathlib import Path


def test_bringup_setup_packages_workspace_config_and_docs() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'setup.py').read_text(encoding='utf-8')
    assert "collect_files('config', anchor=WORKSPACE_ROOT)" in text
    assert "collect_files('docs', anchor=WORKSPACE_ROOT)" in text


def test_validate_workspace_uses_layered_backend_steps() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'validate_workspace.sh').read_text(encoding='utf-8')
    assert 'Backend required tests' in text
    assert 'run_backend_required_tests.sh' in text
    assert 'Backend coverage report' in text
    assert 'run_backend_coverage_report.sh' in text
    assert 'ROS runtime validation' in text
    assert 'run_ros2_humble_runtime_validation.sh' in text


def test_gateway_registration_and_websocket_failures_are_logged() -> None:
    root = Path(__file__).resolve().parents[2]
    context_text = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'context.py').read_text(encoding='utf-8')
    transport_text = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'websocket_transport.py').read_text(encoding='utf-8')
    assert 'ACTION_JOB_REGISTRATION_FAILED' in context_text
    assert 'LOGGER.exception' in context_text
    assert 'WebSocket session failed.' in transport_text
    assert 'LOGGER.exception' in transport_text


def test_ci_workflow_contains_dedicated_ros_release_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert 'ros_release_gate:' in text
    assert 'ros:humble-ros-base' in text
    assert "ENABLE_ROS_RELEASE_GATE: '1'" in text
    assert 'validate_ros_workspace.sh' in text
    assert 'run_ros2_humble_runtime_validation.sh' in text


def test_frontend_playwright_smoke_uses_dedicated_runner() -> None:
    root = Path(__file__).resolve().parents[2]
    validate_text = (root / 'scripts' / 'validate_workspace.sh').read_text(encoding='utf-8')
    runner_text = (root / 'scripts' / 'run_frontend_e2e.sh').read_text(encoding='utf-8')
    assert 'run_frontend_e2e.sh' in validate_text
    assert 'PLAYWRIGHT_CHROMIUM_EXECUTABLE' in runner_text
    assert 'npm --prefix "$FRONTEND_DIR" run e2e' in runner_text


def test_ros_release_gate_builds_frontend_assets_before_colcon() -> None:
    root = Path(__file__).resolve().parents[2]
    ci_text = (root / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    ros_text = (root / 'scripts' / 'validate_ros_workspace.sh').read_text(encoding='utf-8')
    assert 'Build frontend release assets' in ci_text
    assert 'ros_release_gate_preflight.py' in ros_text
    assert '--require-colcon --require-frontend-dist' in ros_text
    assert 'INSPECTION_REQUIRE_FRONTEND_DIST=1' in ros_text
    assert 'ros_release_preflight.json' in ros_text

def test_verification_report_includes_status_source_and_metadata() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'write_verification_report.py').read_text(encoding='utf-8')
    assert 'statusSource' in text
    assert 'buildMetadata' in text

def test_python_syntax_check_covers_scripts_directory() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'check_python_syntax.py').read_text(encoding='utf-8')
    assert "pathlib.Path('scripts').rglob('*.py')" in text

def test_verification_report_handles_absolute_logs_outside_workspace() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'write_verification_report.py').read_text(encoding='utf-8')
    assert 'ROOT in log_path.parents' in text

def test_verification_report_handles_status_file_outside_workspace() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'write_verification_report.py').read_text(encoding='utf-8')
    assert 'status_path.is_absolute() and ROOT in status_path.parents' in text


def test_generated_verification_outputs_live_under_artifacts_directory() -> None:
    root = Path(__file__).resolve().parents[2]
    coverage_text = (root / 'scripts' / 'run_backend_coverage_report.sh').read_text(encoding='utf-8')
    ros_text = (root / 'scripts' / 'validate_ros_workspace.sh').read_text(encoding='utf-8')
    asset_manifest = (root / 'docs' / 'REPOSITORY_ASSET_STATUS.md').read_text(encoding='utf-8')
    assert 'ARTIFACT_DIR="$ROOT_DIR/.artifacts/verification"' in coverage_text
    assert 'backend_coverage.json' in coverage_text
    assert 'ARTIFACT_DIR="$ROOT_DIR/.artifacts/verification"' in ros_text
    assert 'LOG_DIR="$ARTIFACT_DIR/logs"' in ros_text
    assert '.artifacts/verification/backend_coverage.json' in asset_manifest


def test_historical_verification_reports_are_not_kept_under_docs() -> None:
    root = Path(__file__).resolve().parents[2]
    assert not (root / 'docs' / 'FINAL_VERIFICATION.md').exists()
    assert not (root / 'docs' / 'FINAL_VERIFICATION.json').exists()
    assert not (root / 'docs' / 'backend_coverage.json').exists()
    assert not (root / 'docs' / 'validation_logs').exists()


def test_frontend_package_uses_repo_local_vitest_entrypoint() -> None:
    root = Path(__file__).resolve().parents[2]
    package_text = (root / 'frontend' / 'package.json').read_text(encoding='utf-8')
    assert 'node ./node_modules/vitest/vitest.mjs --run --pool=forks --poolOptions.forks.singleFork=true' in package_text
    assert 'node ./node_modules/vitest/vitest.mjs --run --coverage' in package_text


def test_ros_release_gate_preflight_is_shared_by_build_and_runtime_gates() -> None:
    root = Path(__file__).resolve().parents[2]
    preflight_text = (root / 'scripts' / 'ros_release_gate_preflight.py').read_text(encoding='utf-8')
    ros_gate_text = (root / 'scripts' / 'validate_ros_workspace.sh').read_text(encoding='utf-8')
    runtime_text = (root / 'scripts' / 'run_ros2_humble_runtime_validation.sh').read_text(encoding='utf-8')
    readme_text = (root / 'README.md').read_text(encoding='utf-8')
    assert "VERSION_ID={version or 'unknown'}; expected ubuntu 22.04" in preflight_text
    assert 'expected 20 or 22 LTS' in preflight_text
    assert '--require-colcon --require-frontend-dist' in ros_gate_text
    assert '--require-frontend-dist --require-install-setup' in runtime_text
    assert 'ros_release_gate_preflight.py' in readme_text
    assert 'ros_release_preflight.json' in ros_gate_text
    assert 'ros_runtime_preflight.json' in runtime_text


def test_backend_required_tests_include_syntax_and_import_smoke_preflight() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'run_backend_required_tests.sh').read_text(encoding='utf-8')
    assert 'check_python_syntax.py' in text
    assert 'run_backend_import_smoke_tests.sh' in text


def test_verification_report_emits_manifest_source_of_truth() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'write_verification_report.py').read_text(encoding='utf-8')
    assert 'verification_manifest.json' in text
    assert 'sourceOfTruth' in text


def test_backend_release_gate_reuses_required_and_runtime_preflight() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'run_backend_release_gate.sh').read_text(encoding='utf-8')
    assert 'run_backend_required_tests.sh' in text
    assert 'run_backend_runtime_smoke_tests.sh' in text
    assert 'python3 -m pytest src/inspection_tests' in text


def test_interfaces_package_builds_typed_transport_messages() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_interfaces' / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'msg/ControlCommand.msg' in text
    assert 'msg/CaptureRequest.msg' in text
    assert 'msg/DiagnosticsSnapshot.msg' in text
    assert 'msg/SupervisorStateEnvelope.msg' in text
    assert 'msg/ActionExecutorEvent.msg' in text


def test_ros_packages_declare_typed_interface_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    supervisor = (root / 'src' / 'inspection_supervisor' / 'package.xml').read_text(encoding='utf-8')
    orchestrator = (root / 'src' / 'inspection_orchestrator' / 'package.xml').read_text(encoding='utf-8')
    gateway_setup = (root / 'src' / 'inspection_hmi_gateway' / 'setup.py').read_text(encoding='utf-8')
    assert '<exec_depend>inspection_interfaces</exec_depend>' in supervisor
    assert '<exec_depend>inspection_interfaces</exec_depend>' in orchestrator
    assert "'inspection_interfaces'" in gateway_setup


def test_ros_release_gate_requires_typed_interface_import_smoke() -> None:
    root = Path(__file__).resolve().parents[2]
    validate = (root / 'scripts' / 'validate_ros_workspace.sh').read_text(encoding='utf-8')
    runtime = (root / 'scripts' / 'run_ros2_humble_runtime_validation.sh').read_text(encoding='utf-8')
    assert 'run_ros_typed_interface_import_smoke.sh' in validate
    assert 'INSPECTION_REQUIRE_TYPED_INTERFACES=1' in validate
    assert 'run_ros_typed_interface_import_smoke.sh' in runtime
    assert 'INSPECTION_REQUIRE_TYPED_INTERFACES=1' in runtime


def test_verification_manifest_tracks_provenance_completeness() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'scripts' / 'write_verification_report.py').read_text(encoding='utf-8')
    assert 'provenanceComplete' in text
    assert 'STRICT_VERIFICATION_PROVENANCE' in text


def test_read_model_defaults_fail_closed_projection_reads() -> None:
    root = Path(__file__).resolve().parents[2]
    config = (root / 'config' / 'system' / 'read_model.yaml').read_text(encoding='utf-8')
    policy = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'read_model_policy.py').read_text(encoding='utf-8')
    assert 'fallback_legacy_reads: false' in config
    assert 'query_side_trace_refresh: disabled' in config
    assert 'fallback_legacy_reads: bool = False' in policy
    assert 'query_side_trace_refresh: str = READ_MODEL_QUERY_REFRESH_DISABLED' in policy


def test_results_router_exposes_read_model_status_and_repair_endpoints() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'results.py').read_text(encoding='utf-8')
    assert "/results/read-model/status" in text
    assert "/results/read-model/repair" in text
    assert 'ReadModelSyncRequiredError' in text
    assert 'status_code=503' in text


def test_diagnostics_node_enforces_typed_interface_availability_in_strict_mode() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_diagnostics' / 'inspection_diagnostics' / 'diagnostics_node.py').read_text(encoding='utf-8')
    assert 'assert_typed_interfaces_available' in text
    assert "consumer='inspection_diagnostics_node'" in text


def test_bringup_entrypoints_use_package_module_builder_and_absolute_offline_replay_defaults() -> None:
    root = Path(__file__).resolve().parents[2]
    full_stack = (root / 'src' / 'inspection_bringup' / 'launch' / 'full_stack.launch.py').read_text(encoding='utf-8')
    sim_stack = (root / 'src' / 'inspection_bringup' / 'launch' / 'sim_stack.launch.py').read_text(encoding='utf-8')
    offline_replay = (root / 'src' / 'inspection_bringup' / 'launch' / 'offline_replay.launch.py').read_text(encoding='utf-8')
    runtime_launch = (root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'runtime_launch_config.py').read_text(encoding='utf-8')
    package_xml = (root / 'src' / 'inspection_bringup' / 'package.xml').read_text(encoding='utf-8')
    assert 'from inspection_bringup.sim_stack_common import build_simulated_stack' in full_stack
    assert 'from inspection_bringup.sim_stack_common import build_simulated_stack' in sim_stack
    assert 'build_launch_runtime_payload' in offline_replay
    assert 'station_config_path' in offline_replay
    assert 'managed_runtime_enabled' in offline_replay
    assert 'get_package_share_directory' in offline_replay
    assert "resolve_resource_path(str(Path('config/profiles') / f'{profile_name}.yaml')" in runtime_launch
    assert '<exec_depend>ament_index_python</exec_depend>' in package_xml
