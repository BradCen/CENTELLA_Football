from __future__ import annotations

import math

import pygame

from .brand import BRAND
from .cinematic_frontend import (
    App as CinematicApp,
    BLUE,
    BLUE_L,
    MUTED,
    PANEL,
    SOFT,
    WHITE,
)
from .content import TEAMS
from .ui import LOGICAL_SIZE, draw_glow, draw_text, rounded_panel


class App(CinematicApp):
    """Player-facing release presentation for the current CENTELLA shell.

    Engineering health remains available through F2 / CENTELLA LAB, while the
    normal football experience contains no build-state wording.
    """

    def _profile_chip(self, canvas: pygame.Surface) -> None:
        # Fully cover the inherited engineering-state area and replace it with
        # ordinary profile chrome. Technical health belongs only in CENTELLA LAB.
        cover = pygame.Rect(1605, 936, 315, 78)
        layer = pygame.Surface(cover.size, pygame.SRCALPHA)
        layer.fill((3, 7, 14, 246))
        canvas.blit(layer, cover.topleft)
        rect = pygame.Rect(1640, 946, 235, 50)
        rounded_panel(canvas, rect, (7, 12, 21), (39, 50, 68), 13, 1, 250)
        pygame.draw.circle(canvas, BLUE_L, (1666, 971), 5)
        draw_text(canvas, "PERFIL LOCAL", self.f12, (143, 158, 179), (1681, 962))

    def draw_hub(self, canvas: pygame.Surface) -> None:
        super().draw_hub(canvas)
        self._profile_chip(canvas)

        # Broadcast light adds depth behind the selected feature without turning
        # the screen into a technical dashboard.
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
        draw_text(canvas, "CENTELLA MATCHDAY", self.f12, (124, 143, 170), (960, 626), "center")

    def draw_splash(self, canvas: pygame.Surface) -> None:
        super().draw_splash(canvas)
        pulse = 1.0 + (0.04 * math.sin(self.elapsed * 1.6) if self.motion() else 0.0)
        draw_glow(canvas, (1640, 820), int(210 * pulse), BLUE, 34)

    def _choice_card(self, canvas, rect, label, value, selected, accent=BLUE):
        rounded_panel(
            canvas,
            rect,
            (247, 249, 252) if selected else PANEL,
            WHITE if selected else (47, 59, 78),
            18,
            2 if selected else 1,
            250,
        )
        if selected:
            pygame.draw.rect(canvas, accent, (rect.x, rect.y, 7, rect.h), border_radius=3)
        draw_text(canvas, label, self.f12, (83, 96, 116) if selected else MUTED, (rect.x + 24, rect.y + 20))
        draw_text(canvas, value, self.f20, accent if selected else WHITE, (rect.x + 24, rect.y + 54))

    def draw_career(self, canvas: pygame.Surface) -> None:
        """Career creation as a football presentation screen, not a settings form."""
        self.page_header(canvas, "LIGA MÁSTER 2.0", "Construye el club desde el banquillo o desde la presidencia.")

        roles = ["DIRECTOR TÉCNICO", "PRESIDENTE", "CONTROL TOTAL", "DT + PRESIDENTE CO-OP"]
        diffs = ["AMATEUR", "PROFESSIONAL", "TOP PLAYER", "LEGEND"]
        negotiations = ["FLEXIBLES", "REALISTAS", "ESTRICTAS"]
        team = TEAMS[self.career["team"]]
        team_name, team_color = self._team_identity(team)

        # Hero role card.
        role_rect = pygame.Rect(78, 330, 520, 252)
        selected = self.page_cursor == 0
        rounded_panel(canvas, role_rect, (247, 249, 252) if selected else (8, 14, 24), WHITE if selected else (49, 61, 81), 22, 2 if selected else 1, 250)
        pygame.draw.rect(canvas, team_color if selected else BLUE, (role_rect.x, role_rect.y, role_rect.w, 7), border_radius=3)
        draw_text(canvas, "TU PAPEL", self.f12, (76, 90, 111) if selected else BLUE_L, (110, 366))
        draw_text(canvas, roles[self.career["role"]], self.f30, (13, 20, 31) if selected else WHITE, (110, 410))
        draw_text(canvas, "Decide cuánto control quieres tener sobre el proyecto deportivo.", self.f16,
                  (77, 91, 111) if selected else SOFT, (110, 472))
        draw_text(canvas, "← / →  CAMBIAR ROL", self.f12, team_color if selected else MUTED, (110, 536))
        self.add_region(role_rect, "cursor", 0)

        # Club card with prominent identity.
        club_rect = pygame.Rect(628, 330, 560, 252)
        selected = self.page_cursor == 1
        rounded_panel(canvas, club_rect, (247, 249, 252) if selected else (8, 14, 24), WHITE if selected else (49, 61, 81), 22, 2 if selected else 1, 250)
        badge = (724, 456)
        draw_glow(canvas, badge, 92, team_color, 62 if selected else 38)
        pygame.draw.circle(canvas, team_color, badge, 59)
        pygame.draw.circle(canvas, WHITE, badge, 59, 2)
        draw_text(canvas, team.short, self.f20, WHITE, badge, "center")
        draw_text(canvas, "CLUB", self.f12, (78, 91, 111) if selected else BLUE_L, (818, 372))
        draw_text(canvas, team_name, self.f24, (13, 20, 31) if selected else WHITE, (818, 414))
        draw_text(canvas, team.city.upper(), self.f12, (87, 100, 119) if selected else MUTED, (818, 462))
        draw_text(canvas, f"{team.rating}  ·  {team.style.upper()}", self.f16, team_color, (818, 510))
        self.add_region(club_rect, "cursor", 1)

        # Season identity panel makes the setup feel like the opening of a mode.
        identity = pygame.Rect(1218, 330, 624, 252)
        rounded_panel(canvas, identity, (7, 12, 21), (44, 56, 75), 22, 1, 244)
        draw_text(canvas, "NUEVO PROYECTO", self.f12, BLUE_L, (1254, 367))
        draw_text(canvas, "TEMPORADA 01", self.f30, WHITE, (1254, 408))
        pygame.draw.line(canvas, team_color, (1254, 466), (1778, 466), 4)
        draw_text(canvas, "Mercado · cantera · finanzas · estadio", self.f16, SOFT, (1254, 500))
        draw_text(canvas, "Las decisiones del club se guardan en tu perfil local.", self.f12, MUTED, (1254, 539))

        # Two secondary choices and one dominant action.
        diff_rect = pygame.Rect(78, 625, 520, 118)
        self._choice_card(canvas, diff_rect, "DIFICULTAD", diffs[self.career["difficulty"]], self.page_cursor == 2, team_color)
        self.add_region(diff_rect, "cursor", 2)

        nego_rect = pygame.Rect(628, 625, 560, 118)
        self._choice_card(canvas, nego_rect, "NEGOCIACIONES", negotiations[self.career["negotiations"]], self.page_cursor == 3, team_color)
        self.add_region(nego_rect, "cursor", 3)

        start_rect = pygame.Rect(1218, 625, 624, 118)
        selected = self.page_cursor == 4
        rounded_panel(canvas, start_rect, team_color if selected else (19, 31, 50), BLUE_L, 18, 2 if selected else 1, 252)
        draw_text(canvas, "COMENZAR LIGA MÁSTER", self.f20, WHITE, start_rect.center, "center")
        self.add_region(start_rect, "cursor", 4)

        # Feature strip instead of the old debug-like bullet panel.
        features = ["MERCADO", "SCOUTING", "CANTERA", "MORAL", "FINANZAS", "ESTADIO"]
        x = 78
        for feature in features:
            rect = pygame.Rect(x, 795, 278, 80)
            rounded_panel(canvas, rect, (8, 14, 24), (42, 53, 70), 13, 1, 230)
            pygame.draw.circle(canvas, team_color, (rect.x + 23, rect.centery), 4)
            draw_text(canvas, feature, self.f12, (188, 199, 215), (rect.x + 39, rect.y + 31))
            x += 294

        draw_text(canvas, "↑ / ↓  OPCIÓN    ← / →  CAMBIAR    A  CONFIRMAR", self.f12, MUTED, (78, 930))


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
