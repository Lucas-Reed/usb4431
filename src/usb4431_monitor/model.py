from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor, isfinite


CHANNELS = ("ai0", "ai1", "ai2", "ai3")


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    device: str = "Dev1"
    trigger_channel: int = 0
    trigger_threshold_v: float = 2.5
    trigger_hysteresis_v: float = 0.2
    min_trigger_interval_s: float = 0.1
    requested_sample_rate_hz: float = 10_000.0
    window_start_s: float = 0.0
    window_end_s: float = 0.1
    mode: str = "simulation"
    simulation_trigger_period_s: float = 0.25
    simulation_realtime: bool = True

    def validate(self) -> None:
        numeric = {
            "trigger_threshold_v": self.trigger_threshold_v,
            "trigger_hysteresis_v": self.trigger_hysteresis_v,
            "min_trigger_interval_s": self.min_trigger_interval_s,
            "requested_sample_rate_hz": self.requested_sample_rate_hz,
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
        }
        if not all(isfinite(value) for value in numeric.values()):
            raise ValueError("参数必须是有限数值")
        if self.mode not in {"simulation", "hardware"}:
            raise ValueError("采集模式无效")
        if self.trigger_channel not in range(4):
            raise ValueError("触发通道必须是 AI0–AI3")
        if not 1_000 <= self.requested_sample_rate_hz <= 102_400:
            raise ValueError("采样率必须在 1–102.4 kS/s 范围内")
        if self.trigger_hysteresis_v < 0:
            raise ValueError("触发回差不能为负数")
        if self.min_trigger_interval_s < 0:
            raise ValueError("最小触发间隔不能为负数")
        if not 0 <= self.window_start_s < self.window_end_s:
            raise ValueError("平均区间必须满足 0 ≤ 起点 < 终点")
        if self.simulation_trigger_period_s <= 0:
            raise ValueError("模拟触发周期必须大于 0")

    @classmethod
    def from_ui(cls, raw: dict) -> "AcquisitionConfig":
        unit_scale = 0.001 if raw.get("window_unit", "ms") == "ms" else 1.0
        config = cls(
            device=str(raw.get("device", "Dev1")).strip() or "Dev1",
            trigger_channel=int(raw.get("trigger_channel", 0)),
            trigger_threshold_v=float(raw.get("trigger_threshold_v", 2.5)),
            trigger_hysteresis_v=float(raw.get("trigger_hysteresis_v", 0.2)),
            min_trigger_interval_s=float(raw.get("min_trigger_interval_ms", 100)) / 1000.0,
            requested_sample_rate_hz=float(raw.get("sample_rate_hz", 10_000)),
            window_start_s=float(raw.get("window_start", 0)) * unit_scale,
            window_end_s=float(raw.get("window_end", 100)) * unit_scale,
            mode=str(raw.get("mode", "simulation")),
            simulation_trigger_period_s=float(raw.get("simulation_trigger_period_ms", 250)) / 1000.0,
            simulation_realtime=bool(raw.get("simulation_realtime", True)),
        )
        config.validate()
        return config

    def to_dict(self) -> dict:
        return asdict(self)


def window_bounds(trigger_index: int, sample_rate_hz: float, start_s: float, end_s: float) -> tuple[int, int]:
    """Return inclusive sample bounds for the interval ``(start, end]``.

    A zero start therefore begins at the sample immediately after the trigger.
    """
    first = trigger_index + floor(start_s * sample_rate_hz) + 1
    last = trigger_index + floor(end_s * sample_rate_hz)
    return first, last


def window_sample_count(sample_rate_hz: float, start_s: float, end_s: float) -> int:
    first, last = window_bounds(0, sample_rate_hz, start_s, end_s)
    return max(0, last - first + 1)

