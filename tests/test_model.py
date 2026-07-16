import pytest

from usb4431_monitor.model import AcquisitionConfig, window_bounds, window_sample_count


@pytest.mark.parametrize(
    ("rate", "start", "end", "expected"),
    [
        (10_000, 0.0, 0.1, 1_000),
        (10_000, 0.02, 0.12, 1_000),
        (1_000, 0.0005, 0.0035, 3),
        (102_400, 0.0, 0.001, 102),
    ],
)
def test_window_sample_count_uses_open_closed_interval(rate, start, end, expected):
    assert window_sample_count(rate, start, end) == expected


def test_zero_start_begins_after_trigger_sample():
    assert window_bounds(37, 10_000, 0.0, 0.001) == (38, 47)


@pytest.mark.parametrize("rate", [999, 102_401])
def test_rate_limits(rate):
    with pytest.raises(ValueError, match="采样率"):
        AcquisitionConfig(requested_sample_rate_hz=rate).validate()


def test_ui_unit_conversion():
    config = AcquisitionConfig.from_ui({"window_unit": "s", "window_start": 0.02, "window_end": 0.12})
    assert config.window_start_s == pytest.approx(0.02)
    assert config.window_end_s == pytest.approx(0.12)

