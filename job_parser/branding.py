from __future__ import annotations

import os
import sys


RESET = "\033[0m"
RED = "\033[38;5;203m"
WHITE = "\033[38;5;255m"
BLUE = "\033[38;5;117m"
GOLD = "\033[38;5;222m"
CREAM = "\033[38;5;230m"
SLATE = "\033[38;5;245m"
BOLD = "\033[1m"


def render_logo(use_color: bool | None = None) -> str:
    color = _should_use_color() if use_color is None else use_color
    if not color:
        return (
            "   ░▓░\n"
            "  ▓███▓   job parser\n"
            "  ░▓█▓░   search with style\n"
        )

    bull = f"{CREAM}█{RESET}"
    inner = f"{RED}███{RESET}"
    outer = f"{WHITE}█████{RESET}"
    ring = f"{BLUE} ▓█▓ {RESET}"
    line1 = f"   {ring}"
    line2 = f"  {BLUE}▓{RESET}{outer}{BLUE}▓{RESET}   {GOLD}{BOLD}job parser{RESET}"
    line3 = f"  {WHITE}█{RESET}{inner}{bull}{inner}{WHITE}█{RESET}"
    line4 = f"  {BLUE}▓{RESET}{outer}{BLUE}▓{RESET}   {SLATE}search with style{RESET}"
    line5 = f"   {ring}"
    return "\n".join([line1, line2, line3, line4, line5])


def print_logo() -> None:
    print(render_logo())


def _should_use_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()
