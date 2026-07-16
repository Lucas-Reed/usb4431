import time

from usb4431_monitor.controller import AppController


def test_simulation_process_starts_produces_results_and_drains():
    controller = AppController()
    result = controller.start(
        {
            "mode": "simulation",
            "sample_rate_hz": 1_000,
            "window_unit": "ms",
            "window_start": 0,
            "window_end": 10,
            "min_trigger_interval_ms": 20,
            "simulation_trigger_period_ms": 50,
            "simulation_realtime": True,
        }
    )
    assert result["ok"] is True
    deadline = time.monotonic() + 2
    while controller.get_state()["completed_count"] == 0 and time.monotonic() < deadline:
        time.sleep(0.03)
    assert controller.get_state()["completed_count"] > 0
    waveform = controller.get_waveform_data(-1)
    assert waveform["changed"] is True
    assert waveform["waveform"]["collected_count"] > 0
    assert len(waveform["waveform"]["channels"]) == 4
    assert all(
        len(channel) == waveform["waveform"]["collected_count"]
        for channel in waveform["waveform"]["channels"]
    )
    assert controller.get_waveform_data(waveform["revision"])["changed"] is False
    assert controller.stop()["ok"] is True
    deadline = time.monotonic() + 3
    while controller.get_state()["status"] != "idle" and time.monotonic() < deadline:
        time.sleep(0.03)
    assert controller.get_state()["status"] == "idle"
    assert controller.get_state()["pending_count"] == 0
    controller.shutdown()
