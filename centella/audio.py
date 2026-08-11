from __future__ import annotations

import math
from array import array
from typing import Dict, Iterable

import pygame

from .settings import SETTINGS


class UISounds:
    """Tiny procedural sound bank.

    No music or third-party samples are bundled. These short tones exist only
    to make controller navigation feel responsive until original audio assets
    are produced.
    """

    def __init__(self) -> None:
        self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=256)
            self.sounds = {
                "nav": self._tone((390.0, 525.0), 0.045, 0.18),
                "confirm": self._tone((420.0, 630.0, 840.0), 0.085, 0.22),
                "back": self._tone((330.0, 245.0), 0.065, 0.18),
                "tab": self._tone((520.0, 720.0), 0.055, 0.16),
                "ready": self._tone((260.0, 520.0, 780.0), 0.14, 0.22),
            }
            self.enabled = True
        except pygame.error:
            # Audio must never prevent the football shell from opening.
            self.sounds = {}
            self.enabled = False

    @staticmethod
    def _tone(frequencies: Iterable[float], seconds: float, amplitude: float) -> pygame.mixer.Sound:
        sample_rate = 44100
        count = max(1, int(sample_rate * seconds))
        freqs = tuple(frequencies)
        samples = array("h")
        for i in range(count):
            t = i / sample_rate
            # Very fast attack with an exponential-style release prevents clicks
            # and keeps the sound closer to a sports UI than an arcade beep.
            attack = min(1.0, i / max(1, int(sample_rate * 0.004)))
            release = (1.0 - i / count) ** 2.2
            wave = sum(math.sin(2.0 * math.pi * f * t) for f in freqs) / len(freqs)
            value = int(32767 * amplitude * attack * release * wave)
            samples.append(max(-32767, min(32767, value)))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        master = float(SETTINGS.get("audio.master", 0.85))
        menu = float(SETTINGS.get("audio.menu_sfx", 0.75))
        sound.set_volume(max(0.0, min(1.0, master * menu)))
        sound.play()
