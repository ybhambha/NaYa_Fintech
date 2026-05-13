"""
semisector/color_helper.py
──────────────────────────
Terminal colour and style formatting helper.
All other modules import from here — no module should reference
colorama's Fore/Style directly.
"""

from __future__ import annotations

from typing import Optional

try:
    from colorama import Fore, Style, init as _colorama_init
    _colorama_init(autoreset=True)
    _COLOR = True
except ImportError:
    _COLOR = False

from semisector.config import SCORE_HIGH, SCORE_MED


class ColorHelper:
    """
    Class-level helpers for consistent terminal coloring.
    All methods are @classmethod so callers use C.green(...) without
    instantiating the class.
    """

    enabled: bool = _COLOR

    @classmethod
    def green(cls, s) -> str:
        return (Fore.GREEN + str(s) + Style.RESET_ALL) if cls.enabled else str(s)

    @classmethod
    def red(cls, s) -> str:
        return (Fore.RED + str(s) + Style.RESET_ALL) if cls.enabled else str(s)

    @classmethod
    def yellow(cls, s) -> str:
        return (Fore.YELLOW + str(s) + Style.RESET_ALL) if cls.enabled else str(s)

    @classmethod
    def cyan(cls, s) -> str:
        return (Fore.CYAN + str(s) + Style.RESET_ALL) if cls.enabled else str(s)

    @classmethod
    def bold(cls, s) -> str:
        return (Style.BRIGHT + str(s) + Style.RESET_ALL) if cls.enabled else str(s)

    @classmethod
    def dim(cls, s) -> str:
        return (Style.DIM + str(s) + Style.RESET_ALL) if cls.enabled else str(s)

    @classmethod
    def score(cls, v: float) -> str:
        s = f"{v:5.1f}"
        if v >= SCORE_HIGH: return cls.green(s)
        if v >= SCORE_MED:  return cls.yellow(s)
        return cls.red(s)

    @classmethod
    def pct(cls, v: Optional[float], decimals: int = 1) -> str:
        if v is None:
            return cls.dim("  N/A")
        return (cls.green if v > 0 else cls.red)(f"{v:+.{decimals}f}%")

    @staticmethod
    def ratio(v: Optional[float], decimals: int = 1) -> str:
        return f"{v:.{decimals}f}x" if v is not None else ColorHelper.dim("N/A")

    @staticmethod
    def flt(v: Optional[float], decimals: int = 1, suffix: str = "") -> str:
        return f"{v:.{decimals}f}{suffix}" if v is not None else ColorHelper.dim("N/A")


# Convenient module-level alias used across the package
C = ColorHelper
