from __future__ import annotations

import itertools
import sys
import threading
import time
from typing import Callable, TypeVar


T = TypeVar("T")


RESET = "\033[0m"
TEAL = "\033[38;5;109m"
YELLOW = "\033[38;5;222m"
GREEN = "\033[38;5;114m"
TEXT = "\033[38;5;223m"
DIM = "\033[38;5;145m"


def run_with_loading(message: str, func: Callable[[], T]) -> T:
    if not sys.stdout.isatty():
        return func()

    stop_event = threading.Event()
    result: list[T] = []
    error: list[BaseException] = []

    def worker() -> None:
        try:
            result.append(func())
        except BaseException as exc:  # pragma: no cover - surfaced to caller
            error.append(exc)
        finally:
            stop_event.set()

    def spinner() -> None:
        frames = itertools.cycle(["◜", "◠", "◝", "◞", "◡", "◟"])
        sys.stderr.write(f"{TEAL}◉{RESET} {TEXT}{message}{RESET}\n")
        sys.stderr.flush()
        while not stop_event.is_set():
            frame = next(frames)
            sys.stderr.write(
                f"\r{GREEN}{frame}{RESET} {DIM}fetching payload from hiring.cafe...{RESET}"
            )
            sys.stderr.flush()
            time.sleep(0.12)
        sys.stderr.write("\r" + " " * 80 + "\r")
        sys.stderr.flush()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    spinner()
    thread.join()

    if error:
        raise error[0]
    return result[0]
