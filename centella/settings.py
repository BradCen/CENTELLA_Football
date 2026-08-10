from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict


def _app_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "CENTELLA" / "Football"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "centella-football"


SETTINGS_DIR = _app_dir()
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
CONTENT_PATH = SETTINGS_DIR / "content.json"

DEFAULTS: Dict[str, Any] = {
    "display": {
        "fullscreen": False,
        "width": 1600,
        "height": 900,
        "ui_scale": 1.0,
        "vsync": True,
        "fps_cap": 60,
        "render_scale": 0.75,
        "quality": "BALANCED",
        "motion": True,
    },
    "audio": {
        "master": 0.85,
        "music": 0.65,
        "stadium": 0.90,
        "commentary": 0.85,
        "menu_sfx": 0.75,
    },
    "accessibility": {
        "high_contrast": False,
        "reduce_motion": False,
        "large_text": False,
        "hold_to_confirm": False,
    },
    "gameplay": {
        "difficulty": "PROFESSIONAL",
        "match_minutes": 10,
        "assisted_pass": 0.28,
        "assisted_shot": 0.18,
        "defensive_assist": 0.12,
        "low_latency_experimental": False,
    },
    "controller": {
        "preferred_device": "AUTO",
        "deadzone": 0.22,
        "menu_repeat_delay_ms": 245,
        "menu_repeat_ms": 120,
        "buttons": {
            # Generic SDL order: A/Cross, B/Circle, X/Square, Y/Triangle,
            # LB/L1, RB/R1, View/Create, Menu/Options.
            "confirm": 0,
            "back": 1,
            "short_pass": 0,
            "shot": 1,
            "high_pass": 2,
            "long_pass": 3,
            "switch_player": 4,
            "dribble": 5,
            "view": 6,
            "pause": 7,
        },
        "axes": {
            "move_x": 0,
            "move_y": 1,
            "sprint": 5,
        },
    },
    "profile": {
        "name": "PLAYER 1",
        "last_tab": "HOME",
        "last_mode": "PATADA INICIAL",
    },
}


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep settings created by the first shell compatible with Beta v2."""
    buttons = data.get("controller", {}).get("buttons", {}) if isinstance(data, dict) else {}
    if isinstance(buttons, dict):
        if "long_pass" not in buttons and "through_pass" in buttons:
            buttons["long_pass"] = buttons["through_pass"]
        if "dribble" not in buttons and "teammate_press" in buttons:
            buttons["dribble"] = buttons["teammate_press"]
    return data


class Settings:
    def __init__(self) -> None:
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data = _deep_merge(DEFAULTS, _migrate(raw))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.data = copy.deepcopy(DEFAULTS)

    def save(self) -> None:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)

    def get(self, dotted: str, default: Any = None) -> Any:
        value: Any = self.data
        for part in dotted.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def set(self, dotted: str, value: Any, save: bool = True) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        if save:
            self.save()

    def reset(self) -> None:
        self.data = copy.deepcopy(DEFAULTS)
        self.save()


SETTINGS = Settings()
