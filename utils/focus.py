"""Name the profile after the game a launcher started, using gamescope's focused window.

Games started by a launcher share its Steam AppId; gamescope still tells which process owns the focused window.
"""
import asyncio
import os
import re

WRAPPERS = {"sh", "bash", "dash", "zsh", "env", "nohup", "setsid", "reaper",
            "steam-launch-wrapper", "gamemoderun", "mangohud", "strace", "timeout"}
NON_ROM_EXT = {".ini", ".cfg", ".conf", ".json", ".yml", ".yaml", ".xml", ".txt", ".log", ".toml"}
STRIP_EXT = (".appimage", ".exe", ".x86_64", ".x86", ".sh", ".bin", ".elf")
PROTON_STUBS = {"steam.exe", "start.exe", "explorer.exe"}

_launcher_pids: dict = {}  # appid -> pids seen owning a window (launchers may hide theirs)


def _read_cmdline(pid: int) -> list:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def _read_ppid(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat") as f:
            return int(f.read().rsplit(")", 1)[1].split()[1])  # comm may contain ")"
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
    return re.sub(r"[^A-Za-z0-9 ._+-]", "_", name).strip(" ._")[:64] or "unknown"


def _program_name(argv: list) -> str:
    exe = _basename(argv[0])
    if exe == "flatpak":
        app_id = next((a for a in argv[1:] if "." in a and not a.startswith("-")), None)
        if app_id:
            return app_id.split(".")[-1]
    return _strip_ext(exe)


def _rom_name(argv: list):
    for arg in reversed(argv[1:]):
        if os.path.isabs(arg) and os.path.isfile(arg) and os.path.splitext(arg)[1].lower() not in NON_ROM_EXT:
            return os.path.splitext(os.path.basename(arg))[0]
    return None


def _windows_exe(chain: list):
    for pid in reversed(chain):
        for arg in _read_cmdline(pid):
            name = _basename(arg)
            if name.lower().endswith(".exe") and name.lower() not in PROTON_STUBS:
                return _strip_ext(name)
    return None


def _game_name(chain: list) -> str:
    """chain: pids from the launcher's child down to the focused process."""
    exe = _windows_exe(chain)
    if exe:
        return exe
    for pid in chain:
        argv = _read_cmdline(pid)
        if argv and _basename(argv[0]) not in WRAPPERS:
            rom = _rom_name(argv)
            return f"{_program_name(argv)} - {rom}" if rom else _program_name(argv)
    return "unknown"


async def _gamescope_focus():
    """(focused window, [(window, appid, pid), ...]) from gamescope, or None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "xprop", "-root", "GAMESCOPE_FOCUSED_WINDOW", "GAMESCOPE_FOCUSABLE_WINDOWS",
            env={**os.environ, "DISPLAY": ":0"},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 2)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None
    atoms = {}
    for line in out.decode(errors="replace").splitlines():
        name, _, value = line.partition("=")
        atoms[name.split("(")[0].strip()] = [int(n) for n in re.findall(r"\d+", value)]
    focused = atoms.get("GAMESCOPE_FOCUSED_WINDOW")
    if not focused:
        return None
    nums = atoms.get("GAMESCOPE_FOCUSABLE_WINDOWS", [])
    return focused[0], [tuple(nums[i:i + 3]) for i in range(0, len(nums) - 2, 3)]


def _remember_launchers(app: int, windows: list) -> set:
    pids = _launcher_pids.setdefault(app, set())
    pids.update(pid for _, appid, pid in windows if appid == app and pid > 0)
    pids.intersection_update(p for p in list(pids) if os.path.exists(f"/proc/{p}"))
    return pids


def _chain_below_launcher(pid: int, launchers: set):
    """Pids from the launcher's child down to pid, or None if pid wasn't started by a launcher."""
    chain = []
    while pid > 1 and len(chain) < 64:
        chain.insert(0, pid)
        pid = _read_ppid(pid)
        if pid in launchers:
            return chain
    return None


async def resolve_profile(steam_appid: str, steam_appname: str):
    """(profile key, display name) for what is on screen: "<appid>/<game>" when a launcher started it."""
    default = (steam_appid, steam_appname)
    focus = await _gamescope_focus() if steam_appid.isdigit() else None
    if not focus:
        return default
    focused, windows = focus
    app = int(steam_appid)
    launchers = _remember_launchers(app, windows)
    pid = next((p for w, a, p in windows if w == focused and a == app), 0)
    chain = _chain_below_launcher(pid, launchers) if pid > 0 else None
    if not chain:
        return default
    game = _sanitize(_game_name(chain))
    return f"{steam_appid}/{game}", f"{game} ({steam_appname})"
