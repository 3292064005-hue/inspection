from inspection_hmi_gateway.read_model_policy import ReadModelPolicyError, load_read_model_policy


def test_read_model_policy_rejects_online_legacy_fallback(monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_READ_MODEL_FALLBACK_LEGACY_READS', '1')
    try:
        load_read_model_policy()
    except ReadModelPolicyError as exc:
        assert 'Online legacy read fallback has been removed' in str(exc)
    else:
        raise AssertionError('expected ReadModelPolicyError')
