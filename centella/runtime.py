from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .settings import SETTINGS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
TOOLCHAIN_ROOT = WORKSPACE_ROOT / "TOOLCHAIN"
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "scripts" / "INSTALL_BETA.ps1"


@dataclass
class RuntimeProbe:
    executable: str
    exists: bool
    version: str = ""
    modules: Dict[str, bool] = None
    engine: bool = False
    error: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def candidate_pythons() -> List[Path]:
    candidates: List[Path] = []
    for relative in (
        Path("Python310") / "python.exe",
        Path("python310") / "python.exe",
        Path("Python") / "python.exe",
    ):
        p = TOOLCHAIN_ROOT / relative
        if p.exists():
            candidates.append(p)
    current = Path(sys.executable)
    if current.exists() and current not in candidates:
        candidates.append(current)
    return candidates


def _probe(exe: Path) -> RuntimeProbe:
    if not exe.exists():
        return RuntimeProbe(str(exe), False, modules={})
    code = r'''
import importlib, json, sys, traceback
mods = ["absl", "numpy", "cv2", "psutil", "pygame"]
result = {}
errors = []
for name in mods:
    try:
        importlib.import_module(name)
        result[name] = True
    except Exception as exc:
        result[name] = False
        errors.append(f"{name}: {type(exc).__name__}: {exc}")
engine = False
try:
    engine_module = importlib.import_module("gfootball_engine")
    engine = hasattr(engine_module, "GameEnv") and hasattr(engine_module, "GameState")
    result["gfootball_engine"] = engine
    if not engine:
        errors.append("gfootball_engine imported but native GameEnv/GameState are missing")
except Exception as exc:
    result["gfootball_engine"] = False
    errors.append(f"gfootball_engine: {type(exc).__name__}: {exc}")
print(json.dumps({"version": sys.version.split()[0], "modules": result, "engine": engine, "errors": errors}))
'''
    try:
        p = subprocess.run(
            [str(exe), "-c", code],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = [line for line in (p.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise RuntimeError((p.stderr or "runtime probe produced no output").strip())
        payload = json.loads(lines[-1])
        modules = payload.get("modules", {})
        errors = payload.get("errors", [])
        stderr = (p.stderr or "").strip()
        details = " | ".join(errors)
        if stderr:
            details = (details + " | " + stderr).strip(" |")
        return RuntimeProbe(
            str(exe), True, payload.get("version", ""), modules,
            bool(payload.get("engine", False)), details,
        )
    except Exception as exc:
        return RuntimeProbe(str(exe), True, modules={}, error=str(exc))


def probes() -> List[RuntimeProbe]:
    return [_probe(p) for p in candidate_pythons()]


def preferred_engine_python() -> Optional[Path]:
    for probe in probes():
        if probe.engine and probe.modules and all(
            probe.modules.get(m, False) for m in ("absl", "numpy", "pygame")
        ):
            return Path(probe.executable)
    return None


def runtime_summary() -> Dict:
    rows = probes()
    ready = any(
        probe.engine
        and probe.modules
        and all(probe.modules.get(m, False) for m in ("absl", "numpy", "pygame"))
        for probe in rows
    )
    return {
        "project_root": str(PROJECT_ROOT),
        "workspace_root": str(WORKSPACE_ROOT),
        "toolchain_root": str(TOOLCHAIN_ROOT),
        "bootstrap": str(BOOTSTRAP_SCRIPT),
        "runtimes": [p.to_dict() for p in rows],
        "ready": ready,
    }


def _player_spec(controller_count: int, local_players: int = 1, versus: bool = False) -> str:
    if controller_count <= 0:
        return "keyboard:left_players=1"
    if local_players <= 1:
        return "gamepad:left_players=1"
    if controller_count < 2:
        return "gamepad:left_players=1"
    if versus:
        return "gamepad:left_players=1;gamepad:right_players=1"
    return "gamepad:left_players=1;gamepad:left_players=1"


def launch_match(
    *,
    level: str = "",
    controller_count: int = 0,
    local_players: int = 1,
    versus: bool = False,
) -> Tuple[bool, str]:
    engine_python = preferred_engine_python()
    if engine_python is None:
        return False, "MOTOR NO PREPARADO. ABRE CENTELLA LAB Y EJECUTA INSTALAR/REPARAR."
    if local_players > 1 and controller_count < 2:
        return False, "CO-OP LOCAL REQUIERE DOS MANDOS."

    player_spec = _player_spec(controller_count, local_players, versus)
    width = int(SETTINGS.get("display.width", 1600))
    render_scale = float(SETTINGS.get("display.render_scale", 0.75))
    render_width = max(640, int(width * render_scale))
    low_latency = bool(SETTINGS.get("gameplay.low_latency_experimental", False))

    cmd = [
        str(engine_python),
        "-m", "gfootball.play_game",
        f"--players={player_spec}",
        "--action_set=full",
        "--render=True",
        "--real_time=True",
        f"--render_resolution_x={render_width}",
        f"--physics_steps_per_frame={5 if low_latency else 10}",
    ]
    if level:
        cmd.append(f"--level={level}")

    env = os.environ.copy()
    env["CENTELLA_FOOTBALL"] = "1"
    try:
        subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env)
        return True, "PARTIDO INICIADO"
    except OSError as exc:
        return False, f"NO SE PUDO INICIAR EL MOTOR: {exc}"


def open_bootstrap() -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "EL INSTALADOR AUTOMÁTICO DE ESTA BETA ESTÁ PREPARADO PARA WINDOWS."
    if not BOOTSTRAP_SCRIPT.exists():
        return False, "NO SE ENCONTRÓ scripts/INSTALL_BETA.ps1"
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(BOOTSTRAP_SCRIPT)],
            cwd=str(PROJECT_ROOT),
        )
        return True, "INSTALADOR ABIERTO EN POWERSHELL"
    except OSError as exc:
        return False, f"NO SE PUDO ABRIR EL INSTALADOR: {exc}"
