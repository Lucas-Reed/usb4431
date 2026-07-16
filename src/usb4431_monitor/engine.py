from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from .model import AcquisitionConfig, window_bounds, window_sample_count


@dataclass(slots=True)
class PendingWindow:
    event_index: int
    trigger_index: int
    first_index: int
    last_index: int
    trigger_timestamp: str
    sums: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float64))
    count: int = 0
    raw_chunks: list[np.ndarray] = field(default_factory=list)


class TriggerWindowProcessor:
    """Stateful trigger detector and overlapping interval accumulator."""

    def __init__(
        self,
        config: AcquisitionConfig,
        actual_sample_rate_hz: float,
        acquisition_run: str,
        started_at: datetime,
    ) -> None:
        config.validate()
        self.config = config
        self.sample_rate_hz = float(actual_sample_rate_hz)
        self.acquisition_run = acquisition_run
        self.started_at = started_at
        self.next_sample_index = 0
        self.next_event_index = 1
        self.pending: list[PendingWindow] = []
        self.accept_triggers = True
        self._initialized = False
        self._armed = False
        self._previous_trigger_value = 0.0
        self._last_trigger_index: int | None = None
        self._display_event_index: int | None = None
        self.latest_waveform: dict | None = None
        self.waveform_revision = 0
        self._published_waveform_key: tuple[int, int, bool] | None = None

    @property
    def expected_sample_count(self) -> int:
        return window_sample_count(
            self.sample_rate_hz,
            self.config.window_start_s,
            self.config.window_end_s,
        )

    def stop_accepting_triggers(self) -> None:
        self.accept_triggers = False

    def process(self, samples: np.ndarray) -> list[dict]:
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 2 or data.shape[0] != 4:
            raise ValueError("采样块必须是 shape=(4, n) 的数组")
        if data.shape[1] == 0:
            return []

        block_start = self.next_sample_index
        block_end = block_start + data.shape[1] - 1

        # Existing windows consume the block before newly detected windows are added.
        for window in self.pending:
            self._accumulate(window, data, block_start, block_end)

        trigger_values = data[self.config.trigger_channel]
        new_windows = self._detect_triggers(trigger_values, block_start)
        for window in new_windows:
            self._accumulate(window, data, block_start, block_end)
            self.pending.append(window)

        display_window = next(
            (window for window in reversed(self.pending) if window.event_index == self._display_event_index),
            None,
        )
        if display_window is not None:
            self._publish_waveform(display_window, block_end >= display_window.last_index)

        self.next_sample_index = block_end + 1
        completed: list[dict] = []
        remaining: list[PendingWindow] = []
        for window in self.pending:
            if block_end >= window.last_index:
                completed.append(self._finish(window))
            else:
                remaining.append(window)
        self.pending = remaining
        return completed

    def _detect_triggers(self, values: np.ndarray, block_start: int) -> list[PendingWindow]:
        threshold = self.config.trigger_threshold_v
        rearm_level = threshold - self.config.trigger_hysteresis_v
        minimum_samples = int(np.ceil(self.config.min_trigger_interval_s * self.sample_rate_hz))
        windows: list[PendingWindow] = []

        for offset, value in enumerate(values):
            index = block_start + offset
            value = float(value)
            if not self._initialized:
                self._initialized = True
                self._armed = value <= rearm_level
                self._previous_trigger_value = value
                continue

            if not self._armed and value <= rearm_level:
                self._armed = True

            interval_ok = self._last_trigger_index is None or index - self._last_trigger_index >= minimum_samples
            crossing = self._previous_trigger_value < threshold <= value
            if self.accept_triggers and self._armed and crossing and interval_ok:
                first, last = window_bounds(
                    index,
                    self.sample_rate_hz,
                    self.config.window_start_s,
                    self.config.window_end_s,
                )
                timestamp = self.started_at + timedelta(seconds=index / self.sample_rate_hz)
                windows.append(
                    PendingWindow(
                        event_index=self.next_event_index,
                        trigger_index=index,
                        first_index=first,
                        last_index=last,
                        trigger_timestamp=timestamp.astimezone().isoformat(timespec="milliseconds"),
                    )
                )
                self.next_event_index += 1
                self._last_trigger_index = index
                self._display_event_index = windows[-1].event_index
                self._armed = False

            self._previous_trigger_value = value
        return windows

    @staticmethod
    def _accumulate(window: PendingWindow, data: np.ndarray, block_start: int, block_end: int) -> None:
        overlap_start = max(window.first_index, block_start)
        overlap_end = min(window.last_index, block_end)
        if overlap_start > overlap_end:
            return
        local_start = overlap_start - block_start
        local_stop = overlap_end - block_start + 1
        window.sums += np.sum(data[:, local_start:local_stop], axis=1, dtype=np.float64)
        window.count += local_stop - local_start
        window.raw_chunks.append(data[:, local_start:local_stop].copy())

    def _publish_waveform(self, window: PendingWindow, completed: bool) -> None:
        publish_key = (window.event_index, window.count, completed)
        if publish_key == self._published_waveform_key:
            return
        if window.raw_chunks:
            samples = np.concatenate(window.raw_chunks, axis=1)
        else:
            samples = np.empty((4, 0), dtype=np.float64)
        self.waveform_revision += 1
        self._published_waveform_key = publish_key
        self.latest_waveform = {
            "revision": self.waveform_revision,
            "event_index": window.event_index,
            "acquisition_run": self.acquisition_run,
            "trigger_timestamp": window.trigger_timestamp,
            "trigger_sample_index": window.trigger_index,
            "sample_rate_Hz": self.sample_rate_hz,
            "window_start_ms": self.config.window_start_s * 1000.0,
            "window_end_ms": self.config.window_end_s * 1000.0,
            "first_sample_offset_ms": (window.first_index - window.trigger_index) / self.sample_rate_hz * 1000.0,
            "expected_count": self.expected_sample_count,
            "collected_count": window.count,
            "complete": completed,
            "channels": [samples[channel].tolist() for channel in range(4)],
        }

    def _finish(self, window: PendingWindow) -> dict:
        if window.count <= 0:
            raise RuntimeError("平均窗口没有有效样本")
        means = window.sums / window.count
        return {
            "event_index": window.event_index,
            "acquisition_run": self.acquisition_run,
            "trigger_timestamp": window.trigger_timestamp,
            "trigger_sample_index": window.trigger_index,
            "ai0_mean_V": float(means[0]),
            "ai1_mean_V": float(means[1]),
            "ai2_mean_V": float(means[2]),
            "ai3_mean_V": float(means[3]),
            "sample_rate_Hz": self.sample_rate_hz,
            "window_start_ms": self.config.window_start_s * 1000.0,
            "window_end_ms": self.config.window_end_s * 1000.0,
            "sample_count": window.count,
            "run_time_s": window.trigger_index / self.sample_rate_hz,
        }
