from __future__ import annotations

import math
import time

import pygame

from .brand import BRAND
from .content import TEAMS
from .modes import MODES, TABS
from .product_frontend import App as ProductApp, HERO_COPY, TAB_LABELS
from .ui import LOGICAL_SIZE, draw_glow, draw_text, ease_out_cubic, font, hex_color, rounded_panel


BG = (3, 7, 14)
PANEL = (10, 16, 27)
PANEL_2 = (15, 23, 38)
MUTED = (141, 154, 174)
SOFT = (201, 210, 223)
WHITE = (247, 249, 252)
BLUE = BRAND.sapphire
BLUE_L = BRAND.sapphire_light


class App(ProductApp):
    """CENTELLA Football cinematic presentation layer.

    Keeps the tested controller, routing, settings and match-launch logic from
    ProductApp while replacing the first-impression screens with a game-first
    visual language closer to a modern console football title.
    """

    def __init__(self) -> None:
        super().__init__()
        self._hero_mega = font(90, True)
        self._hero_title = font(60, True)
        self._tile_title = font(31, True)
        self._score_font = font(82, True)
        self._thin = font(18)
        self._last_hover = -1

    # ------------------------------------------------------------------
    # Cinematic world
    # ------------------------------------------------------------------
    def _gradient(self, canvas, top=(2, 5, 12), bottom=(8, 18, 34)):
        w, h = LOGICAL_SIZE
        for y in range(0, h, 8):
            t = y / h
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.rect(canvas, c, (0, y, w, 9))

    def _draw_stadium_world(self, canvas, mood=1.0, tunnel=False):
        """Original procedural stadium/tunnel stage with parallax-like motion."""
        self._gradient(canvas)
        t = self.elapsed
        sway = int(math.sin(t * 0.27) * 22) if self.motion() else 0
        w, h = LOGICAL_SIZE

        # Stadium roof / darkness above the floodlights.
        pygame.draw.polygon(canvas, (4, 7, 13), [(0, 0), (w, 0), (w, 270), (0, 330)])
        pygame.draw.polygon(canvas, (8, 13, 22), [(0, 285), (w, 230), (w, 350), (0, 402)])

        # Floodlight rigs and blooms.
        for i, x in enumerate((190, 535, 1380, 1735)):
            px = x + (sway if i < 2 else -sway)
            pygame.draw.line(canvas, (39, 48, 62), (px, 110), (px, 310), 8)
            pygame.draw.rect(canvas, (180, 196, 220), (px - 84, 95, 168, 18), border_radius=4)
            for lx in range(px - 70, px + 71, 28):
                draw_glow(canvas, (lx, 105), 95, (145, 184, 255), int(42 * mood))
                pygame.draw.circle(canvas, (234, 242, 255), (lx, 105), 3)

        # Crowd bowls as layered horizontal bands instead of a tech-grid.
        pygame.draw.polygon(canvas, (9, 16, 28), [(0, 365), (w, 310), (w, 595), (0, 650)])
        pygame.draw.polygon(canvas, (13, 21, 35), [(0, 450), (w, 400), (w, 665), (0, 715)])
        for row_y in range(430, 640, 30):
            pygame.draw.line(canvas, (32, 43, 60), (0, row_y), (w, row_y - 40), 2)
            for x in range((row_y * 3) % 31, w, 37):
                pulse = 35 + int(18 * (0.5 + 0.5 * math.sin(t * 1.8 + x * 0.02))) if self.motion() else 42
                pygame.draw.circle(canvas, (pulse, pulse + 7, pulse + 14), (x, row_y - int(x / w * 40)), 2)

        # Pitch plane in perspective.
        horizon = 600
        pitch = [(155, 1080), (1765, 1080), (1292, horizon), (628, horizon)]
        pygame.draw.polygon(canvas, (9, 57, 42), pitch)
        stripe = [(155, 1080), (480, 1080), (760, horizon), (628, horizon)]
        pygame.draw.polygon(canvas, (10, 67, 48), stripe)
        stripe2 = [(805, 1080), (1115, 1080), (1030, horizon), (890, horizon)]
        pygame.draw.polygon(canvas, (10, 66, 47), stripe2)
        stripe3 = [(1440, 1080), (1765, 1080), (1292, horizon), (1160, horizon)]
        pygame.draw.polygon(canvas, (10, 66, 47), stripe3)
        line = (180, 210, 196)
        pygame.draw.aaline(canvas, line, (960, horizon), (960, 1080))
        pygame.draw.aaline(canvas, line, (628, horizon), (155, 1080))
        pygame.draw.aaline(canvas, line, (1292, horizon), (1765, 1080))
        pygame.draw.ellipse(canvas, line, (805, 645, 310, 128), 2)

        # Blue broadcast light sweeping through the scene.
        beam = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        offset = int(((t * 70) % 2500) - 500) if self.motion() else 870
        pygame.draw.polygon(beam, (*BLUE, int(34 * mood)), [(offset, 0), (offset + 300, 0), (offset + 650, 1080), (offset + 160, 1080)])
        canvas.blit(beam, (0, 0))

        if tunnel:
            # Add a player-tunnel framing layer to the startup screen.
            shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
            pygame.draw.polygon(shade, (0, 0, 0, 188), [(0, 0), (560, 0), (770, 1080), (0, 1080)])
            pygame.draw.polygon(shade, (0, 0, 0, 188), [(1360, 0), (1920, 0), (1920, 1080), (1150, 1080)])
            canvas.blit(shade, (0, 0))
            for x in (552, 1368):
                pygame.draw.line(canvas, (41, 61, 95), (x, 0), (760 if x < 960 else 1160, 1080), 5)

        # Cinematic vignette.
        vignette = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pygame.draw.rect(vignette, (0, 0, 0, 72), vignette.get_rect(), width=120)
        canvas.blit(vignette, (0, 0))

    def _draw_player_figure(self, canvas, center=(1480, 840), scale=1.0, flip=False, alpha=235):
        """Stylised footballer built from vector primitives; no third-party asset."""
        layer = pygame.Surface((560, 820), pygame.SRCALPHA)
        c = (8, 13, 23, alpha)
        rim = (*BLUE_L, int(alpha * 0.7))
        pygame.draw.ellipse(layer, c, (225, 24, 110, 125))
        pygame.draw.rect(layer, c, (247, 130, 68, 68), border_radius=18)
        torso = [(168, 190), (385, 185), (420, 455), (340, 545), (205, 545), (130, 450)]
        pygame.draw.polygon(layer, c, torso)
        pygame.draw.lines(layer, rim, True, torso, 3)
        pygame.draw.polygon(layer, c, [(168, 208), (91, 250), (30, 470), (77, 486), (170, 340)])
        pygame.draw.polygon(layer, c, [(382, 205), (456, 250), (520, 438), (474, 462), (380, 338)])
        pygame.draw.polygon(layer, c, [(201, 527), (341, 527), (357, 620), (293, 638), (270, 585), (247, 640), (181, 620)])
        pygame.draw.polygon(layer, c, [(183, 610), (250, 620), (220, 808), (159, 808)])
        pygame.draw.polygon(layer, c, [(293, 618), (358, 603), (402, 800), (342, 814)])
        pygame.draw.polygon(layer, (*BLUE, int(alpha * 0.88)), [(155, 260), (401, 216), (412, 260), (165, 304)])
        if flip:
            layer = pygame.transform.flip(layer, True, False)
        if scale != 1.0:
            layer = pygame.transform.smoothscale(layer, (int(560 * scale), int(820 * scale)))
        rect = layer.get_rect(midbottom=center)
        canvas.blit(layer, rect)

    # ------------------------------------------------------------------
    # Shared navigation chrome
    # ------------------------------------------------------------------
    def draw_brand(self, canvas, x=72, y=48):
        draw_text(canvas, "CENTELLA", self._display_logo, WHITE, (x, y))
        pygame.draw.rect(canvas, BLUE_L, (x + 2, y + 57, 88, 4), border_radius=2)
        draw_text(canvas, "FOOTBALL", self.f12, (165, 182, 209), (x + 106, y + 50))

    def draw_tabs(self, canvas):
        x = 615
        for i, name in enumerate(TABS):
            label = TAB_LABELS.get(name, name)
            selected = i == self.tab
            color = WHITE if selected else (127, 140, 160)
            rect = draw_text(canvas, label, self.f16, color, (x, 67))
            hit = pygame.Rect(rect.x - 18, 42, rect.w + 36, 64)
            if selected:
                pygame.draw.rect(canvas, BLUE_L, (rect.x - 2, 98, rect.w + 4, 4), border_radius=2)
            self.add_region(hit, "tab", i)
            x = rect.right + 54

        # Device/profile feels like game chrome, not a diagnostic label.
        pygame.draw.circle(canvas, (20, 30, 48), (1758, 72), 26)
        draw_text(canvas, "P1", self.f12, WHITE, (1758, 72), "center")
        draw_text(canvas, "PLAYER 1", self.f12, MUTED, (1800, 65))

    def draw_bottom(self, canvas):
        if self.scene in ("splash", "prematch"):
            return
        footer = pygame.Surface((1920, 56), pygame.SRCALPHA)
        footer.fill((2, 5, 11, 216))
        canvas.blit(footer, (0, 1024))
        draw_text(canvas, "B  VOLVER", self.f12, MUTED, (74, 1044))
        draw_text(canvas, "A  SELECCIONAR", self.f12, WHITE, (174, 1044))
        draw_text(canvas, "LB / RB  SECCIONES", self.f12, MUTED, (1840, 1044), "topright")

    def page_header(self, canvas, title, subtitle=""):
        self._draw_stadium_world(canvas, 0.72)
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 70))
        canvas.blit(overlay, (0, 0))
        self.draw_brand(canvas)
        self.draw_tabs(canvas)
        p = ease_out_cubic(self.elapsed / 0.30)
        x = int(78 + (1.0 - p) * 42)
        draw_text(canvas, title, self._hero_title, WHITE, (x, 164), alpha=int(255 * p))
        if subtitle:
            draw_text(canvas, subtitle, self.f16, SOFT, (x + 3, 242), alpha=int(245 * p))

    # ------------------------------------------------------------------
    # Intro
    # ------------------------------------------------------------------
    def draw_splash(self, canvas):
        t = self.elapsed
        self._draw_stadium_world(canvas, 1.15, tunnel=True)
        self._draw_player_figure(canvas, (1540, 1075), 1.08, False, 245)

        wash = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pygame.draw.polygon(wash, (0, 0, 0, 108), [(0, 0), (1190, 0), (910, 1080), (0, 1080)])
        canvas.blit(wash, (0, 0))

        p1 = ease_out_cubic((t - 0.10) / 0.55)
        p2 = ease_out_cubic((t - 0.48) / 0.62)
        p3 = ease_out_cubic((t - 1.15) / 0.48)

        draw_text(canvas, "CENTELLA", self._hero_mega, WHITE, (150, 360), alpha=int(255 * p1))
        pygame.draw.rect(canvas, (*BLUE_L, int(255 * p2)), (156, 480, 116, 7), border_radius=3)
        draw_text(canvas, "F O O T B A L L", self.f24, (210, 224, 247), (156, 520), alpha=int(255 * p2))
        draw_text(canvas, "TU FÚTBOL. TU DECISIÓN.", self.f16, (139, 156, 181), (158, 578), alpha=int(230 * p2))

        # Large, console-like CTA with a single clear affordance.
        pulse = 0.88 + 0.12 * math.sin(t * 3.0) if self.motion() else 1.0
        cta = pygame.Rect(152, 788, 515, 72)
        rounded_panel(canvas, cta, (247, 249, 252), (255, 255, 255), 12, 1, int(255 * p3))
        pygame.draw.rect(canvas, (*BLUE, int(255 * p3)), (cta.x, cta.y, 8, cta.h), border_radius=3)
        draw_text(canvas, "PRESIONA CUALQUIER BOTÓN", self.f16, (12, 19, 31), cta.center, "center", int(255 * p3 * pulse))
        draw_text(canvas, self.controller.primary_name().upper(), self.f12, (128, 143, 165), (cta.centerx, 890), "center", int(225 * p3))
        draw_text(canvas, "BETA EXPERIENCE", self.f12, (84, 99, 121), (152, 1003), alpha=int(220 * p3))

    # ------------------------------------------------------------------
    # Main hub
    # ------------------------------------------------------------------
    def _mode_art(self, canvas, rect, mode, selected):
        """Give each mode a simple original sports visual identity."""
        clip = canvas.get_clip()
        canvas.set_clip(rect)
        base = BLUE if selected else (21, 34, 53)
        pygame.draw.rect(canvas, base, rect)
        # diagonal broadcast shapes
        for n in range(-2, 7):
            x = rect.x + n * 95
            pygame.draw.polygon(canvas, (35, 72, 125) if selected else (26, 44, 68),
                                [(x, rect.y), (x + 74, rect.y), (x + 210, rect.bottom), (x + 136, rect.bottom)])
        if mode.route in ("quick_match", "training", "local_coop"):
            # Pitch motif
            pygame.draw.ellipse(canvas, (210, 232, 222), (rect.centerx - 94, rect.centery - 45, 188, 90), 2)
            pygame.draw.line(canvas, (210, 232, 222), (rect.centerx, rect.y + 12), (rect.centerx, rect.bottom - 12), 2)
        elif mode.route in ("career", "journey"):
            self._draw_player_figure(canvas, (rect.right - 110, rect.bottom + 115), 0.42, False, 220)
        else:
            draw_glow(canvas, (rect.right - 85, rect.y + 80), 110, BLUE_L, 70)
            pygame.draw.circle(canvas, (225, 236, 255), (rect.right - 85, rect.y + 80), 38, 3)
        canvas.set_clip(clip)

    def draw_hub(self, canvas):
        self._draw_stadium_world(canvas, 1.0)
        # player/scene protagonist on the right
        self._draw_player_figure(canvas, (1565, 1080), 0.98, False, 240)

        veil = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pygame.draw.polygon(veil, (0, 0, 0, 126), [(0, 0), (1180, 0), (1000, 1080), (0, 1080)])
        canvas.blit(veil, (0, 0))

        self.draw_brand(canvas)
        self.draw_tabs(canvas)

        modes = MODES[self.tab_name]
        if self.selected >= len(modes):
            self.selected = 0
        mode = modes[self.selected]
        eyebrow, title, subtitle = HERO_COPY[self.tab_name]

        tab_p = ease_out_cubic((time.perf_counter() - self._tab_changed_at) / 0.32)
        x = int(76 + (1 - tab_p) * 38)
        draw_text(canvas, eyebrow, self.f12, BLUE_L, (x, 174), alpha=int(255 * tab_p))
        draw_text(canvas, title, self._hero_title, WHITE, (x, 208), alpha=int(255 * tab_p))
        draw_text(canvas, subtitle, self.f16, SOFT, (x + 3, 285), alpha=int(240 * tab_p))

        # Current selection gets a real hero panel, not a debug card.
        hero = pygame.Rect(76, 350, 1010, 280)
        rounded_panel(canvas, hero, (8, 13, 23), (48, 62, 84), 22, 1, 234)
        art = pygame.Rect(hero.x, hero.y, 435, hero.h)
        self._mode_art(canvas, art, mode, True)
        shade = pygame.Surface((435, hero.h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 22))
        canvas.blit(shade, art.topleft)
        draw_text(canvas, mode.status, self.f12, (207, 224, 250), (art.x + 26, art.y + 25))
        draw_text(canvas, mode.title, self._tile_title, WHITE, (hero.x + 480, hero.y + 48))
        draw_text(canvas, mode.subtitle, self.f16, BLUE_L, (hero.x + 482, hero.y + 96))
        self._draw_wrapped(canvas, mode.description, self.f16, SOFT,
                           pygame.Rect(hero.x + 482, hero.y + 142, 470, 58), max_lines=2, line_gap=2)
        draw_text(canvas, "A  ENTRAR", self.f16, WHITE, (hero.x + 482, hero.bottom - 48))
        self.add_region(hero, "mode", mode)

        # Horizontal playlist: 5 compact, readable tiles.
        visible = min(5, len(modes))
        start = max(0, min(self.selected - 2, max(0, len(modes) - visible)))
        tile_y, tile_w, tile_h, gap = 706, 330, 210, 17
        for slot, entry in enumerate(modes[start:start + visible]):
            idx = start + slot
            selected = idx == self.selected
            rect = pygame.Rect(76 + slot * (tile_w + gap), tile_y - (9 if selected else 0), tile_w, tile_h + (9 if selected else 0))
            rounded_panel(canvas, rect,
                          (247, 249, 252) if selected else (9, 15, 25),
                          (255, 255, 255) if selected else (45, 56, 74), 16, 1, 247)
            if selected:
                pygame.draw.rect(canvas, BLUE, (rect.x, rect.y, rect.w, 6), border_radius=3)
            tc = (14, 21, 33) if selected else WHITE
            sc = (74, 89, 111) if selected else MUTED
            draw_text(canvas, f"{idx + 1:02d}", self.f12, BLUE if selected else (93, 112, 140), (rect.x + 22, rect.y + 20))
            draw_text(canvas, entry.title, self.f20, tc, (rect.x + 22, rect.y + 53))
            self._draw_wrapped(canvas, entry.subtitle, self.f16, sc,
                               pygame.Rect(rect.x + 22, rect.y + 99, rect.w - 44, 52), max_lines=2, line_gap=1)
            self.add_region(rect, "mode", entry)

        # Very subtle engine state, no giant LAB panel in the player experience.
        ready = self.runtime().get("ready", False)
        status_color = (91, 201, 143) if ready else (172, 141, 88)
        status_text = "MOTOR LISTO" if ready else "MOTOR PENDIENTE"
        pygame.draw.circle(canvas, status_color, (1750, 979), 5)
        draw_text(canvas, status_text, self.f12, (124, 138, 158), (1764, 970))

    # ------------------------------------------------------------------
    # Kick Off / local co-op
    # ------------------------------------------------------------------
    def _team_panel(self, canvas, team, rect, side, selected):
        name, color = self._team_identity(team)
        fill = (245, 248, 252) if selected else (9, 15, 25)
        border = WHITE if selected else (48, 59, 76)
        rounded_panel(canvas, rect, fill, border, 20, 2 if selected else 1, 248)
        if selected:
            pygame.draw.rect(canvas, color, (rect.x, rect.y, rect.w, 7), border_radius=3)
        text = (13, 20, 31) if selected else WHITE
        secondary = (78, 91, 111) if selected else MUTED
        badge_center = (rect.centerx, rect.y + 102)
        draw_glow(canvas, badge_center, 95, color, 65 if selected else 38)
        pygame.draw.circle(canvas, color, badge_center, 62)
        pygame.draw.circle(canvas, WHITE, badge_center, 62, 2)
        draw_text(canvas, team.short, self.f20, WHITE, badge_center, "center")
        draw_text(canvas, side, self.f12, color if selected else BLUE_L, (rect.centerx, rect.y + 185), "center")
        draw_text(canvas, name, self.f24, text, (rect.centerx, rect.y + 220), "center")
        draw_text(canvas, str(team.rating), self._score_font, color, (rect.centerx, rect.y + 278), "center")
        draw_text(canvas, team.style.upper(), self.f12, secondary, (rect.centerx, rect.bottom - 34), "center")

    def draw_quick(self, canvas, coop=False):
        self._draw_stadium_world(canvas, 0.92)
        veil = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        veil.fill((0, 0, 0, 76))
        canvas.blit(veil, (0, 0))
        self.draw_brand(canvas)
        self.draw_tabs(canvas)

        draw_text(canvas, "CO-OP LOCAL" if coop else "PATADA INICIAL", self._hero_title, WHITE, (76, 153))
        draw_text(canvas, "Elige los equipos. Ajusta lo esencial. Juega.", self.f16, SOFT, (80, 229))

        home = TEAMS[self.quick["home"]]
        away = TEAMS[self.quick["away"]]
        home_rect = pygame.Rect(90, 312, 500, 430)
        away_rect = pygame.Rect(1330, 312, 500, 430)
        self._team_panel(canvas, home, home_rect, "LOCAL", self.page_cursor == 0)
        self._team_panel(canvas, away, away_rect, "VISITANTE", self.page_cursor == 1)
        self.add_region(home_rect, "cursor", 0)
        self.add_region(away_rect, "cursor", 1)

        draw_text(canvas, "VS", self._hero_mega, WHITE, (960, 475), "center")
        draw_text(canvas, "CENTELLA EXHIBITION", self.f12, BLUE_L, (960, 566), "center")

        # Match settings compressed into a broadcast-style central strip.
        labels = [
            ("DURACIÓN", f"{self.quick['minutes']} MIN"),
            ("DIFICULTAD", self.quick["difficulty"]),
            ("HORA", self.quick["time"]),
            ("CLIMA", self.quick["weather"]),
        ]
        y = 786
        for n, (label, value) in enumerate(labels):
            idx = n + 2
            x = 90 + n * 315
            rect = pygame.Rect(x, y, 295, 82)
            sel = self.page_cursor == idx
            rounded_panel(canvas, rect,
                          (247, 249, 252) if sel else (10, 16, 27),
                          WHITE if sel else (47, 59, 77), 14, 1, 246)
            draw_text(canvas, label, self.f12, (82, 95, 115) if sel else MUTED, (x + 18, y + 15))
            draw_text(canvas, value, self.f16, BLUE if sel else WHITE, (x + 18, y + 44))
            self.add_region(rect, "cursor", idx)

        if coop:
            idx = 6
            rect = pygame.Rect(1350, 786, 226, 82)
            sel = self.page_cursor == idx
            rounded_panel(canvas, rect, (247, 249, 252) if sel else PANEL, WHITE if sel else (48, 60, 78), 14, 1, 246)
            draw_text(canvas, "P1 + P2", self.f12, MUTED, (rect.x + 16, rect.y + 14))
            draw_text(canvas, "VERSUS" if self.quick["versus"] else "MISMO EQUIPO", self.f16, BLUE if sel else WHITE, (rect.x + 16, rect.y + 44))
            self.add_region(rect, "cursor", idx)

        play = pygame.Rect(1588 if coop else 1350, 786, 242 if coop else 480, 82)
        sel = self.page_cursor == 7
        rounded_panel(canvas, play, BLUE if sel else (22, 34, 54), BLUE_L, 14, 2 if sel else 1, 252)
        draw_text(canvas, "JUGAR PARTIDO", self.f20, WHITE, play.center, "center")
        self.add_region(play, "cursor", 7)

        draw_text(canvas, "← / → CAMBIAR  ·  A CONFIRMAR", self.f12, MUTED, (90, 930))
        draw_text(canvas, f"MANDOS: {len(self.controller.joysticks)}", self.f12, MUTED, (1825, 930), "topright")

    # ------------------------------------------------------------------
    # Diagnostics: visually de-emphasised but still fully available.
    # ------------------------------------------------------------------
    def draw_doctor(self, canvas):
        self.page_header(canvas, "CENTELLA LAB", "Herramientas del motor · no forma parte del flujo principal de juego")
        data = self.runtime()
        ready = bool(data.get("ready", False))
        state = "MOTOR LISTO" if ready else "MOTOR NATIVO PENDIENTE"
        color = (91, 201, 143) if ready else (221, 177, 84)
        draw_text(canvas, state, self.f30, color, (80, 330))
        draw_text(canvas,
                  "El menú, mando y configuración pueden funcionar aunque el motor C++ todavía requiera reparación.",
                  self.f16, SOFT, (82, 382))

        y = 445
        for probe in data.get("runtimes", [])[:3]:
            rect = pygame.Rect(80, y, 1050, 105)
            rounded_panel(canvas, rect, PANEL, (47, 59, 77), 14, 1, 242)
            path = probe.get("executable", "")
            version = probe.get("version", "")
            modules = probe.get("modules") or {}
            draw_text(canvas, f"PYTHON {version}", self.f16, WHITE, (104, y + 20))
            draw_text(canvas, path, self.f12, MUTED, (104, y + 50))
            summary = "  ·  ".join(f"{name.upper()} {'OK' if modules.get(name) else '—'}" for name in ("pygame", "absl", "numpy", "gfootball_engine"))
            draw_text(canvas, summary, self.f12, color if probe.get("engine") else MUTED, (104, y + 75))
            y += 120

        actions = [
            ("VOLVER A COMPROBAR", "Escanear runtimes y motor"),
            ("INSTALAR / REPARAR", "Abrir el reparador de Windows"),
        ]
        for i, (title, sub) in enumerate(actions):
            rect = pygame.Rect(1260, 445 + i * 140, 565, 112)
            sel = self.page_cursor == i
            rounded_panel(canvas, rect, (247, 249, 252) if sel else PANEL_2, WHITE if sel else (55, 68, 90), 16, 1, 248)
            draw_text(canvas, title, self.f20, (15, 22, 34) if sel else WHITE, (1288, rect.y + 24))
            draw_text(canvas, sub, self.f12, (78, 92, 113) if sel else MUTED, (1288, rect.y + 66))
            self.add_region(rect, "cursor", i)


def main():
    App().run()


if __name__ == "__main__":
    main()
