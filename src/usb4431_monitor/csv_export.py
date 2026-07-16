from __future__ import annotations

import csv
from pathlib import Path


ALL_FIELDS = [
    "event_index",
    "acquisition_run",
    "trigger_timestamp",
    "trigger_sample_index",
    "ai0_mean_V",
    "ai1_mean_V",
    "ai2_mean_V",
    "ai3_mean_V",
    "sample_rate_Hz",
    "window_start_ms",
    "window_end_ms",
    "sample_count",
]

CHANNEL_FIELDS = [
    "event_index",
    "acquisition_run",
    "trigger_timestamp",
    "trigger_sample_index",
    "channel",
    "mean_voltage_V",
    "sample_rate_Hz",
    "window_start_ms",
    "window_end_ms",
    "sample_count",
]


def export_all(path: str | Path, records: list[dict]) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ALL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def export_channel(path: str | Path, records: list[dict], channel: int) -> None:
    channel_name = f"ai{channel}"
    rows = []
    for record in records:
        rows.append(
            {
                "event_index": record["event_index"],
                "acquisition_run": record["acquisition_run"],
                "trigger_timestamp": record["trigger_timestamp"],
                "trigger_sample_index": record["trigger_sample_index"],
                "channel": channel_name,
                "mean_voltage_V": record[f"{channel_name}_mean_V"],
                "sample_rate_Hz": record["sample_rate_Hz"],
                "window_start_ms": record["window_start_ms"],
                "window_end_ms": record["window_end_ms"],
                "sample_count": record["sample_count"],
            }
        )
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHANNEL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

