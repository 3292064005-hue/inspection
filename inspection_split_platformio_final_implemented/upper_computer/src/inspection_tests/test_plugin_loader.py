from importlib import metadata
from vision_processing.detectors import ColorDetector
from vision_processing.pipeline.detector_registry import DetectorRegistry
from vision_processing.plugins.plugin_loader import discover_detector_entry_points, load_manifest_plugins


class DummyDetector:
    pass


def test_load_manifest_plugins_loads_factory_from_module():
    plugins = load_manifest_plugins([{'name': 'dummy', 'factory': 'vision_processing.detectors:ColorDetector'}])
    assert plugins['dummy'] is ColorDetector


def test_discover_detector_entry_points_supports_select_api(monkeypatch):
    class FakeEntryPoint:
        def __init__(self, name, factory):
            self.name = name
            self._factory = factory

        def load(self):
            return self._factory

    class FakeSelectable(list):
        def select(self, *, group):
            assert group == 'inspection.vision_detectors'
            return self

    monkeypatch.setattr(metadata, 'entry_points', lambda: FakeSelectable([FakeEntryPoint('dummy_ep', DummyDetector)]))
    discovered = discover_detector_entry_points()
    assert discovered['dummy_ep'] is DummyDetector


def test_detector_registry_can_discover_manifest_plugins():
    registry = DetectorRegistry()
    registry.discover(manifest=[{'name': 'dummy', 'factory': 'vision_processing.detectors:ColorDetector'}])
    instance = registry.create('dummy')
    assert isinstance(instance, ColorDetector)
