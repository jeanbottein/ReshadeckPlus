"""Fit slider ranges to what the panel can show, without editing the .fx files."""
import math
import os
import re
import subprocess
from functools import lru_cache

MAX_TICKS = 4000
WHOLE_STEP_MIN_SPAN = 100
DEFAULT_SCREEN = (3840, 2160)
WIDTH_NAMES = {"BUFFER_WIDTH", "BUFFER_WITDH"}
HEIGHT_NAMES = {"BUFFER_HEIGHT"}
_RE_NUMBER = re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?")


@lru_cache(maxsize=1)
def screen_size() -> tuple:
    try:
        out = subprocess.run(["xrandr", "--display", ":0"], capture_output=True, text=True, timeout=2,
                             env={**os.environ, "LD_LIBRARY_PATH": ""}).stdout
        m = re.search(r"current (\d+) x (\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except (OSError, subprocess.SubprocessError):
        pass
    return DEFAULT_SCREEN


def parse_limit(raw: str):
    """Number, or BUFFER_WIDTH/BUFFER_HEIGHT as the screen size."""
    raw = raw.strip().strip('"')
    number = raw.rstrip("f")
    if _RE_NUMBER.fullmatch(number):
        return float(number)
    if raw in WIDTH_NAMES:
        return float(screen_size()[0])
    if raw in HEIGHT_NAMES:
        return float(screen_size()[1])
    return None


def _nice(value: float, up: bool) -> float:
    """Nearest 1/2/5 x 10^n step above (up) or below value."""
    exp = 10 ** math.floor(math.log10(value))
    steps = [m * exp for m in (1, 2, 5, 10)]
    return next(st for st in steps if st >= value) if up else max(st for st in steps if st <= value)


def _default_step(p: dict, span: float) -> float:
    whole = p["type"] == "int" or (float(p["default"]).is_integer() and span >= WHOLE_STEP_MIN_SPAN)
    return 1.0 if whole else _nice(span / 1000, up=False)


def fit_range(p: dict) -> None:
    """Give a numeric param a range that holds its default, and a step with at most MAX_TICKS ticks."""
    default = float(p["default"])
    lo = min(p.get("ui_min", 0.0), default)
    hi = max(p.get("ui_max", max(2.0, 2 * default)), default)
    if hi <= lo:
        hi = lo + 1
    step = p.get("ui_step", 0.0)
    if step <= 0:
        step = _default_step(p, hi - lo)
    if (hi - lo) / step > MAX_TICKS:
        step = _nice((hi - lo) / MAX_TICKS, up=True)
    if p["type"] == "int":
        step = max(1.0, round(step))
    p.update(ui_min=lo, ui_max=hi, ui_step=step)
