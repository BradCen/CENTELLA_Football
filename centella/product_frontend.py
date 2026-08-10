from __future__ import annotations

import math
import time
from pathlib import Path

import pygame

from .audio import UISounds
from .beta_frontend import App as BetaApp
from .brand import BRAND
from .content import TEAMS
from .modes import MODES, TABS
from .runtime import launch_match
from .settings import SETTINGS
from .ui import (
    LOGICAL_SIZE,
    draw_glow,
    draw_stadium_scene,
    draw_text,
    ease_out_cubic,
    font,
    hex_color,
    rounded_panel,
)


TAB_LABELS = {
    "HOME": "INICIO",
    "PLAY": "JUGAR",
    "CAREER": "CARRERA",
    "ONLINE": "ONLINE",
    "CUSTOMIZE": "PERSONALIZAR",
}

HERO_COPY = {
    "HOME": ("CENTELLA FOOTBALL", "EL FÚTBOL RESPONDE A TI.",
             "Una experiencia directa, física y construida alrededor del jugador."),
    "PLAY": ("JUGAR", "ELIGE CÓMO ENTRAR AL CAMPO.",
             "Partido, entrenamiento, futsal, calle y competiciones en un mismo lugar."),
    "CAREER": ("CARRERA", "TU CLUB. TU HISTORIA.",
               "Dirige, preside o vive una carrera desde dentro del vestuario."),
    "ONLINE": ("ONLINE", "COMPITE. SIN PAY-TO-WIN.",
               "El mismo fútbol offline llevado a competición y comunidad."),
    "CUSTOMIZE": ("PERSONALIZAR", "HAZLO TUYO.",
                  "Equipos, jugadores, competiciones, controles y rendimiento."),
}


