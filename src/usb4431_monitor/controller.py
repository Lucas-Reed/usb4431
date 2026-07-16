from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .csv_export import export_all, export_channel
from .model import AcquisitionConfig
from .worker import acquisition_worker


class AppController:
    PLOT_LIMIT = 5_000

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: mp.Process | None = None
        self._commands = None
        self._events = None
        self._listener: threading.Thread | None = None
        self._records: list[dict] = []
        self._exported_count = 0
        self._waveform: dict | None = None
        self._waveform_revision = 0
        self._run_event_offset = 0
        self._state = {
            "status": "idle",
            "device_status": "未连接",
            "message": "就绪",
            "actual_sample_rate_hz": None,
            "window_start_ms": None,
            "window_end_ms": None,
            "sample_count": None,
            "completed_count": 0,
            "pending_count": 0,
            "samples_acquired": 0,
            "acquisition_run": None,
            "mode": None,
            "started_at": None,
            "unfinished_windows": 0,
        }
        self._summaries = [self._empty_summary() for _ in range(4)]

    @staticmethod
    def _empty_summary() -> dict:
        return {"latest": None, "drift": None, "min": None, "max": None}

    def get_state(self) -> dict:
        with self._lock:
            return {
                **self._state,
                "completed_count": len(self._records),
                "unsaved": len(self._records) > self._exported_count,
                "summaries": [dict(item) for item in self._summaries],
                "config_locked": self._state["status"] in {"starting", "running", "draining"},
            }

    def start(self, raw_config: dict) -> dict:
        try:
            config = AcquisitionConfig.from_ui(raw_config)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

        with self._lock:
            if self._state["status"] in {"starting", "running", "draining"}:
                return {"ok": False, "error": "采集已经在运行"}
            if self._process is not None and self._process.is_alive():
                return {"ok": False, "error": "上一次采集进程尚未退出"}

            ctx = mp.get_context("spawn")
            self._commands = ctx.Queue()
            self._events = ctx.Queue()
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
            self._process = ctx.Process(
                target=acquisition_worker,
                args=(config.to_dict(), self._commands, self._events, run_id),
                name="usb4431-acquisition",
                daemon=True,
            )
            self._state.update(
                {
                    "status": "starting",
                    "device_status": "连接中",
                    "message": "正在启动采集进程…",
                    "actual_sample_rate_hz": None,
                    "sample_count": None,
                    "pending_count": 0,
                    "samples_acquired": 0,
                    "acquisition_run": run_id,
                    "mode": config.mode,
                    "unfinished_windows": 0,
                    "window_start_ms": config.window_start_s * 1000.0,
                    "window_end_ms": config.window_end_s * 1000.0,
                }
            )
            self._waveform = None
            self._waveform_revision += 1
            self._run_event_offset = len(self._records)
            self._process.start()

        deadline = time.monotonic() + 8.0
        first_event = None
        while time.monotonic() < deadline:
            try:
                first_event = self._events.get(timeout=0.2)
                break
            except queue.Empty:
                if self._process is not None and not self._process.is_alive():
                    break

        if first_event is None:
            self._fail_start("采集启动超时或进程异常退出")
            return {"ok": False, "error": self._state["message"]}
        if first_event.get("type") == "error":
            self._handle_event(first_event)
            self._join_process()
            return {"ok": False, "error": first_event.get("message", "采集启动失败")}

        self._handle_event(first_event)
        self._listener = threading.Thread(target=self._listen, name="acquisition-events", daemon=True)
        self._listener.start()
        return {"ok": True, "state": self.get_state()}

    def stop(self) -> dict:
        with self._lock:
            if self._state["status"] not in {"starting", "running"}:
                return {"ok": False, "error": "当前没有正在运行的采集"}
            self._state.update({"status": "draining", "message": "停止接收新触发，正在完成已有窗口…"})
            if self._commands is not None:
                self._commands.put({"type": "stop"})
        return {"ok": True}

    def get_plot_data(self) -> dict:
        with self._lock:
            total = len(self._records)
            if total <= self.PLOT_LIMIT:
                selected = list(self._records)
            else:
                # Uniformly preserve both endpoints and approximately PLOT_LIMIT representatives.
                indices = [(i * (total - 1)) // (self.PLOT_LIMIT - 1) for i in range(self.PLOT_LIMIT)]
                selected = [self._records[index] for index in indices]
            return {
                "total": total,
                "drawn": len(selected),
                "records": selected,
            }

    def get_waveform_data(self, since_revision: int = -1) -> dict:
        with self._lock:
            if int(since_revision) == self._waveform_revision:
                return {"changed": False, "revision": self._waveform_revision}
            return {
                "changed": True,
                "revision": self._waveform_revision,
                "waveform": self._waveform,
            }

    def clear_data(self, force: bool = False) -> dict:
        with self._lock:
            if self._state["status"] in {"starting", "running", "draining"}:
                return {"ok": False, "error": "请先停止采集"}
            if len(self._records) > self._exported_count and not force:
                return {"ok": False, "confirm_required": True}
            self._records.clear()
            self._exported_count = 0
            self._waveform = None
            self._waveform_revision += 1
            self._summaries = [self._empty_summary() for _ in range(4)]
            self._state.update({"completed_count": 0, "message": "数据已清空"})
            return {"ok": True}

    def export_all_csv(self) -> dict:
        with self._lock:
            records = list(self._records)
        if not records:
            return {"ok": False, "error": "当前没有可导出的结果"}
        path = self._choose_save_path("USB4431_all_channels.csv")
        if not path:
            return {"ok": False, "cancelled": True}
        try:
            export_all(path, records)
        except OSError as exc:
            return {"ok": False, "error": f"CSV 保存失败：{exc}"}
        with self._lock:
            self._exported_count = max(self._exported_count, len(records))
        return {"ok": True, "path": str(path), "count": len(records)}

    def export_channel_csv(self, channel: int) -> dict:
        if channel not in range(4):
            return {"ok": False, "error": "通道无效"}
        with self._lock:
            records = list(self._records)
        if not records:
            return {"ok": False, "error": "当前没有可导出的结果"}
        path = self._choose_save_path(f"USB4431_AI{channel}.csv")
        if not path:
            return {"ok": False, "cancelled": True}
        try:
            export_channel(path, records, channel)
        except OSError as exc:
            return {"ok": False, "error": f"CSV 保存失败：{exc}"}
        return {"ok": True, "path": str(path), "count": len(records)}

    def list_devices(self) -> dict:
        try:
            import nidaqmx.system

            devices = [device.name for device in nidaqmx.system.System.local().devices]
            return {"ok": True, "devices": devices}
        except Exception as exc:
            return {"ok": False, "devices": [], "error": f"无法读取 NI 设备：{exc}"}

    def has_unsaved_data(self) -> bool:
        with self._lock:
            return len(self._records) > self._exported_count

    def shutdown(self) -> None:
        with self._lock:
            process = self._process
            if process is not None and process.is_alive() and self._commands is not None:
                self._commands.put({"type": "stop"})
        if process is not None:
            process.join(timeout=3.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)

    def _choose_save_path(self, default_name: str) -> Path | None:
        try:
            import webview

            if not webview.windows:
                return None
            selection = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=default_name,
                file_types=("CSV 文件 (*.csv)",),
            )
            if not selection:
                return None
            if isinstance(selection, (tuple, list)):
                selection = selection[0]
            path = Path(selection)
            return path if path.suffix.lower() == ".csv" else path.with_suffix(".csv")
        except Exception:
            return None

    def _listen(self) -> None:
        while True:
            try:
                event = self._events.get(timeout=0.25)
                self._handle_event(event)
                if event.get("type") in {"stopped", "error"}:
                    break
            except queue.Empty:
                if self._process is None or not self._process.is_alive():
                    with self._lock:
                        if self._state["status"] not in {"idle", "error"}:
                            self._state.update({"status": "error", "message": "采集进程意外退出"})
                    break
        self._join_process()

    def _handle_event(self, event: dict) -> None:
        kind = event.get("type")
        with self._lock:
            if kind == "started":
                self._state.update(
                    {
                        "status": "running",
                        "device_status": "模拟器在线" if self._state.get("mode") == "simulation" else "USB-4431 在线",
                        "message": "采集中",
                        "actual_sample_rate_hz": event["actual_sample_rate_hz"],
                        "sample_count": event["sample_count"],
                        "started_at": event["started_at"],
                    }
                )
            elif kind == "results":
                for record in event.get("records", []):
                    record["event_index"] = len(self._records) + 1
                    self._records.append(record)
                    self._update_summaries(record)
                self._state.update(
                    {
                        "completed_count": len(self._records),
                        "pending_count": event.get("pending", 0),
                    }
                )
            elif kind == "waveform":
                packet = dict(event.get("waveform") or {})
                if packet:
                    packet["event_index"] = self._run_event_offset + int(packet["event_index"])
                    chunks = packet.pop("channels", [[], [], [], []])
                    reset = bool(packet.pop("reset", False))
                    if reset or self._waveform is None or self._waveform.get("event_index") != packet["event_index"]:
                        self._waveform = {**packet, "channels": [list(chunk) for chunk in chunks]}
                    else:
                        for channel, chunk in enumerate(chunks):
                            self._waveform["channels"][channel].extend(chunk)
                        self._waveform.update(packet)
                    self._waveform_revision += 1
            elif kind == "progress":
                self._state.update(
                    {
                        "pending_count": event.get("pending", 0),
                        "samples_acquired": event.get("samples_acquired", 0),
                    }
                )
            elif kind == "draining":
                self._state.update({"status": "draining", "pending_count": event.get("pending", 0)})
            elif kind == "stopped":
                self._state.update(
                    {
                        "status": "idle",
                        "device_status": "未连接",
                        "message": "采集已安全停止",
                        "pending_count": 0,
                    }
                )
            elif kind == "warning":
                self._state["message"] = event.get("message", "设备警告")
            elif kind == "error":
                unfinished = int(event.get("unfinished_windows", 0))
                self._state.update(
                    {
                        "status": "error",
                        "device_status": "连接异常",
                        "message": event.get("message", "采集错误"),
                        "unfinished_windows": unfinished,
                        "pending_count": 0,
                    }
                )

    def _update_summaries(self, record: dict) -> None:
        for channel in range(4):
            value = float(record[f"ai{channel}_mean_V"])
            summary = self._summaries[channel]
            if summary["latest"] is None:
                summary.update({"latest": value, "drift": 0.0, "min": value, "max": value, "first": value})
            else:
                summary["latest"] = value
                summary["drift"] = value - summary["first"]
                summary["min"] = min(summary["min"], value)
                summary["max"] = max(summary["max"], value)

    def _fail_start(self, message: str) -> None:
        with self._lock:
            process = self._process
            self._state.update({"status": "error", "device_status": "连接失败", "message": message})
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1.0)

    def _join_process(self) -> None:
        process = self._process
        if process is not None:
            process.join(timeout=1.0)
