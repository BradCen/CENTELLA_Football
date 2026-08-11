"""CENTELLA Football visual identity tokens.

No font files are bundled here. The UI asks the OS for Urbanist first and
falls back to common system sans-serif fonts when Urbanist is unavailable.
"""

from dataclasses import dataclass
from typing import Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Brand:
    jet_black: Color = (2, 2, 3)       # #020203
    obsidian: Color = (23, 23, 23)     # #171717
    white: Color = (255, 255, 255)     # #FFFFFF
    sapphire: Color = (35, 89, 170)    # #2359AA
    sapphire_light: Color = (73, 128, 210)
    muted: Color = (153, 160, 173)
    surface: Color = (15, 17, 22)
    surface_hover: Color = (24, 28, 36)
    success: Color = (111, 210, 154)

    # Motion: short and decisive rather than gamey/bouncy.
    fast_ms: int = 120
    standard_ms: int = 240
    cinematic_ms: int = 700


BRAND = Brand()
FONT_CANDIDATES = ("Urbanist", "Segoe UI", "Arial", "DejaVu Sans")
