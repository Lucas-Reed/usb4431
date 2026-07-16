from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from .controller import AppController


def main() -> None:
    mp.freeze_support()
    try:
        import webview
    except ImportError as exc:
        raise SystemExit("缺少 pywebview，请先执行 pip install -e .") from exc

    controller = AppController()
    page = (Path(__file__).parent / "web" / "index.html").resolve().as_uri()
    window = webview.create_window(
        "USB-4431 触发后区间平均长漂监测",
        page,
        js_api=controller,
        width=1500,
        height=960,
        min_size=(1120, 720),
        background_color="#0a0f14",
    )

    def on_closing() -> bool:
        if controller.has_unsaved_data():
            try:
                allow = window.evaluate_js("window.confirm('存在未导出的结果，确定退出吗？')")
                if not allow:
                    return False
            except Exception:
                return False
        controller.shutdown()
        return True

    window.events.closing += on_closing
    webview.start(debug=False)


if __name__ == "__main__":
    main()

