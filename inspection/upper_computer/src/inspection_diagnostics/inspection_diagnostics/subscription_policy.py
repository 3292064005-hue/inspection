from __future__ import annotations


def diagnostics_subscription_policy(enable_annotated_image_diagnostics: bool) -> dict[str, bool]:
    """Return the diagnostics-topic subscription policy.

    The annotated-image stream is disabled by default so the diagnostics node
    does not add an always-on high-bandwidth consumer unless the operator
    explicitly enables it.
    """
    return {
        'camera_status': True,
        'result_raw': True,
        'annotated_image': bool(enable_annotated_image_diagnostics),
    }
