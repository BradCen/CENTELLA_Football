from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import pygame

from .brand import BRAND, FONT_CANDIDATES

LOGICAL_SIZE = (1920, 1080)


def hex_color(value: str) -> Tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return BRAND.white
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return BRAND.white


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def mix(a: Sequence[int], b: Sequence[int], t: float) -> Tuple[int, int, int]:
    t = clamp(t)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def font(size: int, bold: bool = False) -> pygame.font.Font:
    for candidate in FONT_CANDIDATES:
        path = pygame.font.match_font(candidate, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def draw_text(surface, value, fnt, color, pos, anchor="topleft", alpha=255):
    image = fnt.render(value, True, color)
    if alpha != 255:
        image.set_alpha(alpha)
    rect = image.get_rect()
    setattr(rect, anchor, pos)
    surface.blit(image, rect)
    return rect


def rounded_panel(surface, rect, fill, border=None, radius=20, width=1, alpha=255):
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    f = (*fill, alpha) if len(fill) == 3 else fill
    pygame.draw.rect(layer, f, layer.get_rect(), border_radius=radius)
    if border:
        b = (*border, min(alpha, 255)) if len(border) == 3 else border
        pygame.draw.rect(layer, b, layer.get_rect(), width=width, border_radius=radius)
    surface.blit(layer, rect.topleft)


def draw_glow(surface, center, radius, color, alpha=80):
    size = radius * 2
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    for r in range(radius, 2, -8):
        strength = int(alpha * (1 - r / max(radius, 1)) ** 0.7)
        pygame.draw.circle(layer, (*color, strength), (radius, radius), r)
    surface.blit(layer, (center[0] - radius, center[1] - radius))


def draw_stadium_scene(surface, t, sapphire=(35, 89, 170), intensity=1.0, motion=True):
    """Original modern sports-game staging without third-party visual assets."""
    w, h = LOGICAL_SIZE
    for y in range(0, h, 8):
        k = y / h
        top = mix((3, 5, 12), (8, 11, 24), k)
        c = mix(top, (10, 28, 58), k * 0.45 * intensity)
        pygame.draw.rect(surface, c, (0, y, w, 9))

    positions = [(230, 110), (610, 65), (1000, 80), (1400, 55), (1750, 120)]
    for i, p in enumerate(positions):
        pulse = 0.74 + (0.16 * math.sin(t * 1.3 + i) if motion else 0)
        draw_glow(surface, p, int(170 * pulse), sapphire, int(48 * intensity))
        pygame.draw.circle(surface, (225, 234, 255), p, 3)

    horizon = 600
    vanishing = (960, 560)
    pygame.draw.polygon(surface, (7, 21, 28), [(0, 1080), (1920, 1080), (1370, horizon), (550, horizon)])
    line = mix((18, 56, 68), sapphire, 0.28)
    for bx in range(-250, 2200, 180):
        pygame.draw.aaline(surface, line, vanishing, (bx, 1100))
    for y in [680, 770, 865, 960, 1050]:
        k = (y - horizon) / max(1, 1080 - horizon)
        half = int(410 + 720 * k)
        pygame.draw.aaline(surface, line, (960 - half, y), (960 + half, y))

    pygame.draw.polygon(surface, (10, 18, 31), [(0, 478), (1920, 432), (1920, 560), (0, 595)])
    for x in range(-100, 2100, 185):
        pygame.draw.line(surface, mix((30, 43, 66), sapphire, 0.35), (x, 500), (x + 120, 535), 2)

    if motion:
        sweep = int(((t * 100) % 2500) - 500)
        beam = pygame.Surface((540, 1080), pygame.SRCALPHA)
        pygame.draw.polygon(beam, (*sapphire, 23), [(80, 0), (390, 0), (540, 1080), (0, 1080)])
        surface.blit(beam, (sweep, 0))

    shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
    pygame.draw.rect(shade, (0, 0, 0, 48), shade.get_rect(), width=120)
    surface.blit(shade, (0, 0))


def draw_player_silhouette(surface, x, y, scale, accent=(35, 89, 170), alpha=230):
    """Stylised original footballer silhouette for the menu stage."""
    layer = pygame.Surface((520, 820), pygame.SRCALPHA)
    c = (13, 17, 28, alpha)
    edge = (*accent, int(alpha * 0.55))
    pygame.draw.ellipse(layer, c, (213, 40, 94, 110))
    pygame.draw.rect(layer, c, (235, 130, 50, 65), border_radius=15)
    torso = [(170, 180), (350, 180), (392, 430), (325, 510), (195, 510), (128, 430)]
    pygame.draw.polygon(layer, c, torso)
    pygame.draw.lines(layer, edge, True, torso, 3)
    pygame.draw.polygon(layer, c, [(165, 195), (108, 225), (48, 430), (86, 448), (165, 320)])
    pygame.draw.polygon(layer, c, [(355, 195), (414, 230), (470, 420), (430, 440), (350, 320)])
    pygame.draw.polygon(layer, c, [(190, 500), (325, 500), (344, 595), (276, 615), (250, 560), (225, 615), (160, 590)])
    pygame.draw.polygon(layer, c, [(170, 580), (235, 592), (210, 785), (158, 785)])
    pygame.draw.polygon(layer, c, [(280, 590), (340, 575), (376, 778), (323, 790)])
    pygame.draw.polygon(layer, (*accent, int(alpha * 0.8)), [(180, 245), (335, 215), (345, 250), (190, 280)])
    if scale != 1:
        layer = pygame.transform.smoothscale(layer, (int(layer.get_width() * scale), int(layer.get_height() * scale)))
    rect = layer.get_rect(midbottom=(x, y))
    surface.blit(layer, rect)
    return rect


class Viewport:
    """Aspect-preserving responsive projection from 1920x1080 to any window."""
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.dest = pygame.Rect(0, 0, *screen.get_size())
        self.scale = 1.0
        self.update()

    def update(self) -> None:
        sw, sh = self.screen.get_size()
        lw, lh = LOGICAL_SIZE
        self.scale = min(sw / lw, sh / lh)
        dw, dh = int(lw * self.scale), int(lh * self.scale)
        self.dest = pygame.Rect((sw - dw) // 2, (sh - dh) // 2, dw, dh)

    def present(self, logical: pygame.Surface) -> None:
        self.update()
        self.screen.fill((0, 0, 0))
        scaled = logical if self.dest.size == LOGICAL_SIZE else pygame.transform.smoothscale(logical, self.dest.size)
        self.screen.blit(scaled, self.dest)
        pygame.display.flip()

    def mouse_to_logical(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        if not self.dest.collidepoint(pos):
            return None
        return (
            int((pos[0] - self.dest.x) / self.scale),
            int((pos[1] - self.dest.y) / self.scale),
        )
