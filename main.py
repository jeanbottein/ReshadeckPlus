import decky_plugin
from pathlib import Path
import json
import os
import subprocess
import shutil
import asyncio
import re

logger = decky_plugin.logger

destination_folder = decky_plugin.DECKY_USER_HOME + "/.local/share/gamescope/reshade/Shaders"
textures_destination = decky_plugin.DECKY_USER_HOME + "/.local/share/gamescope/reshade/Textures"
shaders_folder = decky_plugin.DECKY_PLUGIN_DIR + "/shaders"
textures_folder = decky_plugin.DECKY_PLUGIN_DIR + "/textures"
config_file = decky_plugin.DECKY_PLUGIN_SETTINGS_DIR + "/config.json"
crash_file = decky_plugin.DECKY_PLUGIN_SETTINGS_DIR + "/crash.json"

# ---------------------------------------------------------------------------
# Regex patterns for parsing .fx uniform parameters
# ---------------------------------------------------------------------------

# Annotated uniform:  uniform <type> <name> < ui_... > = <default>;
_RE_ANNOTATED = re.compile(
    r"uniform\s+(float|bool|int)\s+(\w+)\s*<\s*([^>]*)\s*>\s*=\s*(.*?)\s*;",
    re.DOTALL,
)

# Plain uniform (CAS-style):  uniform <type> <name>  = <value>;
# Excludes uniforms that have a < > annotation block
_RE_PLAIN = re.compile(
    r"uniform\s+(float|bool|int)\s+(\w+)\s*=\s*([-+]?\d+\.?\d*)\s*;",
)

# Helpers to pull individual ui_ fields out of the annotation block
_RE_UI = {
    "ui_type":  re.compile(r'ui_type\s*=\s*"(\w+)"'),
    "ui_min":   re.compile(r'ui_min\s*=\s*([-+]?\d+\.?\d*)'),
    "ui_max":   re.compile(r'ui_max\s*=\s*([-+]?\d+\.?\d*)'),
    "ui_step":  re.compile(r'ui_step\s*=\s*([-+]?\d+\.?\d*)'),
    "ui_label": re.compile(r'ui_label\s*=\s*"([^"]*)"'),
}

# Regex for combo/radio ui_items  (e.g.  ui_items = "Off\0Hard Cut\0Smooth Fade\0"; )
_RE_UI_ITEMS = re.compile(r'ui_items\s*=\s*"((?:[^"\\]|\\0)*)"')

# Skip engine-provided uniforms (timer, framecount, etc.)
_RE_SOURCE = re.compile(r'source\s*=\s*"')


