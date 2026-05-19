from __future__ import annotations

import os
import sys
from pathlib import Path


RESET = "\033[0m"
SELECTED = "\033[38;2;219;188;127m"
LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "logo.ansi"


def render_logo(use_color: bool | None = None) -> str:
    color = _should_use_color() if use_color is None else use_color
    logo = LOGO_PATH.read_text(encoding="utf-8").rstrip("\n")
    if not color:
        return logo
    return f"{SELECTED}{logo}{RESET}"


def print_logo() -> None:
    print(render_logo())


def _should_use_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()
