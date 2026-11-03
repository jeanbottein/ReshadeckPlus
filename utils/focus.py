"""Resolve which game is really on screen when Steam only knows the launcher.

Steam reports the app it started (e.g. a non-Steam shortcut to a launcher such as
Cartouche, Lutris, or XIVLauncher). Games started *by* that launcher inherit its
Steam AppId, so every game would share the launcher's profile.

Gamescope publishes the focused window and, for each focusable window, the triple
(window, appid, pid) on the root window of display :0. If the focused window's process
descends from another process that owns a window of the same app (the launcher),
we key the profile as "<appid>/<game>" instead of "<appid>".
"""
import asyncio
import os
import re

from utils.constants import logger

# Processes that only wrap the real program: skip them when naming the game.
WRAPPERS = {"sh", "bash", "dash", "zsh", "env", "nohup", "setsid", "reaper",
            "steam-launch-wrapper", "gamemoderun", "mangohud", "strace", "timeout"}
# Arguments that look like files but are not the game/ROM.
NON_ROM_EXT = {".ini", ".cfg", ".conf", ".json", ".yml", ".yaml", ".xml", ".txt", ".log", ".toml"}
STRIP_EXT = (".appimage", ".exe", ".x86_64", ".x86", ".sh", ".bin", ".elf")

# pids seen owning a window per Steam appid (a launcher may hide its window while the game runs)
_window_pids: dict = {}


def _read_cmdline(pid: int) -> list:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def _read_ppid(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat") as f:
            # comm may contain spaces/parentheses: fields after the last ')'
            return int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        return 0


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _strip_ext(name: str) -> str:
    lower = name.lower()
    for ext in STRIP_EXT:
        if lower.endswith(ext):
            return name[: -len(ext)]
    return name


def _sanitize(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9 ._+-]", "_", name).strip(" ._")
    return name[:64] or "unknown"


def _program_name(argv: list) -> str:
    """Readable program name from argv (handles flatpak run <app-id>)."""
    exe = _basename(argv[0]) if argv else ""
    if exe == "flatpak":
        for a in argv[1:]:
            if not a.startswith("-") and a != "run" and "." in a:
                return a.split(".")[-1]
    return _strip_ext(exe)


def _rom_name(argv: list):
    """Last argument that is an existing file (not a config file): the ROM/content for emulators."""
    for a in reversed(argv[1:]):
        if a.startswith("-") or not os.path.isabs(a) or a == argv[0]:
            continue
        if os.path.isfile(a) and os.path.splitext(a)[1].lower() not in NON_ROM_EXT:
            return _strip_ext(os.path.splitext(_basename(a))[0]) or None
    return None


def _game_name(chain: list) -> str:
    """chain: pids from the launcher's child down to the focused process."""
    # Proton/Wine: a Windows .exe anywhere below the launcher names the game best.
    for pid in reversed(chain):
        for a in _read_cmdline(pid):
            if a.lower().endswith(".exe") and _basename(a).lower() not in ("proton", "wine64", "wine", "wineserver"):
                return _strip_ext(_basename(a))
    # Otherwise the first process below the launcher that isn't a shell/wrapper.
    for pid in chain:
        argv = _read_cmdline(pid)
        if argv and _basename(argv[0]) not in WRAPPERS:
            name = _program_name(argv)
            rom = _rom_name(argv)
            return f"{name} - {rom}" if rom else name
    return _program_name(_read_cmdline(chain[-1]))


async def _gamescope_focus():
    """Return (focused_window, [(window, appid, pid), ...]) from gamescope, or None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "xprop", "-root", "GAMESCOPE_FOCUSED_WINDOW", "GAMESCOPE_FOCUSABLE_WINDOWS",
            env={"DISPLAY": ":0"}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), 2)
    except Exception:
        return None
    focused, triples = None, []
    for line in out.decode(errors="replace").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        nums = [int(x) for x in re.findall(r"\d+", value)]
        if name.startswith("GAMESCOPE_FOCUSED_WINDOW") and nums:
            focused = nums[0]
        elif name.startswith("GAMESCOPE_FOCUSABLE_WINDOWS"):
            triples = [tuple(nums[i:i + 3]) for i in range(0, len(nums) - 2, 3)]
    if focused is None:
        return None
    return focused, triples


async def resolve_target(steam_appid: str, steam_appname: str):
    """Return (profile_key, display_name) for what is actually on screen."""
    default = (steam_appid, steam_appname)
    if not steam_appid.isdigit():
        return default
    focus = await _gamescope_focus()
    if not focus:
        return default
    focused, triples = focus
    app = int(steam_appid)
    seen = _window_pids.setdefault(app, set())
    seen.update(pid for _, a, pid in triples if a == app and pid > 0)
    for pid in list(seen):
        if not os.path.exists(f"/proc/{pid}"):
            seen.discard(pid)

    hit = next(((w, a, pid) for w, a, pid in triples if w == focused), None)
    if not hit or hit[1] != app or hit[2] <= 0:
        return default  # Steam UI or another app has focus

    # Walk up from the focused process; stop at the first ancestor owning a window of this app.
    chain, pid = [], hit[2]
    while pid > 1 and len(chain) < 64:
        parent = _read_ppid(pid)
        chain.insert(0, pid)
        if parent in seen:
            return f"{steam_appid}/{_sanitize(_game_name(chain))}", None
        pid = parent
    return default  # the focused window belongs to the launched app itself


async def resolve_with_name(steam_appid: str, steam_appname: str):
    key, name = await resolve_target(steam_appid, steam_appname)
    if name is None:
        game = key.split("/", 1)[1]
        name = f"{game} ({steam_appname})"
    return key, name