class Plugin:
    _enabled = False
    _current = "None"
    _appid = "Unknown"
    _appname = "Unknown"
    _per_game = False     # True = save settings under this appid; False = use _global
    _params = {}          # {shader_name: {param_name: value, ...}}
    _params_meta = {}     # cache: {shader_name: [param_dict, ...]}
    _params_meta = {}     # cache: {shader_name: [param_dict, ...]}

    # ------------------------------------------------------------------
    # Shader parameter parser
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_shader_params(shader_name: str) -> list[dict]:
        """Parse all user-tuneable uniform parameters from a .fx file.
        
        Defaults are always read from the SOURCE (pristine) shader files,
        not the patched copies in destination_folder.
        """
        # Prefer the source/pristine copy for parsing defaults
        source_file = Path(shaders_folder) / shader_name
        dest_file = Path(destination_folder) / shader_name
        fx_file = source_file if source_file.exists() else dest_file
        if not fx_file.exists():
            logger.warning(f"Shader file not found: {shader_name}")
            return []

        text = fx_file.read_text(encoding="utf-8", errors="replace")
        params: list[dict] = []

        # --- annotated uniforms ---
        for m in _RE_ANNOTATED.finditer(text):
            utype, uname, annotation, raw_default = (
                m.group(1), m.group(2), m.group(3), m.group(4).strip()
            )
            # skip engine-provided
            if _RE_SOURCE.search(annotation):
                continue

            p: dict = {"name": uname, "type": utype}

            for key, pat in _RE_UI.items():
                hit = pat.search(annotation)
                if hit:
                    p[key] = hit.group(1)

            # Parse combo / radio items (\0-separated list)
            items_hit = _RE_UI_ITEMS.search(annotation)
            if items_hit:
                raw_items = items_hit.group(1)
                # Split on literal \0 sequences, filter empty trailing entries
                p["ui_items"] = [s for s in raw_items.split("\\0") if s]

            # Parse default value
            if utype == "float":
                p["default"] = float(raw_default)
            elif utype == "bool":
                p["default"] = raw_default.lower() == "true"
            elif utype == "int":
                p["default"] = int(raw_default)
            else:
                p["default"] = raw_default

            # Coerce numeric ui_ fields
            for k in ("ui_min", "ui_max", "ui_step"):
                if k in p:
                    p[k] = float(p[k])

            # Generate label if missing
            if "ui_label" not in p:
                base = shader_name.replace(".fx", "")
                p["ui_label"] = f"{uname} [{base}]"

            params.append(p)

        # --- plain uniforms (CAS-style, no annotation block) ---
        # Only pick up lines NOT already captured by annotated regex
        annotated_names = {p["name"] for p in params}
        for m in _RE_PLAIN.finditer(text):
            utype, uname, raw_default = m.group(1), m.group(2), m.group(3)
            if uname in annotated_names:
                continue
            # Verify this isn't inside an annotation block (heuristic: check
            # that there is no '<' between start-of-line and the match)
            line_start = text.rfind("\n", 0, m.start()) + 1
            preceding = text[line_start:m.start()]
            if "<" in preceding:
                continue
            # Skip common engine uniforms by name
            if uname.lower() in ("iglobaltime", "framecount", "fcount"):
                continue

            base = shader_name.replace(".fx", "")
            p = {
                "name": uname,
                "type": utype,
                "default": float(raw_default) if utype == "float" else int(raw_default),
                "ui_type": "drag",
                "ui_min": 0.0,
                "ui_max": 2.0,
                "ui_step": 0.01,
                "ui_label": f"{uname} [{base}]",
            }
            params.append(p)

        return params

    # ------------------------------------------------------------------
    # Public API: get / set / reset parameters
    # ------------------------------------------------------------------
    async def get_shader_params(self):
        """Return the parameter list for the currently selected shader,
        with saved per-game values overlaid on top of defaults."""
        shader = Plugin._current
        if shader == "None":
            return []

        params = Plugin._parse_shader_params(shader)
        Plugin._params_meta[shader] = params  # cache

        saved = Plugin._params.get(shader, {})
        result = []
        for p in params:
            entry = dict(p)  # copy
            if p["name"] in saved:
                entry["value"] = saved[p["name"]]
            else:
                entry["value"] = p["default"]
            result.append(entry)
        return result

    async def set_shader_param(self, name: str, value):
        """Set a single parameter value, patch the .fx file, and save config."""
        shader = Plugin._current
        if shader == "None":
            return

        # Coerce type
        meta_list = Plugin._params_meta.get(shader)
        if meta_list:
            for p in meta_list:
                if p["name"] == name:
                    if p["type"] == "float":
                        value = float(value)
                    elif p["type"] == "bool":
                        value = bool(value)
                    elif p["type"] == "int":
                        value = int(value)
                    break

        if shader not in Plugin._params:
            Plugin._params[shader] = {}
        Plugin._params[shader][name] = value

        await Plugin._patch_uniform(shader, name, value)
        Plugin.save_config()

    async def reset_shader_params(self):
        """Reset all parameters of the current shader to their .fx defaults."""
        shader = Plugin._current
        if shader == "None":
            return

        params = Plugin._parse_shader_params(shader)
        Plugin._params_meta[shader] = params

        Plugin._params[shader] = {}
        for p in params:
            Plugin._params[shader][p["name"]] = p["default"]
            await Plugin._patch_uniform(shader, p["name"], p["default"])

        Plugin.save_config()

    # ------------------------------------------------------------------
    # In-place .fx patching (generalized)
    # ------------------------------------------------------------------

    # Pattern for annotated default:  > = <value> ;
    _RE_ANNO_VALUE = None  # built per-uniform below

    @staticmethod
    async def _patch_uniform(shader_name: str, uniform_name: str, value):
        fx_file = Path(destination_folder) / shader_name
        if not fx_file.exists():
            logger.error(f"Cannot patch — {fx_file} not found")
            return

        text = fx_file.read_text(encoding="utf-8", errors="replace")

        # Try annotated pattern first:
        #   uniform <type> <name> < ... > = <old_value>;
        pat_anno = re.compile(
            rf"(uniform\s+(?:float|bool|int)\s+{re.escape(uniform_name)}\s*<[^>]*>\s*=\s*)([-+]?\d+\.?\d*|true|false)(\s*;)",
            re.DOTALL | re.IGNORECASE,
        )
        m = pat_anno.search(text)
        if not m:
            # Try plain pattern:  uniform <type> <name>  = <old_value>;
            pat_plain = re.compile(
                rf"(uniform\s+(?:float|bool|int)\s+{re.escape(uniform_name)}\s*=\s*)([-+]?\d+\.?\d*|true|false)(\s*;)",
                re.IGNORECASE,
            )
            m = pat_plain.search(text)

        if not m:
            logger.warning(f"Uniform {uniform_name} not found in {shader_name}")
            return

        if isinstance(value, bool):
            new_val = "true" if value else "false"
        elif isinstance(value, float):
            new_val = f"{value:.6f}"
        elif isinstance(value, int):
            new_val = str(value)
        else:
            new_val = str(value)

        new_text = text[:m.start(2)] + new_val + text[m.end(2):]
        fx_file.write_text(new_text, encoding="utf-8")
        logger.info(f"Patched {uniform_name} → {new_val} in {shader_name}")

    # ------------------------------------------------------------------
    # Apply shader (calls set_shader.sh)
    # ------------------------------------------------------------------
    async def apply_shader(self, force: str = "true"):
        if Plugin._enabled:
            shader = Plugin._current
            # Patch all saved params into the .fx before applying
            saved = Plugin._params.get(shader, {})
            for name, value in saved.items():
                await Plugin._patch_uniform(shader, name, value)
            Plugin.save_config()
            logger.info("Applying shader " + shader)
            try:
                env = os.environ.copy()
                env["LD_LIBRARY_PATH"] = ""
                ret = subprocess.run(
                    [shaders_folder + "/set_shader.sh", shader, destination_folder, force],
                    capture_output=True, env=env,
                )
                logger.info(ret)
            except Exception:
                logger.exception("Apply shader")

    async def set_shader(self, shader_name):
        Plugin._current = shader_name
        
        Plugin.save_config()
        if Plugin._enabled:
            saved = Plugin._params.get(shader_name, {})
            for name, value in saved.items():
                await Plugin._patch_uniform(shader_name, name, value)
            logger.info("Setting and applying shader " + shader_name)
            try:
                env = os.environ.copy()
                env["LD_LIBRARY_PATH"] = ""
                ret = subprocess.run(
                    [shaders_folder + "/set_shader.sh", shader_name, destination_folder],
                    capture_output=True, env=env,
                )
                decky_plugin.logger.info(ret)
            except Exception:
                decky_plugin.logger.exception("Set shader")

    async def toggle_shader(self, shader_name):
        if shader_name != "None":
            saved = Plugin._params.get(shader_name, {})
            for name, value in saved.items():
                await Plugin._patch_uniform(shader_name, name, value)
        logger.info("Applying shader " + shader_name)
        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = ""
            ret = subprocess.run(
                [shaders_folder + "/set_shader.sh", shader_name, destination_folder],
                capture_output=True, env=env,
            )
            decky_plugin.logger.info(ret)
        except Exception:
            decky_plugin.logger.exception("Toggle shader")

    # ------------------------------------------------------------------
    # Config persistence with backward compatibility
    # ------------------------------------------------------------------
    _save_task = None  # type: asyncio.Task | None

    @staticmethod
    def _config_key():
        """Return the config key to read/write.
        If per_game is True use the appid, otherwise use '_global'."""
        return Plugin._appid if Plugin._per_game else "_global"

    @staticmethod
    def load_config():
        try:
            if not os.path.exists(config_file):
                return
            with open(config_file, "r") as f:
                data = json.load(f)

            # First check if this appid has a per-game entry
            app_config = data.get(Plugin._appid, {})
            is_per_game = app_config.get("per_game", False)
            Plugin._per_game = is_per_game

            if is_per_game:
                config = app_config
            else:
                # Fall back to _global config
                config = data.get("_global", {})

            Plugin._enabled = config.get("enabled", False)
            Plugin._current = config.get("current", "None")
            Plugin._params = config.get("params", {})

            # --- Retrocompatibility: migrate old contrast/sharpness keys ---
            if "contrast" in config or "sharpness" in config:
                cas_params = Plugin._params.get("CAS.fx", {})
                if "Contrast" not in cas_params and "contrast" in config:
                    cas_params["Contrast"] = config["contrast"]
                if "Sharpness" not in cas_params and "sharpness" in config:
                    cas_params["Sharpness"] = config["sharpness"]
                Plugin._params["CAS.fx"] = cas_params
                Plugin.save_config()
                logger.info("Migrated old contrast/sharpness config to new params format")

        except Exception as e:
            logger.error(f"Failed to read config: {e}")

    @staticmethod
    async def _save_config_delayed():
        try:
            # Wait 5 seconds before saving
            await asyncio.sleep(5)
            Plugin._save_config_immediate()
            Plugin._save_task = None
        except asyncio.CancelledError:
            # Task was cancelled (e.g. by a new save request or flush)
            pass



    @staticmethod
    def save_config():
        """Schedule a delayed save of the configuration."""
        if Plugin._save_task:
            Plugin._save_task.cancel()
        
        Plugin._save_task = asyncio.create_task(Plugin._save_config_delayed())

    @staticmethod
    def flush_pending_save():
        """Force any pending save to write to disk immediately."""
        if Plugin._save_task:
            if not Plugin._save_task.done():
                Plugin._save_task.cancel()
                Plugin._save_config_immediate()
            Plugin._save_task = None

    @staticmethod
    def _save_config_immediate():
        """Write configuration to disk immediately."""
        try:
            Path(os.path.dirname(config_file)).mkdir(parents=True, exist_ok=True)
            data = {}
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    data = json.load(f)

            key = Plugin._config_key()
            
            # Filter params to only include the current shader
            saved_params = {}
            target_shader = Plugin._current
            if target_shader in Plugin._params:
                saved_params[target_shader] = Plugin._params[target_shader]

            entry = {
                "appname": Plugin._appname if Plugin._per_game else "Global",
                "enabled": Plugin._enabled,
                "current": target_shader,
                "params": saved_params,
            }
            if Plugin._per_game:
                entry["per_game"] = True
            data[key] = entry

            # When per_game is True, also store a stub under the appid so
            # we know to load per-game on next visit even if key != appid
            if Plugin._per_game and key == Plugin._appid:
                if Plugin._appid not in data or not isinstance(data[Plugin._appid], dict):
                     data[Plugin._appid] = {}
                data[Plugin._appid]["per_game"] = True

            # When per_game is OFF, ensure the appid entry records per_game=False
            # but doesn't overwrite a per-game entry that was previously saved
            if not Plugin._per_game:
                if Plugin._appid not in data:
                    data[Plugin._appid] = {}
                data[Plugin._appid]["per_game"] = False
                data[Plugin._appid]["appname"] = Plugin._appname

            with open(config_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write config: {e}")

    # ------------------------------------------------------------------
    # Shader list
    # ------------------------------------------------------------------
    @staticmethod
    def _get_all_shaders():
        temp_pattern = re.compile(r"^.+_[A-Za-z0-9]{6}\.fx$")
        return sorted(
            (str(p.name)
            for p in Path(destination_folder).glob("*.fx")
            if not temp_pattern.match(p.name)),
            key=str.lower
        )

    async def get_shader_list(self):
        shaders = Plugin._get_all_shaders()
        return shaders

    async def get_shader_enabled(self):
        return Plugin._enabled

    async def get_current_shader(self):
        return Plugin._current

    async def get_per_game(self):
        """Return whether per-game mode is active."""
        return Plugin._per_game

    async def set_per_game(self, enabled: bool):
        """Toggle per-game mode. When switching ON, copy global config to
        per-game. When switching OFF, the game will use global config."""

        # Flush any pending save before switching modes to ensure consistency
        Plugin.flush_pending_save()

        prevEnabled = Plugin._enabled
        prevCurrent = Plugin._current
        prevParams = {}
        if prevCurrent in Plugin._params:
             prevParams = Plugin._params[prevCurrent].copy()

        Plugin._per_game = enabled
        if enabled:
            # Clone current (Global) settings to Per-Game
            Plugin.save_config()
        else:
            # Revert to Global settings (discard current Local tweaks)
            # We must force the file to say per_game=False BEFORE calling load_config,
            # otherwise load_config will see "per_game": true and switch us back.
            try:
                if os.path.exists(config_file):
                    with open(config_file, "r") as f:
                        data = json.load(f)
                    
                    if Plugin._appid not in data:
                        data[Plugin._appid] = {}
                    data[Plugin._appid]["per_game"] = False
                    
                    with open(config_file, "w") as f:
                        json.dump(data, f, indent=4)

            except Exception as e:
                decky_plugin.logger.error(f"Failed to update per_game flag: {e}")

            Plugin.load_config()
            
        decky_plugin.logger.info(f"Per-game mode set to {enabled} for {Plugin._appid}")

        currentParams = {}
        if Plugin._current in Plugin._params:
             currentParams = Plugin._params[Plugin._current]

        if Plugin._enabled and not prevEnabled:
            await Plugin.apply_shader(self)
        elif prevEnabled and not Plugin._enabled:
            await Plugin.toggle_shader(self, "None")
        elif Plugin._enabled:
             if (Plugin._current != prevCurrent) or (currentParams != prevParams):
                 await Plugin.apply_shader(self, force="false")

    async def get_game_info(self):
        """Return current game info for the frontend."""
        return {
            "appid": Plugin._appid,
            "appname": Plugin._appname,
            "per_game": Plugin._per_game,
        }

    async def set_current_game_info(self, appid: str, appname: str):
        # Recognize SteamOS menu / desktop
        if appid == "Unknown" or appid == "" or appid == "undefined":
            appid = "steamos"
            appname = "SteamOS"
        
        if appid == Plugin._appid:
            if appname != "Loading..." and appname != "Unknown" and Plugin._appname != appname:
                Plugin._appname = appname
                # If per-game settings are active, we might want to save the new name to config
                if Plugin._per_game:
                    Plugin.save_config()
            return

        decky_plugin.logger.info(f"Current game info received: AppID={appid}, Name={appname}")

        # Flush any pending save for the previous game before switching
        Plugin.flush_pending_save()

        prevEnabled = Plugin._enabled
        prevCurrent = Plugin._current
        # Capture parameters of the active shader to detect changes
        prevParams = {}
        if prevCurrent in Plugin._params:
             prevParams = Plugin._params[prevCurrent].copy()

        Plugin._appid = appid
        Plugin._appname = appname
        
        Plugin.load_config()
        
        currentParams = {}
        if Plugin._current in Plugin._params:
             currentParams = Plugin._params[Plugin._current]

        if Plugin._enabled and not prevEnabled:
            await Plugin.apply_shader(self)
        elif prevEnabled and not Plugin._enabled:
            await Plugin.toggle_shader(self, "None")
        elif Plugin._enabled:
            # If shader changed OR parameters changed, re-apply
            if (Plugin._current != prevCurrent) or (currentParams != prevParams):
                await Plugin.apply_shader(self, force="false")

    async def set_shader_enabled(self, isEnabled):
        Plugin._enabled = isEnabled
        Plugin.save_config()

    async def get_current_effect(self):
        try:
            result = subprocess.run(
                ['xprop', '-root', 'GAMESCOPE_RESHADE_EFFECT'],
                env={"DISPLAY": ":0"},
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and "=" in result.stdout:
                effect = result.stdout.split('=', 1)[1].strip().strip('"')
                return {"effect": effect}
            else:
                return {"effect": "None"}
        except Exception as e:
            logger.error(f"Failed to get current effect: {e}")
            return {"effect": "None"}

    # ------------------------------------------------------------------
    # Crash Loop Protection (Canary)
    # ------------------------------------------------------------------
    @staticmethod
    def _read_crash_count():
        try:
            if os.path.exists(crash_file):
                with open(crash_file, "r") as f:
                    return json.load(f).get("count", 0)
        except Exception:
            pass
        return 0

    @staticmethod
    def _write_crash_count(count: int):
        try:
            with open(crash_file, "w") as f:
                json.dump({"count": count}, f)
        except Exception:
            pass

    @staticmethod
    def check_crash_loop():
        count = Plugin._read_crash_count()
        # Threshold: 2 consecutive crashes
        if count >= 2:
            logger.warning(f"Crash loop detected (count={count}). Disabling shaders.")
            Plugin._enabled = False
            Plugin.save_config()  # Persist disabled state
            Plugin._write_crash_count(0) # Reset count after taking action
            return True
        else:
            Plugin._write_crash_count(count + 1)
            return False

    @staticmethod
    async def mark_stable():
        """Wait for 30 seconds of stable operation, then reset crash count."""
        try:
            await asyncio.sleep(30)
            logger.info("System stable. Resetting crash count.")
            Plugin._write_crash_count(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in mark_stable: {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def _main(self):
        # 1. Check for crash loop immediately
        Plugin.check_crash_loop()

        try:
            Path(destination_folder).mkdir(parents=True, exist_ok=True)
            for item in Path(shaders_folder).glob("*.fx"):
                try:
                    dest_path = shutil.copy(item, destination_folder)
                    os.chmod(dest_path, 0o644)
                except Exception:
                    decky_plugin.logger.debug(f"could not copy {item}")
            # Copy textures (including subdirectories) to the gamescope Textures folder
            if Path(textures_folder).exists():
                try:
                    shutil.copytree(
                        textures_folder,
                        textures_destination,
                        dirs_exist_ok=True,
                    )
                    # Fix permissions on all copied files
                    for root, dirs, files in os.walk(textures_destination):
                        for f in files:
                            os.chmod(os.path.join(root, f), 0o644)
                except Exception:
                    decky_plugin.logger.debug(f"could not copy textures")
            decky_plugin.logger.info("Initialized")
            decky_plugin.logger.info(str(await Plugin.get_shader_list(self)))
            Plugin.load_config()
            if Plugin._enabled:
                await asyncio.sleep(5)
                await Plugin.apply_shader(self)
            
            # Start stability timer
            asyncio.create_task(Plugin.mark_stable())
        except Exception:
            decky_plugin.logger.exception("main")
