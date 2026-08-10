from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pygame

from .settings import SETTINGS


@dataclass
class InputAction:
    name: str
    value: float = 1.0
    source: str = "keyboard"


class ControllerManager:
    """Controller-first input layer for the CENTELLA shell.

    SDL/Pygame normalizes many Xbox/PlayStation compatible controllers to the
    familiar A/B/X/Y logical order. The mapping remains user-editable and is
    also consumed by the GRF ``gamepad.py`` player implementation.
    """

    def __init__(self) -> None:
        pygame.joystick.init()
        self.joysticks: List[pygame.joystick.Joystick] = []
        self.refresh()
        self.deadzone = float(SETTINGS.get("controller.deadzone", 0.22))
        self._axis_latch: Dict[Tuple[int, int, int], float] = {}
        self._last_repeat: Dict[str, float] = {}
        self._repeat_delay = SETTINGS.get("controller.menu_repeat_delay_ms", 245) / 1000.0
        self._repeat_rate = SETTINGS.get("controller.menu_repeat_ms", 120) / 1000.0

    def refresh(self) -> None:
        self.joysticks.clear()
        for index in range(pygame.joystick.get_count()):
            js = pygame.joystick.Joystick(index)
            js.init()
            self.joysticks.append(js)

    @property
    def connected(self) -> bool:
        return bool(self.joysticks)

    def names(self) -> List[str]:
        return [js.get_name() or f"Controller {i + 1}" for i, js in enumerate(self.joysticks)]

    def primary_name(self) -> str:
        return self.names()[0] if self.joysticks else "TECLADO"

    def button_for(self, action: str) -> int:
        return int(SETTINGS.get(f"controller.buttons.{action}", 0))

    def rebind_button(self, action: str, button_index: int) -> None:
        SETTINGS.set(f"controller.buttons.{action}", int(button_index))

    def _repeat_allowed(self, key: str, first: bool = False) -> bool:
        now = time.monotonic()
        previous = self._last_repeat.get(key)
        if previous is None:
            self._last_repeat[key] = now + self._repeat_delay - self._repeat_rate
            return True
        if first or now - previous >= self._repeat_rate:
            self._last_repeat[key] = now
            return True
        return False

    def _from_keyboard(self, event: pygame.event.Event) -> Optional[InputAction]:
        if event.type != pygame.KEYDOWN:
            return None
        key = event.key
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            return InputAction("confirm")
        if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            return InputAction("back")
        if key in (pygame.K_LEFT, pygame.K_a):
            return InputAction("left")
        if key in (pygame.K_RIGHT, pygame.K_d):
            return InputAction("right")
        if key in (pygame.K_UP, pygame.K_w):
            return InputAction("up")
        if key in (pygame.K_DOWN, pygame.K_s):
            return InputAction("down")
        if key in (pygame.K_q, pygame.K_PAGEUP):
            return InputAction("tab_left")
        if key in (pygame.K_e, pygame.K_PAGEDOWN):
            return InputAction("tab_right")
        if key == pygame.K_F1:
            return InputAction("performance")
        if key == pygame.K_F2:
            return InputAction("doctor")
        return None

    def translate(self, event: pygame.event.Event) -> Optional[InputAction]:
        kb = self._from_keyboard(event)
        if kb:
            return kb

        if event.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
            self.refresh()
            return InputAction("device_changed", source="controller")

        if event.type == pygame.JOYBUTTONDOWN:
            button = int(event.button)
            mapping = SETTINGS.get("controller.buttons", {})
            if button == int(mapping.get("confirm", 0)):
                return InputAction("confirm", source="controller")
            if button == int(mapping.get("back", 1)):
                return InputAction("back", source="controller")
            # Shoulder buttons are deliberately fixed for global navigation;
            # match actions mapped to them remain configurable independently.
            if button == 4:
                return InputAction("tab_left", source="controller")
            if button == 5:
                return InputAction("tab_right", source="controller")
            if button == int(mapping.get("pause", 7)):
                return InputAction("menu", source="controller")
            return InputAction(f"button:{button}", source="controller")

        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if x < 0:
                return InputAction("left", source="controller")
            if x > 0:
                return InputAction("right", source="controller")
            if y > 0:
                return InputAction("up", source="controller")
            if y < 0:
                return InputAction("down", source="controller")

        if event.type == pygame.JOYAXISMOTION and event.axis in (0, 1):
            v = float(event.value)
            if abs(v) < self.deadzone:
                for direction in (-1, 1):
                    self._axis_latch.pop((event.instance_id, event.axis, direction), None)
                return None
            direction = -1 if v < 0 else 1
            latch_key = (event.instance_id, event.axis, direction)
            now = time.monotonic()
            last = self._axis_latch.get(latch_key)
            if last is not None and now - last < self._repeat_rate:
                return None
            self._axis_latch[latch_key] = now
            if event.axis == 0:
                return InputAction("left" if direction < 0 else "right", source="controller")
            return InputAction("up" if direction < 0 else "down", source="controller")
        return None

    def ui_hint(self) -> str:
        if not self.connected:
            return "ENTER SELECCIONAR   ·   ESC VOLVER   ·   Q/E CAMBIAR PESTAÑA"
        name = self.primary_name().upper()
        if "PLAYSTATION" in name or "DUALSENSE" in name or "DUALSHOCK" in name:
            return "✕ SELECCIONAR   ·   ○ VOLVER   ·   L1/R1 CAMBIAR PESTAÑA"
        return "A SELECCIONAR   ·   B VOLVER   ·   LB/RB CAMBIAR PESTAÑA"


GAMEPLAY_ACTION_LABELS = [
    ("short_pass", "PASE CORTO / PRESIÓN"),
    ("shot", "TIRO / PRESIÓN DE EQUIPO"),
    ("high_pass", "CENTRO ALTO / ENTRADA"),
    ("long_pass", "PASE LARGO / SALIDA DE PORTERO"),
    ("switch_player", "CAMBIAR JUGADOR"),
    ("dribble", "DRIBBLE / CONTROL ESPECIAL"),
    ("pause", "PAUSA / OPCIONES"),
]
