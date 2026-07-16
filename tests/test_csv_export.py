import csv

from usb4431_monitor.csv_export import ALL_FIELDS, CHANNEL_FIELDS, export_all, export_channel


def record():
    return {
        "event_index": 1,
        "acquisition_run": "run-1",
        "trigger_timestamp": "2026-01-01T00:00:00.001+00:00",
        "trigger_sample_index": 10,
        "ai0_mean_V": 0.1,
        "ai1_mean_V": 1.1,
        "ai2_mean_V": 2.1,
        "ai3_mean_V": 3.1,
        "sample_rate_Hz": 10_000,
        "window_start_ms": 20,
        "window_end_ms": 120,
        "sample_count": 1_000,
        "run_time_s": 0.001,
    }


def test_all_channel_csv_has_exact_contract(tmp_path):
    path = tmp_path / "all.csv"
    export_all(path, [record()])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == ALL_FIELDS
    assert rows[0]["ai3_mean_V"] == "3.1"


def test_single_channel_csv_has_exact_contract(tmp_path):
    path = tmp_path / "ai2.csv"
    export_channel(path, [record()], 2)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == CHANNEL_FIELDS
    assert rows[0]["channel"] == "ai2"
    assert rows[0]["mean_voltage_V"] == "2.1"

