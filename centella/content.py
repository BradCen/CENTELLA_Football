from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Dict, List

from .settings import SETTINGS_DIR


@dataclass
class Team:
    key: str
    name: str
    short: str
    city: str
    primary: str
    secondary: str
    rating: int
    style: str


TEAMS: List[Team] = [
    Team("centella", "CENTELLA FC", "CEN", "Barinas", "#2359AA", "#FFFFFF", 84, "Posesión vertical"),
    Team("aurora", "AURORA 1908", "AUR", "Northport", "#EDEDED", "#171717", 82, "Bloque medio"),
    Team("atlantic", "ATLANTIC CITY", "ATC", "Harbour", "#15366F", "#F0C861", 83, "Transición rápida"),
    Team("volcan", "VOLCÁN ROJO", "VOL", "Altavista", "#8B1D2C", "#101010", 81, "Presión alta"),
    Team("orion", "ORIÓN UNITED", "ORI", "Nova", "#E8E8EA", "#552A91", 85, "Juego interior"),
    Team("llanos", "LLANOS SPORTING", "LLA", "Barinas", "#1F6D42", "#F4F0D4", 80, "Ataque directo"),
    Team("metro", "METRO 11", "MET", "Capital", "#111827", "#57D2FF", 82, "Amplitud"),
    Team("sur", "SUR REAL", "SUR", "San Aurelio", "#F5F5F5", "#1D3A6F", 83, "Control paciente"),
]

COMPETITIONS = [
    {"name": "CENTELLA LEAGUE", "format": "Liga", "teams": 16, "identity": "SAPPHIRE"},
    {"name": "CONTINENTAL NIGHT", "format": "Grupos + KO", "teams": 32, "identity": "MIDNIGHT"},
    {"name": "CUP ZERO", "format": "Eliminación", "teams": 64, "identity": "WHITE"},
    {"name": "STREET CIRCUIT", "format": "Futsal/Street", "teams": 24, "identity": "CONCRETE"},
]

CONTENT_FILE = SETTINGS_DIR / "user_content.json"


def load_user_content() -> Dict:
    try:
        data = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_user_content(data: Dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    CONTENT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def teams_as_dicts() -> List[Dict]:
    return [asdict(t) for t in TEAMS]
