from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from uuid import uuid4

import numpy as np

from .model import AcquisitionConfig


class SampleSource(ABC):
    actual_sample_rate_hz: float

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> np.ndarray: ...

    @abstractmethod
    def close(self) -> None: ...


class SimulationSource(SampleSource):
    def __init__(self, config: AcquisitionConfig, block_size: int = 512) -> None:
        self.config = config
        self.actual_sample_rate_hz = float(config.requested_sample_rate_hz)
        self.block_size = block_size
        self._index = 0
        self._rng = np.random.default_rng(4431)
        self._next_deadline = 0.0

    def open(self) -> None:
        self._next_deadline = time.perf_counter()

    def read(self) -> np.ndarray:
        rate = self.actual_sample_rate_hz
        indices = np.arange(self._index, self._index + self.block_size, dtype=np.int64)
        t = indices / rate
        drift = 0.018 * np.sin(2 * np.pi * t / 45.0) + 0.00008 * t
        base = np.array([0.0, 1.0, -1.0, 0.5], dtype=np.float64)[:, None]
        gains = np.array([1.0, 0.72, 1.18, -0.55], dtype=np.float64)[:, None]
        noise = self._rng.normal(0.0, 0.002, size=(4, self.block_size))
        data = base + gains * drift[None, :] + noise

        period = max(2, int(round(self.config.simulation_trigger_period_s * rate)))
        pulse_width = max(1, int(round(0.012 * rate)))
        phase = indices % period
        trigger_wave = np.where(phase < pulse_width, 5.0, 0.0)
        data[self.config.trigger_channel] = trigger_wave + noise[self.config.trigger_channel] * 0.2

        self._index += self.block_size
        if self.config.simulation_realtime:
            self._next_deadline += self.block_size / rate
            delay = self._next_deadline - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        return data

    def close(self) -> None:
        return None


class NIDaqSource(SampleSource):
    """Continuous four-channel NI-DAQmx source for USB-4431."""

    def __init__(self, config: AcquisitionConfig, block_size: int = 1024) -> None:
        self.config = config
        self.block_size = block_size
        self.actual_sample_rate_hz = float(config.requested_sample_rate_hz)
        self._task = None
        self._reader = None
        self._buffer = np.empty((4, block_size), dtype=np.float64)

    def open(self) -> None:
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, Coupling
            from nidaqmx.stream_readers import AnalogMultiChannelReader
        except ImportError as exc:
            raise RuntimeError("未安装 NI-DAQmx Python 支持，请安装项目依赖和 NI-DAQmx 驱动") from exc

        last_error: Exception | None = None
        for attempt in range(3):
            task_name = f"USB4431_LongDrift_{os.getpid()}_{uuid4().hex[:8]}"
            task = nidaqmx.Task(task_name)
            try:
                for index in range(4):
                    channel = task.ai_channels.add_ai_voltage_chan(
                        f"{self.config.device}/ai{index}",
                        min_val=-10.0,
                        max_val=10.0,
                    )
                    try:
                        channel.ai_coupling = Coupling.DC
                    except Exception:
                        pass
                    # USB-4431 IEPE excitation is disabled for voltage inputs when supported.
                    try:
                        channel.ai_excit_enable = False
                    except Exception:
                        pass

                task.timing.cfg_samp_clk_timing(
                    rate=self.config.requested_sample_rate_hz,
                    sample_mode=AcquisitionType.CONTINUOUS,
                    samps_per_chan=max(self.block_size * 8, int(self.config.requested_sample_rate_hz)),
                )
                self.actual_sample_rate_hz = float(task.timing.samp_clk_rate)
                self._reader = AnalogMultiChannelReader(task.in_stream)
                task.start()
                self._task = task
                return
            except Exception as exc:
                last_error = exc
                task.close()
                self._reader = None
                if is_resource_reserved_error(exc) and attempt < 2:
                    time.sleep(0.5)
                    continue
                if is_resource_reserved_error(exc):
                    raise RuntimeError(
                        "USB-4431 仍被其他采集任务占用（NI-DAQmx -50103）。"
                        "程序已自动重试 3 次；请停止其他使用该设备的程序或 NI MAX 测试面板后重试。"
                    ) from exc
                raise
        if last_error is not None:
            raise last_error

    def read(self) -> np.ndarray:
        if self._reader is None:
            raise RuntimeError("NI 采集任务尚未启动")
        self._reader.read_many_sample(
            self._buffer,
            number_of_samples_per_channel=self.block_size,
            timeout=2.0,
        )
        return self._buffer.copy()

    def close(self) -> None:
        if self._task is not None:
            try:
                self._task.stop()
            finally:
                self._task.close()
        self._task = None
        self._reader = None


def create_source(config: AcquisitionConfig) -> SampleSource:
    if config.mode == "hardware":
        return NIDaqSource(config)
    return SimulationSource(config)


def is_resource_reserved_error(error: BaseException) -> bool:
    return getattr(error, "error_code", None) == -50103 or "-50103" in str(error)
