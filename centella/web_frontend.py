from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from . import runtime

CENTELLA_ROOT = Path(__file__).resolve().parent
REACT_WEB_ROOT = CENTELLA_ROOT / "web-react"
LEGACY_WEB_ROOT = CENTELLA_ROOT / "web"
_WINDOW: Any | None = None


def _index_html() -> Path:
    """Prefer the new React build, but never brick the launcher during migration."""
    react_index = REACT_WEB_ROOT / "index.html"
    if react_index.exists():
        return react_index
    return LEGACY_WEB_ROOT / "index.html"


class CentellaApi:
    """Small, deliberate bridge between the menu and the football runtime.

    Keep native pywebview objects out of the js_api instance. pywebview inspects
    public attributes on that object when exposing the API to JavaScript; storing
    the Window there makes it recursively walk WinForms/WebView2 COM objects.
    """

    def runtime_state(self) -> Dict[str, Any]:
        summary = runtime.runtime_summary()
        return {
            "ready": bool(summary.get("ready")),
            "platform": os.name,
        }

    def play(self, local_players: int = 1, versus: bool = False) -> Dict[str, Any]:
        # Kept for compatibility with older menu builds.
        ok, message = runtime.launch_match(
            controller_count=0,
            local_players=max(1, int(local_players)),
            versus=bool(versus),
        )
        return {"ok": ok, "message": message}

    def play_config(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Launch the real Gameplay Football match configured by the web menu."""
        config = dict(payload or {})
        try:
            local_players = max(1, int(config.get("local_players", 1)))
        except (TypeError, ValueError):
            local_players = 1
        try:
            controller_count = max(0, int(config.get("controller_count", 0)))
        except (TypeError, ValueError):
            controller_count = 0

        ok, message = runtime.launch_match(
            level=str(config.get("level", "") or ""),
            controller_count=controller_count,
            local_players=local_players,
            versus=bool(config.get("versus", False)),
            match_config=config,
        )
        return {"ok": ok, "message": message}

    def toggle_fullscreen(self) -> Dict[str, Any]:
        if _WINDOW is None:
            return {"ok": False}
        _WINDOW.toggle_fullscreen()
        return {"ok": True}

    def close(self) -> Dict[str, Any]:
        if _WINDOW is None:
            return {"ok": False}
        _WINDOW.destroy()
        return {"ok": True}


def main() -> None:
    global _WINDOW

    index_html = _index_html()
    if not index_html.exists():
        raise FileNotFoundError(f"CENTELLA web frontend missing: {index_html}")

    import webview

    api = CentellaApi()
    _WINDOW = webview.create_window(
        "CENTELLA Football",
        str(index_html),
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
    webview.start(debug=False, http_server=True, private_mode=True)


if __name__ == "__main__":
    main()
