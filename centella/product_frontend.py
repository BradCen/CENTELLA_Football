from __future__ import annotations

import math
import time

import pygame

from .audio import UISounds
from .beta_frontend import App as BetaApp
from .brand import BRAND
from .content import TEAMS
from .runtime import launch_match
from .ui import (
    LOGICAL_SIZE,
    draw_glow,
    draw_player_silhouette,
    draw_stadium_scene,
    draw_text,
    ease_out_cubic,
    hex_color,
    rounded_panel,
)


class App(BetaApp):
    """Presentation layer on top of the functional Beta v2 shell.

    Keeping this as a subclass lets the stable shell remain small/testable while
    match-day staging can evolve rapidly without coupling it to GRF.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sfx = UISounds()
        self.pending_coop = False
        self.match_launching = False

    def start_match(self, coop: bool = False) -> None:
        if coop and len(self.controller.joysticks) < 2:
            self.notify("CO-OP LOCAL REQUIERE DOS MANDOS CONECTADOS", 4)
            return
        if not self.runtime(force=True).get("ready", False):
            self.notify("EL MOTOR NATIVO NECESITA REPARACIÓN ANTES DEL PARTIDO", 5)
            self.enter("doctor")
            return
        if self.quick["home"] == self.quick["away"]:
            self.quick["away"] = (self.quick["away"] + 1) % len(TEAMS)
        self.pending_coop = coop
        self.match_launching = False
        self.enter("prematch")
        self.sfx.play("ready")

    def _launch_pending_match(self) -> None:
        if self.match_launching:
            return
        self.match_launching = True
        self.sfx.play("ready")
        ok, msg = launch_match(
            controller_count=len(self.controller.joysticks),
            local_players=2 if self.pending_coop else 1,
            versus=self.quick["versus"] if self.pending_coop else False,
        )
        self.notify(msg, 5)
        if ok:
            # The native Gameplay Football renderer opens its own window. Keep
            # CENTELLA alive behind it instead of killing the product shell.
            try:
                pygame.display.iconify()
            except pygame.error:
                pass
            self.enter("hub")
        else:
            self.match_launching = False
            self.enter("doctor")

    def handle_action(self, action) -> None:
        if self.scene == "prematch":
            if self.elapsed < 0.22:
                return
            if action.name == "back":
                self.sfx.play("back")
                self.enter("coop" if self.pending_coop else "quick")
                return
            if action.name in ("confirm", "menu"):
                self._launch_pending_match()
                return
            return

        if action.name in ("left", "right", "up", "down"):
            self.sfx.play("nav")
        elif action.name in ("tab_left", "tab_right"):
            self.sfx.play("tab")
        elif action.name == "back":
            self.sfx.play("back")
        elif action.name == "confirm":
            self.sfx.play("confirm")
        elif self.scene == "splash":
            self.sfx.play("ready")
        super().handle_action(action)

    def draw_prematch(self, canvas: pygame.Surface) -> None:
        t = self.elapsed
        draw_stadium_scene(canvas, t, BRAND.sapphire, 1.0, self.motion())
        fade = ease_out_cubic(t / 0.7)

        dark = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        dark.fill((0, 0, 0, int(68 * fade)))
        canvas.blit(dark, (0, 0))

        home = TEAMS[self.quick["home"]]
        away = TEAMS[self.quick["away"]]
        home_override = self.user.get("team_overrides", {}).get(home.key, {})
        away_override = self.user.get("team_overrides", {}).get(away.key, {})
        home_color = hex_color(home_override.get("primary", home.primary))
        away_color = hex_color(away_override.get("primary", away.primary))
        home_name = home_override.get("name", home.name)
        away_name = away_override.get("name", away.name)

        # Human silhouettes make the stage read as a football broadcast without
        # redistributing third-party player photography or proprietary renders.
        draw_player_silhouette(canvas, 235, 1070, 0.88, home_color, int(210 * fade))
        draw_player_silhouette(canvas, 1695, 1070, 0.88, away_color, int(210 * fade))

        draw_text(canvas, "CENTELLA BROADCAST", self.f12, BRAND.sapphire_light,
                  (960, 82), "center", int(255 * fade))
        draw_text(canvas, "MATCH DAY", self.f40, BRAND.white,
                  (960, 132), "center", int(255 * fade))

        panel = pygame.Rect(420, 255, 1080, 530)
        rounded_panel(canvas, panel, (10, 14, 22), (72, 82, 102), 28, 1, int(242 * fade))
        pygame.draw.rect(canvas, (*BRAND.sapphire, int(235 * fade)),
                         (panel.x, panel.y, panel.w, 7), border_radius=4)

        for team, name, color, x in (
            (home, home_name, home_color, 680),
            (away, away_name, away_color, 1240),
        ):
            draw_glow(canvas, (x, 445), 135, color, int(90 * fade))
            pygame.draw.circle(canvas, color, (x, 445), 92)
            pygame.draw.circle(canvas, BRAND.white, (x, 445), 92, 2)
            draw_text(canvas, team.short, self.f30, BRAND.white, (x, 445), "center", int(255 * fade))
            draw_text(canvas, name, self.f24, BRAND.white, (x, 580), "center", int(255 * fade))
            draw_text(canvas, f"RATING {team.rating}", self.f12, BRAND.muted,
                      (x, 625), "center", int(235 * fade))

        draw_text(canvas, "VS", self.f52, BRAND.white, (960, 445), "center", int(255 * fade))
        pygame.draw.line(canvas, (70, 80, 98), (850, 680), (1070, 680), 1)

        info = (
            f"{self.quick['minutes']} MIN     ·     {self.quick['difficulty']}     ·     "
            f"{self.quick['time']}     ·     {self.quick['weather']}"
        )
        draw_text(canvas, info, self.f16, BRAND.muted, (960, 720), "center", int(245 * fade))

        if self.pending_coop:
            side = "P1 + P2 MISMO EQUIPO" if not self.quick["versus"] else "P1 LOCAL  ·  P2 VISITANTE"
        else:
            side = "MANDO" if self.controller.connected else "TECLADO"
        draw_text(canvas, side, self.f16, BRAND.sapphire_light,
                  (960, 825), "center", int(255 * fade))
        draw_text(canvas, self.controller.primary_name().upper(), self.f12, BRAND.muted,
                  (960, 860), "center", int(235 * fade))

        pulse = 0.7 + 0.3 * math.sin(t * 3.4) if self.motion() else 1.0
        button = pygame.Rect(665, 905, 590, 78)
        rounded_panel(canvas, button, (18, 24, 37), BRAND.sapphire_light, 18, 2, int(245 * fade))
        draw_text(canvas, "A / ENTER   SALIR AL CAMPO", self.f20, BRAND.white,
                  button.center, "center", int(255 * fade * pulse))
        self.add_region(button, "action", "confirm")

        draw_text(canvas, "B / ESC  VOLVER A CONFIGURACIÓN", self.f12, BRAND.muted,
                  (960, 1015), "center", int(230 * fade))

    def render(self) -> None:
        if self.scene != "prematch":
            return super().render()
        self.mouse_regions = []
        canvas = pygame.Surface(LOGICAL_SIZE).convert()
        self.draw_prematch(canvas)
        self.draw_message(canvas)
        self.draw_perf(canvas)
        self.viewport.present(canvas)


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
