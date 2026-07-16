from __future__ import annotations

import queue
import time
import traceback
from datetime import datetime
from multiprocessing.queues import Queue

from .engine import TriggerWindowProcessor
from .model import AcquisitionConfig
from .sources import create_source


def acquisition_worker(config_data: dict, command_queue: Queue, event_queue: Queue, run_id: str) -> None:
    config = AcquisitionConfig(**config_data)
    source = create_source(config)
    processor: TriggerWindowProcessor | None = None
    stop_requested = False
    try:
        source.open()
        started_at = datetime.now().astimezone()
        processor = TriggerWindowProcessor(config, source.actual_sample_rate_hz, run_id, started_at)
        event_queue.put(
            {
                "type": "started",
                "actual_sample_rate_hz": source.actual_sample_rate_hz,
                "sample_count": processor.expected_sample_count,
                "started_at": started_at.isoformat(timespec="seconds"),
            }
        )

        last_status = time.monotonic()
        last_waveform_revision = 0
        last_waveform_event: int | None = None
        last_waveform_count = 0
        next_waveform_emit = 0.0
        while True:
            stop_requested = _consume_commands(command_queue, event_queue, processor, stop_requested)

            if stop_requested and not processor.pending:
                break

            block = source.read()
            # Catch a stop request that arrived while a hardware read was blocked.
            stop_requested = _consume_commands(command_queue, event_queue, processor, stop_requested)
            results = processor.process(block)
            waveform = processor.latest_waveform
            if processor.waveform_revision != last_waveform_revision and waveform is not None:
                now = time.monotonic()
                event_changed = waveform["event_index"] != last_waveform_event
                if event_changed or waveform["complete"] or now >= next_waveform_emit:
                    first_new = 0 if event_changed else last_waveform_count
                    packet = {key: value for key, value in waveform.items() if key != "channels"}
                    packet["reset"] = event_changed
                    packet["channels"] = [values[first_new:] for values in waveform["channels"]]
                    event_queue.put({"type": "waveform", "waveform": packet})
                    last_waveform_revision = processor.waveform_revision
                    last_waveform_event = waveform["event_index"]
                    last_waveform_count = waveform["collected_count"]
                    next_waveform_emit = now + (1.0 / 60.0)
            if results:
                event_queue.put({"type": "results", "records": results, "pending": len(processor.pending)})

            now = time.monotonic()
            if now - last_status >= 0.25:
                event_queue.put(
                    {
                        "type": "progress",
                        "pending": len(processor.pending),
                        "samples_acquired": processor.next_sample_index,
                    }
                )
                last_status = now

        event_queue.put({"type": "stopped", "pending": 0})
    except Exception as exc:
        event_queue.put(
            {
                "type": "error",
                "message": str(exc) or exc.__class__.__name__,
                "unfinished_windows": len(processor.pending) if processor else 0,
                "details": traceback.format_exc(limit=8),
            }
        )
    finally:
        try:
            source.close()
        except Exception as close_exc:
            event_queue.put({"type": "warning", "message": f"关闭设备时发生错误：{close_exc}"})


def _consume_commands(command_queue: Queue, event_queue: Queue, processor: TriggerWindowProcessor, stopped: bool) -> bool:
    try:
        while True:
            command = command_queue.get_nowait()
            if command.get("type") == "stop" and not stopped:
                stopped = True
                processor.stop_accepting_triggers()
                event_queue.put({"type": "draining", "pending": len(processor.pending)})
    except queue.Empty:
        return stopped
