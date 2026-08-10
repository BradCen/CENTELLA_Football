from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from . import runtime

WEB_ROOT = Path(__file__).resolve().parent / "web"
INDEX_HTML = WEB_ROOT / "index.html"


class CentellaApi:
    """Small, deliberate bridge between the menu and the football runtime."""

    def __init__(self) -> None:
        self.window = None

    def bind_window(self, window: Any) -> None:
        self.window = window

    def runtime_state(self) -> Dict[str, Any]:
        summary = runtime.runtime_summary()
        return {
            "ready": bool(summary.get("ready")),
            "platform": os.name,
        }

    def play(self, local_players: int = 1, versus: bool = False) -> Dict[str, Any]:
        # Controller discovery is intentionally conservative until the native
        # runtime owns input enumeration. Keyboard always remains a valid P1.
        ok, message = runtime.launch_match(
            controller_count=0,
            local_players=max(1, int(local_players)),
            versus=bool(versus),
        )
        return {"ok": ok, "message": message}

    def toggle_fullscreen(self) -> Dict[str, Any]:
        if self.window is None:
            return {"ok": False}
        self.window.toggle_fullscreen()
        return {"ok": True}

    def close(self) -> Dict[str, Any]:
        if self.window is None:
            return {"ok": False}
        self.window.destroy()
        return {"ok": True}


def main() -> None:
    if not INDEX_HTML.exists():
        raise FileNotFoundError(f"CENTELLA web frontend missing: {INDEX_HTML}")

    import webview

    api = CentellaApi()
    window = webview.create_window(
        "CENTELLA Football",
        str(INDEX_HTML),
        js_api=api,
        width=1600,
        height=900,
        min_size=(960, 540),
        resizable=True,
        maximized=True,
        background_color="#05080f",
        text_select=False,
        zoomable=False,
    )
    api.bind_window(window)
    webview.start(debug=False, http_server=True, private_mode=True)


if __name__ == "__main__":
    main()
