from __future__ import annotations

import math

import pygame

from .brand import BRAND
from .cinematic_frontend import App as CinematicApp, BLUE, BLUE_L, MUTED, WHITE
from .ui import LOGICAL_SIZE, draw_glow, draw_text, rounded_panel


class App(CinematicApp):
    """Player-facing release presentation for the current CENTELLA shell.

    Engineering health remains available through F2 / CENTELLA LAB, but the
    normal football experience deliberately contains no build-state wording.
    """

    def __init__(self) -> None:
        super().__init__()
        self._broadcast = pygame.font.Font(self.f12.get_name() if False else None, 18)

    def _profile_chip(self, canvas: pygame.Surface) -> None:
        # This replaces the old engine-status chip with ordinary game chrome.
        rect = pygame.Rect(1640, 944, 205, 52)
        rounded_panel(canvas, rect, (6, 11, 19), (39, 50, 68), 13, 1, 245)
        pygame.draw.circle(canvas, BLUE_L, (1665, 970), 5)
        draw_text(canvas, "PERFIL LOCAL", self.f12, (143, 158, 179), (1680, 961))

    def draw_hub(self, canvas: pygame.Surface) -> None:
        super().draw_hub(canvas)
        self._profile_chip(canvas)

        # A subtle broadcast accent ties the hero and carousel together without
        # turning the home screen into a diagnostic dashboard.
        phase = self.elapsed * 1.25
        x = 1140 + int(math.sin(phase) * 14) if self.motion() else 1140
        glow = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pygame.draw.polygon(
            glow,
            (*BRAND.sapphire, 18),
            [(x, 132), (x + 150, 132), (x - 10, 930), (x - 160, 930)],
        )
        canvas.blit(glow, (0, 0))

    def draw_quick(self, canvas: pygame.Surface, coop: bool = False) -> None:
        super().draw_quick(canvas, coop)
        # Competition-style microcopy; no engine/runtime status is shown here.
        draw_text(canvas, "CENTELLA MATCHDAY", self.f12, (124, 143, 170), (960, 626), "center")

    def draw_splash(self, canvas: pygame.Surface) -> None:
        super().draw_splash(canvas)
        # Soft lower-right broadcast bloom gives the intro more depth while
        # remaining entirely original and asset-free.
        pulse = 1.0 + (0.04 * math.sin(self.elapsed * 1.6) if self.motion() else 0.0)
        draw_glow(canvas, (1640, 820), int(210 * pulse), BLUE, 34)


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
