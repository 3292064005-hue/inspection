from inspection_decision.rules import decision_rule_manifest_catalog
from vision_acquisition.provider_registry import provider_manifest_catalog
from vision_processing.detectors import REGISTRY as DETECTOR_REGISTRY


def test_plugin_manifests_expose_owner_plane_and_promotion_path() -> None:
    providers = provider_manifest_catalog()
    detectors = DETECTOR_REGISTRY.manifest_catalog()
    decision_rules = decision_rule_manifest_catalog()
    for manifest in providers + detectors + decision_rules:
        assert str(manifest.get('ownerPlane', '')).strip()
        assert isinstance(manifest.get('promotionPath', []), list)
        assert manifest['promotionPath']
        assert isinstance(manifest.get('verificationRequirements', []), list)


def test_builtin_real_plugins_define_verification_requirements() -> None:
    providers = {item['name']: item for item in provider_manifest_catalog()}
    detectors = {item['name']: item for item in DETECTOR_REGISTRY.manifest_catalog()}
    assert 'snapshot_capture_success' in providers['esp32_http']['verificationRequirements']
    assert 'camera_health_endpoint_ready' in providers['opencv']['verificationRequirements']
    assert 'capture_process_decision_cycle' in detectors['color']['verificationRequirements']
