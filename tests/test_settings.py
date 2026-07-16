import json

import pytest

from usb4431_monitor.model import AcquisitionConfig
from usb4431_monitor.settings import SettingsStore
from usb4431_monitor.sources import is_resource_reserved_error
from usb4431_monitor.worker import _parent_is_alive


def test_settings_round_trip_preserves_ui_unit_and_values(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    raw = {
        "mode": "hardware",
        "device": "USB4431",
        "trigger_channel": 2,
        "trigger_threshold_v": 3.1,
        "trigger_hysteresis_v": 0.3,
        "min_trigger_interval_ms": 150,
        "sample_rate_hz": 51_200,
        "window_unit": "s",
        "window_start": 0.02,
        "window_end": 0.12,
        "simulation_trigger_period_ms": 400,
        "simulation_realtime": False,
    }
    saved = store.save(raw)
    loaded, warning = store.load()
    assert warning is None
    assert loaded == saved
    assert loaded["window_unit"] == "s"
    assert loaded["window_start"] == pytest.approx(0.02)
    assert loaded["window_end"] == pytest.approx(0.12)


def test_missing_settings_uses_builtin_defaults(tmp_path):
    loaded, warning = SettingsStore(tmp_path / "missing.json").load()
    assert warning is None
    assert loaded == AcquisitionConfig().to_ui()


def test_invalid_settings_uses_builtin_defaults_with_warning(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"sample_rate_hz": 10}), encoding="utf-8")
    loaded, warning = SettingsStore(path).load()
    assert loaded == AcquisitionConfig().to_ui()
    assert warning is not None


def test_resource_reserved_error_recognizes_code_and_message():
    class CodedError(Exception):
        error_code = -50103

    assert is_resource_reserved_error(CodedError())
    assert is_resource_reserved_error(RuntimeError("Status Code: -50103"))
    assert not is_resource_reserved_error(RuntimeError("other"))


def test_parent_liveness_handles_dead_and_invalid_parent():
    class Parent:
        def __init__(self, alive):
            self.alive = alive

        def is_alive(self):
            if self.alive == "error":
                raise ValueError("closed")
            return self.alive

    assert _parent_is_alive(None)
    assert _parent_is_alive(Parent(True))
    assert not _parent_is_alive(Parent(False))
    assert not _parent_is_alive(Parent("error"))