class App(BetaApp):
    """CENTELLA Football professional presentation v3."""

    def __init__(self) -> None:
        super().__init__()
        self.sfx = UISounds()
        self.pending_coop = False
        self.match_launching = False
        self._selection_seen = -1
        self._selection_changed_at = time.perf_counter()
        self._tab_changed_at = time.perf_counter()
        self._display_logo = font(48, True)
        self._display_hero = font(74, True)
        self._display_big = font(104, True)
        self._display_card = font(28, True)
        self._fit_window_to_desktop()

    def _fit_window_to_desktop(self) -> None:
        """Prevent the default 1600x900 window from overflowing small desktops."""
        if SETTINGS.get("display.fullscreen", False):
            return
        try:
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except (IndexError, pygame.error, AttributeError):
            info = pygame.display.Info()
            desktop_w, desktop_h = info.current_w, info.current_h

        current_w, current_h = self.screen.get_size()
        max_w = max(960, int(desktop_w * 0.92))
        max_h = max(540, int(desktop_h * 0.88))
        scale = min(1.0, max_w / max(current_w, 1), max_h / max(current_h, 1))
        if scale >= 0.999:
            return

        new_w = max(960, int(current_w * scale))
        new_h = max(540, int(current_h * scale))
        if new_w / new_h > 16 / 9:
            new_w = int(new_h * 16 / 9)
        else:
            new_h = int(new_w * 9 / 16)
        self.screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE | pygame.DOUBLEBUF)
        self.viewport.screen = self.screen
        self.viewport.update()

    def set_tab(self, index):
        before = self.tab
        super().set_tab(index)
        if self.tab != before:
            self._tab_changed_at = time.perf_counter()

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

        old_selected = self.selected
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
        if self.scene == "hub" and self.selected != old_selected:
            self._selection_seen = self.selected
            self._selection_changed_at = time.perf_counter()

    def _draw_stage(self, canvas: pygame.Surface, intensity: float = 1.0) -> None:
        draw_stadium_scene(canvas, self.elapsed, BRAND.sapphire, intensity, self.motion())
        t = self.elapsed
        veil = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        veil.fill((2, 4, 10, 72))
        canvas.blit(veil, (0, 0))

        cx, cy = 1510, 445
        pulse = 1.0 + (0.025 * math.sin(t * 1.6) if self.motion() else 0.0)
        for radius, alpha, width in ((330, 24, 2), (260, 38, 2), (190, 55, 3)):
            r = int(radius * pulse)
            pygame.draw.arc(canvas, (*BRAND.sapphire_light, alpha),
                            pygame.Rect(cx - r, cy - r, r * 2, r * 2),
                            math.radians(198), math.radians(518), width)

        panes = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shift = int((math.sin(t * 0.45) * 24) if self.motion() else 0)
        pygame.draw.polygon(panes, (*BRAND.sapphire, 24),
                            [(1110 + shift, 0), (1450 + shift, 0),
                             (1120 + shift, 1080), (780 + shift, 1080)])
        pygame.draw.polygon(panes, (255, 255, 255, 10),
                            [(1500 - shift, 0), (1690 - shift, 0),
                             (1480 - shift, 1080), (1290 - shift, 1080)])
        canvas.blit(panes, (0, 0))

        vignette = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pygame.draw.rect(vignette, (0, 0, 0, 54), vignette.get_rect(), width=90)
        canvas.blit(vignette, (0, 0))

    def draw_brand(self, canvas, x=96, y=58):
        draw_text(canvas, "CENTELLA", self._display_logo, BRAND.white, (x, y))
        draw_text(canvas, "F O O T B A L L", self.f12, BRAND.sapphire_light, (x + 2, y + 54))

    def draw_tabs(self, canvas):
        x = 650
        for i, name in enumerate(TABS):
            label = TAB_LABELS.get(name, name)
            selected = i == self.tab
            color = BRAND.white if selected else (136, 147, 166)
            rect = draw_text(canvas, label, self.f20, color, (x, 70))
            hit = pygame.Rect(rect.x - 18, rect.y - 16, rect.w + 36, 60)
            if selected:
                pygame.draw.rect(canvas, BRAND.sapphire_light,
                                 (rect.x, rect.bottom + 11, rect.w, 4), border_radius=2)
            self.add_region(hit, "tab", i)
            x = rect.right + 48
        draw_text(canvas, self.controller.primary_name().upper(), self.f16,
                  (145, 155, 174), (1820, 73), "topright")

    def page_header(self, canvas, title, subtitle=""):
        self._draw_stage(canvas, 0.62)
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 68))
        canvas.blit(overlay, (0, 0))
        self.draw_brand(canvas)
        self.draw_tabs(canvas)

        p = ease_out_cubic(self.elapsed / 0.28)
        x = int(96 + (1 - p) * 34)
        draw_text(canvas, title, self._display_hero, BRAND.white, (x, 178), alpha=int(255 * p))
        if subtitle:
            draw_text(canvas, subtitle, self.f20, (171, 182, 198), (x + 3, 263), alpha=int(255 * p))
        pygame.draw.line(canvas, (*BRAND.sapphire, int(210 * p)), (96, 310), (1824, 310), 2)

    def option(self, canvas, y, label, value, index):
        selected = self.page_cursor == index
        rect = pygame.Rect(96, y, 1040, 70)
        if selected:
            rounded_panel(canvas, rect, (242, 245, 249), (255, 255, 255), 14, 1, 252)
            pygame.draw.rect(canvas, BRAND.sapphire, (rect.x, rect.y, 7, rect.h), border_radius=3)
            label_color = (17, 23, 34)
            value_color = BRAND.sapphire
        else:
            rounded_panel(canvas, rect, (10, 15, 25), (48, 58, 74), 14, 1, 220)
            label_color = (211, 218, 229)
            value_color = (151, 164, 184)
        draw_text(canvas, label, self.f20, label_color, (124, y + 17))
        draw_text(canvas, str(value), self.f20, value_color, (1098, y + 17), "topright")
        self.add_region(rect, "cursor", index)

    def _draw_wrapped(self, canvas, text, fnt, color, rect, max_lines=2, line_gap=4):
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if fnt.size(candidate)[0] <= rect.w:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) == max_lines and words:
            rendered_words = " ".join(lines).split()
            if len(rendered_words) < len(words):
                last = lines[-1]
                while last and fnt.size(last + "…")[0] > rect.w:
                    last = last[:-1]
                lines[-1] = last.rstrip() + "…"
        y = rect.y
        for line in lines:
            draw_text(canvas, line, fnt, color, (rect.x, y))
            y += fnt.get_linesize() + line_gap

    def draw_bottom(self, canvas):
        if self.scene in ("splash", "prematch"):
            return
        pygame.draw.line(canvas, (45, 54, 70), (62, 1022), (1858, 1022), 1)
        draw_text(canvas, "B / ESC   VOLVER", self.f16, (142, 153, 170), (74, 1038))
        draw_text(canvas, self.controller.ui_hint(), self.f16, (221, 226, 235), (1846, 1038), "topright")

    def _draw_scene_transition(self, canvas):
        if self.scene == "splash" or self.elapsed >= 0.22:
            return
        p = ease_out_cubic(self.elapsed / 0.22)
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, int(150 * (1 - p))))
        canvas.blit(shade, (0, 0))
        x = int(1920 * p)
        pygame.draw.rect(canvas, (*BRAND.sapphire_light, int(210 * (1 - p))), (x - 4, 0, 4, 1080))

    def draw_splash(self, canvas):
        t = self.elapsed
        self._draw_stage(canvas, 1.1)
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pygame.draw.polygon(shade, (0, 0, 0, 120), [(0, 0), (1250, 0), (980, 1080), (0, 1080)])
        canvas.blit(shade, (0, 0))

        a = ease_out_cubic((t - 0.08) / 0.45)
        b = ease_out_cubic((t - 0.35) / 0.55)
        cta = ease_out_cubic((t - 1.05) / 0.48)
        draw_text(canvas, "CENTELLA", self._display_big, BRAND.white, (190, 378), alpha=int(255 * a))
        pygame.draw.rect(canvas, (*BRAND.sapphire_light, int(255 * b)), (196, 518, 122, 6), border_radius=3)
        draw_text(canvas, "F O O T B A L L", self.f24, BRAND.sapphire_light, (196, 552), alpha=int(255 * b))
        draw_text(canvas, "THE GAME STARTS WITH YOUR INPUT", self.f12, (126, 140, 160), (198, 608), alpha=int(230 * b))

        center = (1470, 430)
        for r, alpha in ((230, 70), (170, 95), (110, 130)):
            draw_glow(canvas, center, r, BRAND.sapphire, int(alpha * b))
        pygame.draw.circle(canvas, BRAND.sapphire_light, center, 84, 3)
        pygame.draw.circle(canvas, (238, 244, 255), center, 10)
        for ang in range(0, 360, 60):
            rad = math.radians(ang + (t * 8 if self.motion() else 0))
            p1 = (center[0] + int(math.cos(rad) * 36), center[1] + int(math.sin(rad) * 36))
            p2 = (center[0] + int(math.cos(rad) * 78), center[1] + int(math.sin(rad) * 78))
            pygame.draw.line(canvas, BRAND.sapphire_light, p1, p2, 2)

        pulse = 0.82 + 0.18 * math.sin(t * 3.1) if self.motion() else 1.0
        button = pygame.Rect(190, 820, 570, 76)
        rounded_panel(canvas, button, (13, 18, 29), (82, 112, 172), 18, 1, int(238 * cta))
        draw_text(canvas, "PRESIONA CUALQUIER BOTÓN", self.f20, BRAND.white,
                  button.center, "center", int(255 * cta * pulse))
        draw_text(canvas, self.controller.primary_name().upper(), self.f12, (127, 139, 157),
                  (button.centerx, 930), "center", int(235 * cta))
        draw_text(canvas, "© CENTELLA TECHNOLOGIES", self.f12, (76, 88, 107),
                  (190, 1005), alpha=int(220 * cta))

    def draw_hub(self, canvas):
        self._draw_stage(canvas, 1.0)
        self.draw_brand(canvas)
        self.draw_tabs(canvas)

        if self._selection_seen != self.selected:
            self._selection_seen = self.selected
            self._selection_changed_at = time.perf_counter()
        selection_p = ease_out_cubic((time.perf_counter() - self._selection_changed_at) / 0.20)
        tab_p = ease_out_cubic((time.perf_counter() - self._tab_changed_at) / 0.28)

        eyebrow, title, subtitle = HERO_COPY[self.tab_name]
        hero_x = int(96 + (1 - tab_p) * 36)
        draw_text(canvas, eyebrow, self.f20, BRAND.sapphire_light, (hero_x, 186), alpha=int(255 * tab_p))
        draw_text(canvas, title, self._display_hero, BRAND.white, (hero_x, 232), alpha=int(255 * tab_p))
        draw_text(canvas, subtitle, self.f20, (174, 185, 201), (hero_x + 3, 326), alpha=int(245 * tab_p))

        panel = pygame.Rect(1255, 210, 560, 360)
        rounded_panel(canvas, panel, (8, 13, 23), (40, 52, 72), 28, 1, 205)
        draw_text(canvas, "CENTELLA MATCH ENGINE", self.f12, BRAND.sapphire_light, (1294, 252))
        draw_text(canvas, "IMMEDIATE", self.f30, BRAND.white, (1294, 304))
        draw_text(canvas, "TO COMMAND.", self.f30, BRAND.white, (1294, 350))
        draw_text(canvas, "PHYSICAL", self.f30, (164, 177, 197), (1294, 410))
        draw_text(canvas, "AFTER THE COMMAND.", self.f30, (164, 177, 197), (1294, 456))
        pygame.draw.line(canvas, BRAND.sapphire, (1294, 522), (1768, 522), 3)

        modes = MODES[self.tab_name]
        visible = 4
        start = max(0, min(self.selected - 1, max(0, len(modes) - visible)))
        safe_x, gap, card_w, card_h, base_y = 96, 18, 414, 232, 698
        for slot, mode in enumerate(modes[start:start + visible]):
            idx = start + slot
            selected = idx == self.selected
            lift = int((1 - selection_p) * 18) if selected else 0
            y = base_y - (12 if selected else 0) + lift
            rect = pygame.Rect(safe_x + slot * (card_w + gap), y, card_w, card_h)

            if selected:
                rounded_panel(canvas, rect, (244, 247, 251), (255, 255, 255), 18, 1, 255)
                pygame.draw.rect(canvas, BRAND.sapphire, (rect.x, rect.y, rect.w, 7), border_radius=4)
                title_color, sub_color, small_color = (16, 22, 33), (77, 89, 108), BRAND.sapphire
            else:
                rounded_panel(canvas, rect, (10, 15, 24), (46, 55, 72), 18, 1, 220)
                title_color, sub_color, small_color = (222, 228, 237), (123, 137, 157), (105, 121, 145)

            draw_text(canvas, f"{idx + 1:02d}", self.f12, small_color, (rect.x + 26, rect.y + 24))
            draw_text(canvas, mode.title, self._display_card, title_color, (rect.x + 26, rect.y + 61))
            draw_text(canvas, mode.subtitle, self.f20, sub_color, (rect.x + 26, rect.y + 108))
            if selected:
                self._draw_wrapped(canvas, mode.description, self.f16, (92, 104, 122),
                                   pygame.Rect(rect.x + 26, rect.y + 151, rect.w - 52, 48),
                                   max_lines=2, line_gap=1)
                draw_text(canvas, "A / ENTER  ABRIR", self.f16, BRAND.sapphire,
                          (rect.x + 26, rect.bottom - 29))
            self.add_region(rect, "mode", mode)

        for i in range(len(modes)):
            x = 96 + i * 16
            pygame.draw.rect(canvas,
                             BRAND.sapphire_light if i == self.selected else (67, 76, 92),
                             (x, 962, 10 if i == self.selected else 6, 3), border_radius=2)
        draw_text(canvas, "PLAYER 1", self.f12, (122, 136, 156), (1818, 960), "topright")

    def _team_identity(self, team):
        overrides = self.user.get("team_overrides", {}).get(team.key, {})
        return overrides.get("name", team.name), hex_color(overrides.get("primary", team.primary))

    def _draw_team_badge(self, canvas, team, center, selected=False):
        name, color = self._team_identity(team)
        draw_glow(canvas, center, 145 if selected else 120, color, 75 if selected else 46)
        pygame.draw.circle(canvas, (13, 18, 29), center, 104)
        pygame.draw.circle(canvas, color, center, 98, 8)
        pygame.draw.circle(canvas, (226, 233, 244), center, 98, 2)
        draw_text(canvas, team.short, self.f30, BRAND.white, center, "center")
        draw_text(canvas, name, self.f20, BRAND.white, (center[0], center[1] + 137), "center")
        draw_text(canvas, f"{team.rating}", self.f30, color, (center[0], center[1] + 183), "center")

    def draw_quick(self, canvas, coop=False):
        self.page_header(canvas, "CO-OP LOCAL" if coop else "PATADA INICIAL",
                         "Configura lo esencial y entra al campo.")
        home = TEAMS[self.quick["home"]]
        away = TEAMS[self.quick["away"]]

        match_panel = pygame.Rect(96, 348, 1728, 330)
        rounded_panel(canvas, match_panel, (7, 12, 21), (44, 54, 71), 24, 1, 225)
        pygame.draw.rect(canvas, BRAND.sapphire, (match_panel.x, match_panel.y, match_panel.w, 5), border_radius=3)
        home_selected, away_selected = self.page_cursor == 0, self.page_cursor == 1
        self._draw_team_badge(canvas, home, (410, 490), home_selected)
        self._draw_team_badge(canvas, away, (1510, 490), away_selected)
        draw_text(canvas, "VS", self._display_hero, (218, 224, 234), (960, 475), "center")
        draw_text(canvas, "LOCAL", self.f12, BRAND.sapphire_light, (410, 390), "center")
        draw_text(canvas, "VISITANTE", self.f12, BRAND.sapphire_light, (1510, 390), "center")

        home_hit, away_hit = pygame.Rect(236, 382, 350, 275), pygame.Rect(1334, 382, 350, 275)
        self.add_region(home_hit, "cursor", 0)
        self.add_region(away_hit, "cursor", 1)
        if home_selected:
            pygame.draw.rect(canvas, BRAND.sapphire_light, home_hit, 2, border_radius=20)
        if away_selected:
            pygame.draw.rect(canvas, BRAND.sapphire_light, away_hit, 2, border_radius=20)

        settings = [("DURACIÓN", f"{self.quick['minutes']} MIN"),
                    ("DIFICULTAD", self.quick["difficulty"]),
                    ("HORA", self.quick["time"]), ("CLIMA", self.quick["weather"])]
        x0, y, gap, w = 96, 720, 16, 420
        for offset, (label, value) in enumerate(settings):
            idx = 2 + offset
            selected = self.page_cursor == idx
            rect = pygame.Rect(x0 + offset * (w + gap), y, w, 92)
            if selected:
                rounded_panel(canvas, rect, (242, 245, 249), (255, 255, 255), 16, 1, 252)
                lc, vc = (72, 83, 102), BRAND.sapphire
            else:
                rounded_panel(canvas, rect, (11, 16, 26), (48, 57, 72), 16, 1, 228)
                lc, vc = (121, 136, 156), (225, 230, 238)
            draw_text(canvas, label, self.f12, lc, (rect.x + 22, rect.y + 17))
            draw_text(canvas, value, self.f20, vc, (rect.x + 22, rect.y + 45))
            self.add_region(rect, "cursor", idx)

        if coop:
            idx = 6
            side_rect = pygame.Rect(96, 836, 570, 78)
            selected = self.page_cursor == idx
            rounded_panel(canvas, side_rect,
                          (242, 245, 249) if selected else (11, 16, 26),
                          (255, 255, 255) if selected else (48, 57, 72), 15, 1, 245)
            draw_text(canvas, "P1 + P2", self.f12,
                      (73, 84, 103) if selected else (125, 139, 159),
                      (side_rect.x + 22, side_rect.y + 16))
            side = "VERSUS" if self.quick["versus"] else "MISMO EQUIPO"
            draw_text(canvas, side, self.f16,
                      BRAND.sapphire if selected else BRAND.white,
                      (side_rect.x + 22, side_rect.y + 44))
            self.add_region(side_rect, "cursor", idx)

        play_rect = pygame.Rect(1264, 836, 560, 78)
        selected = self.page_cursor == 7
        rounded_panel(canvas, play_rect,
                      BRAND.sapphire if selected else (20, 29, 45),
                      BRAND.sapphire_light, 16, 2 if selected else 1, 250)
        draw_text(canvas, "JUGAR PARTIDO", self.f20, BRAND.white, play_rect.center, "center")
        self.add_region(play_rect, "cursor", 7)
        device_text = f"{len(self.controller.joysticks)} MANDO(S)" if self.controller.joysticks else "TECLADO"
        draw_text(canvas, device_text, self.f12, (121, 135, 154), (960, 944), "center")

    def draw_doctor(self, canvas):
        self.page_header(canvas, "SISTEMA", "Estado del runtime local y reparación del motor.")
        data = self.runtime()
        ready = data.get("ready", False)
        status = "LISTO PARA JUGAR" if ready else "MOTOR PENDIENTE"
        status_color = (107, 218, 158) if ready else (244, 183, 77)
        draw_text(canvas, status, self.f30, status_color, (96, 360))
        y = 430
        for p in data.get("runtimes", [])[:3]:
            mods = p.get("modules") or {}
            engine = bool(p.get("engine"))
            rect = pygame.Rect(96, y, 1100, 116)
            rounded_panel(canvas, rect, (9, 14, 23), (45, 55, 71), 16, 1, 225)
            draw_text(canvas, f"PYTHON {p.get('version','—')}", self.f20, BRAND.white, (124, y + 22))
            summary = "  ·  ".join(f"{m.upper()} {'OK' if mods.get(m) else '—'}"
                                   for m in ("pygame", "numpy", "absl", "gfootball_engine"))
            draw_text(canvas, summary, self.f12,
                      (109, 213, 158) if engine else (154, 166, 184), (124, y + 68))
            y += 132

        buttons = [("VOLVER A COMPROBAR", "Actualiza el diagnóstico"),
                   ("REPARAR MOTOR", "Abre el instalador de Windows")]
        for i, (title, subtitle) in enumerate(buttons):
            rect = pygame.Rect(1265, 430 + i * 145, 559, 116)
            selected = self.page_cursor == i
            rounded_panel(canvas, rect,
                          (242, 245, 249) if selected else (10, 15, 25),
                          (255, 255, 255) if selected else (48, 57, 72), 18, 1, 245)
            draw_text(canvas, title, self.f20,
                      (18, 24, 36) if selected else BRAND.white, (rect.x + 28, rect.y + 24))
            draw_text(canvas, subtitle, self.f12,
                      BRAND.sapphire if selected else (127, 140, 160), (rect.x + 28, rect.y + 70))
            self.add_region(rect, "cursor", i)
        draw_text(canvas, "Esta pantalla es técnica y no aparece como modo de juego.",
                  self.f12, (113, 126, 145), (96, 922))

    def draw_prematch(self, canvas: pygame.Surface) -> None:
        t = self.elapsed
        self._draw_stage(canvas, 1.15)
        fade = ease_out_cubic(t / 0.55)
        home = TEAMS[self.quick["home"]]
        away = TEAMS[self.quick["away"]]
        home_name, home_color = self._team_identity(home)
        away_name, away_color = self._team_identity(away)

        draw_text(canvas, "CENTELLA FOOTBALL", self.f12, BRAND.sapphire_light,
                  (960, 92), "center", int(255 * fade))
        draw_text(canvas, "MATCH DAY", self._display_hero, BRAND.white,
                  (960, 150), "center", int(255 * fade))

        left, right = pygame.Rect(140, 300, 720, 470), pygame.Rect(1060, 300, 720, 470)
        for rect, team, name, color, align in (
            (left, home, home_name, home_color, "left"),
            (right, away, away_name, away_color, "right"),
        ):
            rounded_panel(canvas, rect, (8, 13, 22), (48, 58, 74), 26, 1, int(236 * fade))
            edge_x = rect.x if align == "left" else rect.right - 8
            pygame.draw.rect(canvas, (*color, int(245 * fade)),
                             (edge_x, rect.y, 8, rect.h), border_radius=3)
            center = (rect.centerx, rect.y + 190)
            draw_glow(canvas, center, 150, color, int(90 * fade))
            pygame.draw.circle(canvas, (13, 18, 29), center, 106)
            pygame.draw.circle(canvas, color, center, 100, 8)
            pygame.draw.circle(canvas, BRAND.white, center, 100, 2)
            draw_text(canvas, team.short, self.f30, BRAND.white, center, "center", int(255 * fade))
            draw_text(canvas, name, self.f30, BRAND.white,
                      (rect.centerx, rect.y + 330), "center", int(255 * fade))
            draw_text(canvas, f"RATING {team.rating}", self.f12, (139, 152, 172),
                      (rect.centerx, rect.y + 382), "center", int(240 * fade))

        draw_text(canvas, "VS", self._display_big, (230, 234, 241),
                  (960, 512), "center", int(245 * fade))
        info = (f"{self.quick['minutes']} MIN   ·   {self.quick['difficulty']}   ·   "
                f"{self.quick['time']}   ·   {self.quick['weather']}")
        draw_text(canvas, info, self.f20, (171, 183, 201),
                  (960, 820), "center", int(245 * fade))
        button = pygame.Rect(660, 888, 600, 82)
        pulse = 0.88 + 0.12 * math.sin(t * 3.4) if self.motion() else 1.0
        rounded_panel(canvas, button, BRAND.sapphire, BRAND.sapphire_light, 18, 2, int(250 * fade))
        draw_text(canvas, "SALIR AL CAMPO", self.f20, BRAND.white,
                  button.center, "center", int(255 * fade * pulse))
        self.add_region(button, "action", "confirm")
        draw_text(canvas, "B / ESC  VOLVER", self.f12, (121, 134, 154),
                  (960, 1012), "center", int(235 * fade))

    def render(self) -> None:
        self.mouse_regions = []
        canvas = pygame.Surface(LOGICAL_SIZE).convert()
        scene_map = {
            "splash": self.draw_splash,
            "hub": self.draw_hub,
            "quick": lambda c: self.draw_quick(c, False),
            "coop": lambda c: self.draw_quick(c, True),
            "training": self.draw_training,
            "career": self.draw_career,
            "street": self.draw_street,
            "journey": self.draw_journey,
            "online": self.draw_online,
            "edit": self.draw_edit,
            "player": self.draw_player,
            "tournament": self.draw_tournament,
            "setpiece": self.draw_setpiece,
            "controls": self.draw_controls,
            "video": self.draw_video,
            "access": self.draw_access,
            "workshop": self.draw_workshop,
            "doctor": self.draw_doctor,
            "detail": self.draw_detail,
            "prematch": self.draw_prematch,
        }
        scene_map.get(self.scene, self.draw_hub)(canvas)
        if self.scene not in ("splash", "prematch"):
            self.draw_bottom(canvas)
        self.draw_message(canvas)
        self.draw_perf(canvas)
        self._draw_scene_transition(canvas)
        self.viewport.present(canvas)


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
