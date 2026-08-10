"""Modern product shell for CENTELLA Football.

Run with:
    python -m centella

The shell intentionally sits above Google Research Football / Gameplay Football
instead of forking the simulation loop blindly. Quick Match and Training launch
the existing engine today; the remaining cards describe the product roadmap and
stay visibly locked until they are real.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pygame

from .brand import BRAND, FONT_CANDIDATES

BASE_SIZE = (1600, 900)
FPS = 60
ASSET_DIR = Path(__file__).resolve().parent / "assets"


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


def mix(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float):
    t = clamp(t)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def resolve_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Prefer Urbanist without redistributing font files."""
    for candidate in FONT_CANDIDATES:
        path = pygame.font.match_font(candidate, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def text(surface, value, font, color, pos, anchor="topleft", alpha=255):
    rendered = font.render(value, True, color)
    if alpha != 255:
        rendered.set_alpha(alpha)
    rect = rendered.get_rect()
    setattr(rect, anchor, pos)
    surface.blit(rendered, rect)
    return rect


def load_image(name: str) -> Optional[pygame.Surface]:
    path = ASSET_DIR / name
    if not path.exists():
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except pygame.error:
        return None


def scaled_inside(image: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    iw, ih = image.get_size()
    ratio = min(max_w / iw, max_h / ih)
    return pygame.transform.smoothscale(
        image, (max(1, int(iw * ratio)), max(1, int(ih * ratio)))
    )


@dataclass
class MenuCard:
    title: str
    subtitle: str
    tag: str = ""
    enabled: bool = False
    action: Optional[Callable[[], None]] = None


class App:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        pygame.joystick.init()
        pygame.display.set_caption("CENTELLA Football")
        self.screen = pygame.display.set_mode(
            BASE_SIZE, pygame.RESIZABLE | pygame.DOUBLEBUF
        )
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = "splash"
        self.state_started = time.perf_counter()
        self.toast = ""
        self.toast_until = 0.0
        self.selected = 0
        self.performance_overlay = False

        self.wordmark = load_image("centella_wordmark_white.png")
        self.symbol = load_image("centella_symbol_white.png")

        self.font_xs = resolve_font(18)
        self.font_sm = resolve_font(22)
        self.font_md = resolve_font(30, bold=True)
        self.font_lg = resolve_font(52, bold=True)
        self.font_xl = resolve_font(84, bold=True)
        self.font_hero = resolve_font(106, bold=True)

        self.cards: List[MenuCard] = [
            MenuCard(
                "PARTIDO RÁPIDO",
                "Entra al campo. Sin rodeos.",
                "JUGAR",
                True,
                self.launch_quick_match,
            ),
            MenuCard(
                "ENTRENAMIENTO",
                "Pase, control y definición.",
                "ACADEMIA",
                True,
                self.launch_training,
            ),
            MenuCard(
                "CARRERA",
                "Construye un club y una historia.",
                "PRÓXIMAMENTE",
                False,
            ),
            MenuCard(
                "ONLINE",
                "Competición con defensa manual.",
                "EN DESARROLLO",
                False,
            ),
            MenuCard(
                "CLUB",
                "Crea, personaliza y comparte.",
                "EN DESARROLLO",
                False,
            ),
            MenuCard(
                "AJUSTES",
                "Vídeo, controles y accesibilidad.",
                "SIGUIENTE",
                False,
            ),
        ]

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.state_started

    def enter(self, state: str):
        self.state = state
        self.state_started = time.perf_counter()

    def notify(self, message: str, seconds: float = 2.2):
        self.toast = message
        self.toast_until = time.perf_counter() + seconds

    def launch_game(self, level: Optional[str] = None):
        cmd = [
            sys.executable,
            "-m",
            "gfootball.play_game",
            "--action_set=full",
            "--render=True",
        ]
        if level:
            cmd.append(f"--level={level}")
        self.notify("INICIANDO MOTOR DE PARTIDO…", 1.0)
        pygame.display.flip()
        pygame.quit()
        try:
            os.execv(sys.executable, cmd)
        except OSError:
            subprocess.Popen(cmd)
            raise SystemExit(0)

    def launch_quick_match(self):
        self.launch_game()

    def launch_training(self):
        self.launch_game("academy_pass_and_shoot_with_keeper")

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode(
                event.size, pygame.RESIZABLE | pygame.DOUBLEBUF
            )
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
            self.performance_overlay = not self.performance_overlay
            return

        if self.state == "splash":
            if event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEBUTTONDOWN,
                pygame.JOYBUTTONDOWN,
            ):
                self.enter("home")
            return

        if self.state == "home":
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    self.running = False
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.selected = (self.selected + 1) % len(self.cards)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self.selected = (self.selected - 1) % len(self.cards)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.selected = (self.selected + 3) % len(self.cards)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self.selected = (self.selected - 3) % len(self.cards)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.activate_selected()
            elif event.type == pygame.JOYHATMOTION:
                x, y = event.value
                if x > 0:
                    self.selected = (self.selected + 1) % len(self.cards)
                elif x < 0:
                    self.selected = (self.selected - 1) % len(self.cards)
                elif y < 0:
                    self.selected = (self.selected + 3) % len(self.cards)
                elif y > 0:
                    self.selected = (self.selected - 3) % len(self.cards)
            elif event.type == pygame.JOYBUTTONDOWN:
                if event.button in (0, 7):
                    self.activate_selected()
                elif event.button in (1, 6):
                    self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                idx = self.card_at(event.pos)
                if idx is not None:
                    self.selected = idx
                    self.activate_selected()

    def activate_selected(self):
        card = self.cards[self.selected]
        if card.enabled and card.action:
            card.action()
        else:
            self.notify(f"{card.title}: {card.tag or 'EN DESARROLLO'}")

    def logical_mouse(self, pos):
        w, h = self.screen.get_size()
        sx = w / BASE_SIZE[0]
        sy = h / BASE_SIZE[1]
        return int(pos[0] / sx), int(pos[1] / sy)

    def card_rects(self):
        start_x, start_y = 765, 390
        card_w, card_h, gap = 365, 145, 18
        rects = []
        for i in range(6):
            row, col = divmod(i, 3)
            rects.append(
                pygame.Rect(
                    start_x + col * (card_w + gap),
                    start_y + row * (card_h + gap),
                    card_w,
                    card_h,
                )
            )
        return rects

    def card_at(self, screen_pos):
        point = self.logical_mouse(screen_pos)
        for i, rect in enumerate(self.card_rects()):
            if rect.collidepoint(point):
                return i
        return None

    def draw_background(
        self, canvas: pygame.Surface, t: float, intensity: float = 1.0
    ):
        w, h = BASE_SIZE

        # Vertical cyberminimal gradient.
        for y in range(0, h, 6):
            k = y / h
            color = mix(BRAND.jet_black, (8, 14, 27), k * 0.72 * intensity)
            pygame.draw.rect(canvas, color, (0, y, w, 7))

        # Stadium horizon / floodlights: abstract, not a stock image.
        horizon = 315
        for i in range(11):
            x = int((i + 0.5) * w / 11)
            pulse = 0.55 + 0.45 * math.sin(t * 1.4 + i * 0.73)
            radius = int(2 + pulse * 4 * intensity)
            alpha = int((45 + pulse * 55) * intensity)
            glow = pygame.Surface((80, 80), pygame.SRCALPHA)
            pygame.draw.circle(
                glow,
                (*BRAND.sapphire_light, alpha // 5),
                (40, 40),
                38,
            )
            pygame.draw.circle(
                glow, (*BRAND.white, alpha), (40, 40), radius
            )
            canvas.blit(glow, (x - 40, horizon - 40))

        # Perspective pitch lines; restrained so UI stays premium.
        vanishing = (w // 2, 345)
        field_bottom = h + 80
        line_col = (35, 69, 108)
        for bottom_x in range(-100, w + 101, 200):
            pygame.draw.aaline(
                canvas, line_col, vanishing, (bottom_x, field_bottom)
            )
        for y in (500, 640, 790):
            width = int((y - vanishing[1]) * 1.95)
            pygame.draw.aaline(
                canvas,
                line_col,
                (w // 2 - width, y),
                (w // 2 + width, y),
            )

        # Slow blue light sweep. It reads as stadium energy, not arcade pixels.
        sweep_x = int(((t * 82) % (w + 600)) - 300)
        beam = pygame.Surface((600, h), pygame.SRCALPHA)
        for x in range(600):
            d = abs(x - 300) / 300
            alpha = int(18 * (1.0 - d) ** 2 * intensity)
            pygame.draw.line(
                beam,
                (*BRAND.sapphire, alpha),
                (x, 0),
                (x - 170, h),
            )
        canvas.blit(beam, (sweep_x, 0))

        vignette = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(vignette, (0, 0, 0, 52), vignette.get_rect(), width=95)
        canvas.blit(vignette, (0, 0))

    def draw_splash(self, canvas: pygame.Surface):
        t = self.elapsed
        self.draw_background(canvas, t, intensity=0.72)

        ignition = ease_out_cubic((t - 0.20) / 0.75)
        word_phase = ease_out_cubic((t - 0.75) / 0.85)
        prompt_phase = ease_in_out((t - 1.85) / 0.65)

        if self.symbol:
            image = scaled_inside(self.symbol, 96, 170)
            image.set_alpha(int(255 * ignition))
            canvas.blit(image, image.get_rect(center=(800, 326)))
            glow = pygame.Surface((240, 240), pygame.SRCALPHA)
            pygame.draw.circle(
                glow,
                (*BRAND.sapphire, int(65 * ignition)),
                (120, 120),
                int(78 + 15 * math.sin(t * 3)),
            )
            canvas.blit(glow, (680, 206))
        else:
            text(
                canvas,
                "ϟ",
                self.font_xl,
                BRAND.white,
                (800, 326),
                "center",
                int(255 * ignition),
            )

        if self.wordmark:
            image = scaled_inside(self.wordmark, 560, 160)
            image.set_alpha(int(255 * word_phase))
            canvas.blit(image, image.get_rect(center=(800, 495)))
        else:
            text(
                canvas,
                "CENTELLA",
                self.font_xl,
                BRAND.white,
                (800, 495),
                "center",
                int(255 * word_phase),
            )

        text(
            canvas,
            "F O O T B A L L",
            self.font_sm,
            BRAND.sapphire_light,
            (800, 585),
            "center",
            int(230 * word_phase),
        )

        pulse = 0.65 + 0.35 * math.sin(t * 3.1)
        text(
            canvas,
            "PRESIONA CUALQUIER BOTÓN",
            self.font_sm,
            BRAND.white,
            (800, 760),
            "center",
            int(255 * prompt_phase * pulse),
        )
        text(
            canvas,
            "ALPHA 0.1  ·  MOTOR GAMEPLAY FOOTBALL",
            self.font_xs,
            BRAND.muted,
            (800, 812),
            "center",
            int(170 * prompt_phase),
        )

    def draw_home(self, canvas: pygame.Surface):
        t = self.elapsed
        self.draw_background(canvas, t, intensity=1.0)

        if self.wordmark:
            logo = scaled_inside(self.wordmark, 220, 62)
            canvas.blit(logo, (72, 52))
        else:
            text(canvas, "CENTELLA", self.font_md, BRAND.white, (72, 58))
        text(canvas, "FOOTBALL", self.font_xs, BRAND.sapphire_light, (72, 114))
        text(canvas, "OFFLINE", self.font_xs, BRAND.muted, (1515, 66), "topright")
        pygame.draw.circle(canvas, BRAND.success, (1536, 73), 5)

        text(canvas, "EL FÚTBOL", self.font_hero, BRAND.white, (72, 226))
        text(
            canvas,
            "RESPONDE A TI.",
            self.font_hero,
            BRAND.sapphire_light,
            (72, 325),
        )
        text(
            canvas,
            "Precisión de simulación. Respuesta inmediata. Cero pay-to-win.",
            self.font_sm,
            BRAND.muted,
            (78, 456),
        )

        pillars = (
            ("RESPUESTA", "< 85 ms objetivo"),
            ("BALÓN", "Física independiente"),
            ("DEFENSA", "Primero manual"),
        )
        x = 78
        for title_, value in pillars:
            pygame.draw.line(canvas, BRAND.sapphire, (x, 522), (x + 42, 522), 3)
            text(canvas, title_, self.font_xs, BRAND.white, (x, 540))
            text(canvas, value, self.font_xs, BRAND.muted, (x, 568))
            x += 205

        mouse_idx = self.card_at(pygame.mouse.get_pos())
        if mouse_idx is not None:
            self.selected = mouse_idx

        for i, (card, rect) in enumerate(zip(self.cards, self.card_rects())):
            selected = i == self.selected
            base = BRAND.surface_hover if selected else BRAND.surface
            pygame.draw.rect(canvas, base, rect, border_radius=18)
            border = BRAND.sapphire_light if selected else (48, 52, 62)
            pygame.draw.rect(
                canvas,
                border,
                rect,
                width=2 if selected else 1,
                border_radius=18,
            )
            if selected:
                pygame.draw.rect(
                    canvas,
                    BRAND.sapphire,
                    (rect.x, rect.y, 6, rect.height),
                    border_radius=3,
                )
            text(
                canvas,
                card.tag,
                self.font_xs,
                BRAND.sapphire_light if card.enabled else BRAND.muted,
                (rect.x + 26, rect.y + 22),
            )
            text(
                canvas,
                card.title,
                self.font_md,
                BRAND.white,
                (rect.x + 26, rect.y + 55),
            )
            text(
                canvas,
                card.subtitle,
                self.font_xs,
                BRAND.muted,
                (rect.x + 26, rect.y + 103),
            )

        text(canvas, "← →  NAVEGAR", self.font_xs, BRAND.muted, (78, 842))
        text(
            canvas,
            "ENTER / A  SELECCIONAR",
            self.font_xs,
            BRAND.white,
            (260, 842),
        )
        text(canvas, "ESC / B  SALIR", self.font_xs, BRAND.muted, (495, 842))
        text(
            canvas,
            "F1  RENDIMIENTO",
            self.font_xs,
            BRAND.muted,
            (1518, 842),
            "topright",
        )

    def draw_toast(self, canvas):
        if time.perf_counter() >= self.toast_until or not self.toast:
            return
        rendered = self.font_sm.render(self.toast, True, BRAND.white)
        rect = rendered.get_rect()
        box = pygame.Rect(0, 0, rect.width + 54, 58)
        box.midbottom = (800, 820)
        pygame.draw.rect(canvas, (19, 24, 32), box, border_radius=16)
        pygame.draw.rect(canvas, BRAND.sapphire, box, width=2, border_radius=16)
        canvas.blit(rendered, rendered.get_rect(center=box.center))

    def draw_perf(self, canvas):
        if not self.performance_overlay:
            return
        fps = self.clock.get_fps()
        label = f"{fps:5.1f} FPS · UI 1600×900 logical"
        rendered = self.font_xs.render(label, True, BRAND.white)
        rect = rendered.get_rect(topright=(1518, 118))
        bg = pygame.Surface((rect.width + 20, rect.height + 12), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 155))
        canvas.blit(bg, (rect.x - 10, rect.y - 6))
        canvas.blit(rendered, rect)

    def render(self):
        canvas = pygame.Surface(BASE_SIZE).convert()
        if self.state == "splash":
            self.draw_splash(canvas)
        else:
            self.draw_home(canvas)
            self.draw_toast(canvas)
        self.draw_perf(canvas)

        screen_size = self.screen.get_size()
        scaled = (
            pygame.transform.smoothscale(canvas, screen_size)
            if screen_size != BASE_SIZE
            else canvas
        )
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                self.handle_event(event)
            self.render()
        pygame.quit()


def main():
    App().run()


if __name__ == "__main__":
    main()
