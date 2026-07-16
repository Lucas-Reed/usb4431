from __future__ import annotations

import sys
import traceback
from pathlib import Path

from usb4431_monitor.app import main


def hardware_self_test(report_path: str) -> int:
    from usb4431_monitor.model import AcquisitionConfig
    from usb4431_monitor.sources import NIDaqSource

    report = Path(report_path)
    source = NIDaqSource(AcquisitionConfig(mode="hardware", device="Dev1"))
    try:
        source.open()
        block = source.read()
        report.write_text(
            "PASS\n"
            f"sample_rate_hz={source.actual_sample_rate_hz}\n"
            f"shape={block.shape}\n",
            encoding="utf-8",
        )
        return 0
    except Exception:
        report.write_text("FAIL\n" + traceback.format_exc(), encoding="utf-8")
        return 1
    finally:
        source.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--hardware-self-test":
        raise SystemExit(hardware_self_test(sys.argv[2]))
    main()
