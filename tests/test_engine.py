from datetime import datetime, timezone

import numpy as np
import pytest

from usb4431_monitor.engine import TriggerWindowProcessor
from usb4431_monitor.model import AcquisitionConfig


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def processor(*, start=0.0, end=0.002, min_interval=0.0):
    config = AcquisitionConfig(
        trigger_channel=3,
        requested_sample_rate_hz=1_000,
        window_start_s=start,
        window_end_s=end,
        min_trigger_interval_s=min_interval,
    )
    return TriggerWindowProcessor(config, 1_000, "run-test", START)


def block(indices, trigger):
    indices = np.asarray(indices, dtype=np.float64)
    return np.vstack((indices, indices + 100, indices - 100, np.asarray(trigger, dtype=np.float64)))


def test_trigger_sample_is_excluded_when_start_is_zero():
    engine = processor(end=0.002)
    results = engine.process(block(range(5), [0, 5, 0, 0, 0]))
    assert len(results) == 1
    result = results[0]
    assert result["trigger_sample_index"] == 1
    assert result["sample_count"] == 2
    assert result["ai0_mean_V"] == pytest.approx((2 + 3) / 2)
    assert result["ai1_mean_V"] == pytest.approx((102 + 103) / 2)


def test_open_closed_boundaries_with_nonzero_start():
    engine = processor(start=0.002, end=0.005)
    results = engine.process(block(range(8), [0, 5, 0, 0, 0, 0, 0, 0]))
    result = results[0]
    # Trigger index 1: (2 ms, 5 ms] selects absolute indices 4, 5, 6.
    assert result["sample_count"] == 3
    assert result["ai0_mean_V"] == pytest.approx(5.0)


def test_window_accumulates_across_blocks():
    engine = processor(end=0.004)
    assert engine.process(block(range(3), [0, 5, 0])) == []
    results = engine.process(block(range(3, 7), [0, 0, 0, 0]))
    assert len(results) == 1
    assert results[0]["sample_count"] == 4
    assert results[0]["ai0_mean_V"] == pytest.approx(3.5)


def test_multiple_overlapping_windows_share_samples():
    engine = processor(end=0.005)
    data = block(range(10), [0, 5, 0, 5, 0, 0, 0, 0, 0, 0])
    results = engine.process(data)
    assert [item["trigger_sample_index"] for item in results] == [1, 3]
    assert [item["sample_count"] for item in results] == [5, 5]
    assert results[0]["ai0_mean_V"] == pytest.approx(4.0)  # indices 2..6
    assert results[1]["ai0_mean_V"] == pytest.approx(6.0)  # indices 4..8


def test_starting_high_does_not_trigger_until_rearmed_low():
    engine = processor(end=0.002)
    results = engine.process(block(range(7), [5, 5, 0, 5, 0, 0, 0]))
    assert len(results) == 1
    assert results[0]["trigger_sample_index"] == 3


def test_hysteresis_requires_fall_below_rearm_level():
    engine = processor(end=0.001)
    trigger = [0, 5, 2.4, 5, 2.3, 5, 0]
    results = engine.process(block(range(len(trigger)), trigger))
    assert [item["trigger_sample_index"] for item in results] == [1, 5]


def test_minimum_trigger_interval_filters_close_crossings():
    engine = processor(end=0.001, min_interval=0.004)
    trigger = [0, 5, 0, 5, 0, 5, 0, 0]
    results = engine.process(block(range(len(trigger)), trigger))
    assert [item["trigger_sample_index"] for item in results] == [1, 5]


def test_stop_accepting_finishes_existing_window_only():
    engine = processor(end=0.004)
    assert engine.process(block(range(3), [0, 5, 0])) == []
    engine.stop_accepting_triggers()
    results = engine.process(block(range(3, 8), [5, 0, 0, 0, 0]))
    assert len(results) == 1
    assert results[0]["trigger_sample_index"] == 1
    assert engine.pending == []


def test_all_channels_use_identical_sample_count_and_range():
    engine = processor(end=0.003)
    results = engine.process(block(range(6), [0, 5, 1, 2, 3, 0]))
    result = results[0]
    assert result["sample_count"] == 3
    assert result["ai0_mean_V"] == pytest.approx(3.0)
    assert result["ai1_mean_V"] == pytest.approx(103.0)
    assert result["ai2_mean_V"] == pytest.approx(-97.0)
    assert result["ai3_mean_V"] == pytest.approx(2.0)

