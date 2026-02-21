import decky_plugin
from pathlib import Path
import json
import os
import subprocess
import shutil
import asyncio
import re
import time

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
    # --- 1. State Variables (Backend Memory) ---
    _master_switch = True
    _active_shader = "None"
    _shader_parameters = {}  # {shader_name: {param_name: value, ...}}
    _crash_detected = False
    _per_game_mode = False
    _current_appid = "Unknown"
    
    # State related to packages and caching
    _appname = "Unknown"
    _active_category = "Default"
    _params_meta = {}  # cache: {shader_name: [param_dict, ...]}
    
    # Task Management
    _active_crash_monitor_task = None
    _debounce_task = None

    # ------------------------------------------------------------------
    # Shader parameter parser
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_shader_params(shader_name: str) -> list[dict]:
        """Parse all user-tuneable uniform parameters from a .fx file."""
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
            if _RE_SOURCE.search(annotation):
                continue

            p: dict = {"name": uname, "type": utype}

            for key, pat in _RE_UI.items():
                hit = pat.search(annotation)
                if hit:
                    p[key] = hit.group(1)

            items_hit = _RE_UI_ITEMS.search(annotation)
            if items_hit:
                raw_items = items_hit.group(1)
                p["ui_items"] = [s for s in raw_items.split("\\0") if s]

            if utype == "float":
                p["default"] = float(raw_default)
            elif utype == "bool":
                p["default"] = raw_default.lower() == "true"
            elif utype == "int":
                p["default"] = int(raw_default)
            else:
                p["default"] = raw_default

            for k in ("ui_min", "ui_max", "ui_step"):
                if k in p:
                    p[k] = float(p[k])

            if "ui_label" not in p:
                base = shader_name.replace(".fx", "")
                p["ui_label"] = f"{uname} [{base}]"

            params.append(p)

        # --- plain uniforms (CAS-style, no annotation block) ---
        annotated_names = {p["name"] for p in params}
        for m in _RE_PLAIN.finditer(text):
            utype, uname, raw_default = m.group(1), m.group(2), m.group(3)
            if uname in annotated_names:
                continue
            line_start = text.rfind("\n", 0, m.start()) + 1
            preceding = text[line_start:m.start()]
            if "<" in preceding:
                continue
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
    # In-place .fx patching -> Memory Patching
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_params_to_content(text: str, params: dict) -> str:
        """Apply parameter values to shader content in memory."""
        if not params:
            return text

        for uniform_name, value in params.items():
            pat_anno = re.compile(
                rf"(uniform\s+(?:float|bool|int)\s+{re.escape(uniform_name)}\s*<[^>]*>\s*=\s*)([-+]?\d+\.?\d*|true|false)(\s*;)",
                re.DOTALL | re.IGNORECASE,
            )
            m = pat_anno.search(text)
            if not m:
                pat_plain = re.compile(
                    rf"(uniform\s+(?:float|bool|int)\s+{re.escape(uniform_name)}\s*=\s*)([-+]?\d+\.?\d*|true|false)(\s*;)",
                    re.IGNORECASE,
                )
                m = pat_plain.search(text)

            if not m:
                continue

            if isinstance(value, bool):
                new_val = "true" if value else "false"
            elif isinstance(value, float):
                new_val = f"{value:.6f}"
            elif isinstance(value, int):
                new_val = str(value)
            else:
                new_val = str(value)

            text = text[:m.start(2)] + new_val + text[m.end(2):]
            
        return text

    @staticmethod
    def _generate_staging_shader(shader_name: str) -> str:
        """Read source shader, patch in memory, write to fixed staging file .reshadeck.fx"""
        source_file = Path(shaders_folder) / shader_name
        if not source_file.exists():
            source_file = Path(destination_folder) / shader_name
            
        if not source_file.exists():
            logger.error(f"Generate staging: Source {shader_name} not found")
            return shader_name

        text = source_file.read_text(encoding="utf-8", errors="replace")
        
        params = Plugin._shader_parameters.get(shader_name, {})
        patched_text = Plugin._apply_params_to_content(text, params)
        
        staging_filename = ".reshadeck.fx"
        full_dest_path = Path(destination_folder) / staging_filename
        full_dest_path.write_text(patched_text, encoding="utf-8")
        
        return staging_filename

    # ------------------------------------------------------------------
    # Subroutine: apply_shader
    # ------------------------------------------------------------------
    @staticmethod
    async def _apply_shader_internal(target_shader: str):
        """
        Pure dumb function that takes target_shader and shells out to set_shader.sh.
        Does NOT contain logical checks for whether it should run.
        """
        staging_file = target_shader
        if target_shader != "None":
            staging_file = Plugin._generate_staging_shader(target_shader)
            
        logger.info(f"Applying shader {target_shader} via {staging_file}")
        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = ""
            
            proc = await asyncio.create_subprocess_exec(
                shaders_folder + "/set_shader.sh", staging_file, destination_folder,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await proc.communicate()
            logger.info(f"Apply shader result: {proc.returncode}")
            if stdout: logger.debug(f"stdout: {stdout.decode()}")
            if stderr: logger.error(f"stderr: {stderr.decode()}")
        except Exception as e:
            logger.exception(f"Apply shader failed: {e}")

    # ------------------------------------------------------------------
    # Subroutine: Crash Detection
    # ------------------------------------------------------------------
    @staticmethod
    async def _crash_detection_subroutine():
        """
        Managed asyncio.Task that lives for precisely 60 seconds.
        Looks for gamescope coredumps and instantly kills shaders if found.
        """
        start_time = time.time()
        coredump_path = Path("/var/lib/systemd/coredump")
        
        logger.info("Crash Detection Subroutine started (60s window).")
        
        try:
            while (time.time() - start_time) < 60:
                await asyncio.sleep(2.0)
                
                if not coredump_path.exists():
                    continue
                    
                files = list(coredump_path.glob("core.gamescope-wl.*.zst"))
                if not files:
                    continue
                    
                latest_file = max(files, key=os.path.getmtime)
                latest_timestamp = latest_file.stat().st_mtime
                
                if latest_timestamp > start_time:
                    logger.error(f"NEW CRASH DETECTED. File: {latest_file.name}. Disabling shaders.")
                    
                    Plugin._master_switch = False
                    Plugin._crash_detected = True
                    Plugin._save_config_immediate()
                    await Plugin._apply_shader_internal("None")
                    
                    # Record the crash timestamp so we don't trip on it at startup
                    Plugin._write_crash_data(1, str(latest_timestamp))
                    
                    return # Exit subroutine
                    
            logger.info("Crash Detection Subroutine cleanly expired (no crash).")
        except asyncio.CancelledError:
            logger.info("Crash Detection Subroutine cancelled.")
        except Exception as e:
            logger.error(f"Error in Crash Detection Subroutine: {e}")

    @staticmethod
    def _trigger_crash_detection():
        if Plugin._active_crash_monitor_task:
            Plugin._active_crash_monitor_task.cancel()
        Plugin._active_crash_monitor_task = asyncio.create_task(Plugin._crash_detection_subroutine())

    @staticmethod
    def _cancel_crash_detection():
        if Plugin._active_crash_monitor_task:
            Plugin._active_crash_monitor_task.cancel()
            Plugin._active_crash_monitor_task = None

    # ------------------------------------------------------------------
    # Config persistence 
    # ------------------------------------------------------------------
    @staticmethod
    def _config_key():
        return Plugin._current_appid if Plugin._per_game_mode else "_global"

    @staticmethod
    def _save_config_immediate():
        """Consolidated save logic."""
        try:
            Path(os.path.dirname(config_file)).mkdir(parents=True, exist_ok=True)
            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            key = Plugin._config_key()
            
            saved_params = {}
            if Plugin._active_shader in Plugin._shader_parameters:
                saved_params[Plugin._active_shader] = Plugin._shader_parameters[Plugin._active_shader]

            entry = {
                "appname": Plugin._appname if Plugin._per_game_mode else "Global",
                "current": Plugin._active_shader,
                "active_category": Plugin._active_category,
                "params": saved_params,
            }
            if Plugin._per_game_mode:
                entry["per_game"] = True
            data[key] = entry
            
            data["master_enabled"] = Plugin._master_switch

            if Plugin._per_game_mode and key == Plugin._current_appid:
                if Plugin._current_appid not in data or not isinstance(data[Plugin._current_appid], dict):
                     data[Plugin._current_appid] = {}
                data[Plugin._current_appid]["per_game"] = True

            if not Plugin._per_game_mode:
                if Plugin._current_appid not in data:
                    data[Plugin._current_appid] = {}
                data[Plugin._current_appid]["per_game"] = False
                data[Plugin._current_appid]["appname"] = Plugin._appname

            with open(config_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write config: {e}")

    @staticmethod
    def _load_config_state(appid: str):
        """Load state from file into memory based on appid."""
        try:
            if not os.path.exists(config_file):
                return
            with open(config_file, "r") as f:
                data = json.load(f)

            app_config = data.get(appid, {})
            is_per_game = app_config.get("per_game", False)
            Plugin._per_game_mode = is_per_game

            config = app_config if is_per_game else data.get("_global", {})

            Plugin._master_switch = data.get("master_enabled", True)
            Plugin._active_shader = config.get("current", "None")
            Plugin._active_category = config.get("active_category", "Default")
            Plugin._shader_parameters = config.get("params", {})
            
        except Exception as e:
            logger.error(f"Failed to read config: {e}")

    @staticmethod
    def _read_crash_data():
        try:
            if os.path.exists(crash_file):
                with open(crash_file, "r") as f:
                    data = json.load(f)
                    return {"count": data.get("count", 0), "last_timestamp": data.get("last_timestamp", "0")}
        except Exception:
            pass
        return {"count": 0, "last_timestamp": "0"}

    @staticmethod
    def _write_crash_data(count: int, last_timestamp: str):
        try:
            with open(crash_file, "w") as f:
                json.dump({"count": count, "last_timestamp": last_timestamp}, f)
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Async Event Handlers (Called from UI or Lifecycle)
    # ------------------------------------------------------------------
    
    # Event A: on_plugin_load()
    async def _main(self):
        try:
            Plugin._install_resources()
            logger.info("Plugin Initialized (Event A: on_plugin_load)")
            
            # 1. Load config
            Plugin._load_config_state(Plugin._current_appid)
            
            # 1.5. Force disable if old version exists
            old_dir = decky_plugin.DECKY_USER_HOME + "/homebrew/plugins/Reshadeck"
            if os.path.isdir(old_dir):
                Plugin._master_switch = False
                Plugin._save_config_immediate()
            
            # 2. Startup Canary Check
            if Plugin._master_switch and Plugin._active_shader != "None":
                crash_data = Plugin._read_crash_data()
                try:
                    last_known_timestamp = float(crash_data.get("last_timestamp", "0"))
                except ValueError:
                    last_known_timestamp = 0.0
                    
                coredump_path = Path("/var/lib/systemd/coredump")
                crashed_recently = False
                
                if coredump_path.exists():
                    files = list(coredump_path.glob("core.gamescope-wl.*.zst"))
                    if files:
                        latest_file = max(files, key=os.path.getmtime)
                        latest_timestamp = latest_file.stat().st_mtime
                        
                        # Check if crash is new and within last 5 minutes
                        if latest_timestamp > last_known_timestamp and (time.time() - latest_timestamp) <= 300:
                            crashed_recently = True
                            
                if crashed_recently:
                    logger.error("Canary check failed. Recent crash detected on startup.")
                    Plugin._master_switch = False
                    Plugin._crash_detected = True
                    Plugin._save_config_immediate()
                    Plugin._write_crash_data(1, str(time.time()))
                    return # Exit without applying
                
            # 3. Apply shader
            if Plugin._master_switch and Plugin._active_shader != "None":
                await asyncio.sleep(3) # Give X time to initialize
                await Plugin._apply_shader_internal(Plugin._active_shader)
                
        except Exception:
            logger.exception("main")

    # Event B: on_master_switch_changed(is_enabled)
    async def set_master_enabled(self, enabled: bool):
        logger.info(f"Event B: on_master_switch_changed({enabled})")
        
        old_dir = decky_plugin.DECKY_USER_HOME + "/homebrew/plugins/Reshadeck"
        if enabled and os.path.isdir(old_dir):
            enabled = False
        
        # 1. Cancel active crash detection
        Plugin._cancel_crash_detection()
        
        # 2. Set crash_detected = false
        Plugin._crash_detected = False
        
        # 3. Set master_switch = is_enabled
        Plugin._master_switch = enabled
        
        # 4. If is_enabled == false
        if not enabled:
            await Plugin._apply_shader_internal("None")
            
        # 5. If is_enabled == true AND active_shader != "None"
        elif enabled and Plugin._active_shader != "None":
            Plugin._trigger_crash_detection()
            await Plugin._apply_shader_internal(Plugin._active_shader)
            
        # 6. Save config to disk
        Plugin._save_config_immediate()

    # Event C: on_active_app_changed(appid)
    async def set_current_game_info(self, appid: str, appname: str):
        if appid in ["Unknown", "", "undefined", "0"]:
            appid = "steamos"
            appname = "SteamOS"
            
        if appname in ["Loading...", "Unknown"]:
            return
            
        logger.info(f"Event C: on_active_app_changed({appid})")

        # 1. Cancel any pending debounce tasks
        if Plugin._debounce_task:
            Plugin._debounce_task.cancel()
            Plugin._debounce_task = None
            
        # 2. Set current_appid
        Plugin._current_appid = appid
        Plugin._appname = appname
        
        # 3. If master_switch == false -> Halt execution
        if not Plugin._master_switch:
             # Still load config so the UI updates correctly
             Plugin._load_config_state(appid)
             return
             
        # 4,5,6. Load config profile
        Plugin._load_config_state(appid)
        
        # 7. Execute apply_shader
        await Plugin._apply_shader_internal(Plugin._active_shader)

    # Event E: on_shader_changed(new_shader)
    async def set_shader(self, shader_name: str):
        # We handle toggling/setting in the same handler
        logger.info(f"Event E: on_shader_changed({shader_name})")
        
        # 1. Cancel active crash detection tasks
        Plugin._cancel_crash_detection()
        
        # 2. Update active_shader
        Plugin._active_shader = shader_name
        
        # 3. Save config
        Plugin._save_config_immediate()
        
        # 4. If master_switch == false -> Halt execution
        if not Plugin._master_switch:
            # We must still clear current shaders visually if they picked None
            if shader_name == "None":
                 await Plugin._apply_shader_internal("None")
            return
            
        # 5. Trigger Crash Detection
        if shader_name != "None":
            Plugin._trigger_crash_detection()
            
        # 6. Execute apply_shader
        await Plugin._apply_shader_internal(Plugin._active_shader)

    async def toggle_shader(self, shader_name: str):
        await self.set_shader(shader_name)

    # Event F: on_parameters_changed(new_parameters)
    async def set_shader_param(self, name: str, value):
        shader = Plugin._active_shader
        if shader == "None":
            return
            
        # Coerce type
        meta_list = Plugin._params_meta.get(shader)
        if meta_list:
            for p in meta_list:
                if p["name"] == name:
                    if p["type"] == "float": value = float(value)
                    elif p["type"] == "bool": value = bool(value)
                    elif p["type"] == "int": value = int(value)
                    break

        # 1. Update shader_parameters
        if shader not in Plugin._shader_parameters:
            Plugin._shader_parameters[shader] = {}
        Plugin._shader_parameters[shader][name] = value
        
        # 2,3. Cancel and Schedule apply_debounced
        if Plugin._debounce_task:
            Plugin._debounce_task.cancel()
        Plugin._debounce_task = asyncio.create_task(Plugin._apply_debounced())

    @staticmethod
    async def _apply_debounced():
        try:
            await asyncio.sleep(1.0)
            logger.info("Executing debounced parameter apply")
            
            # 1. Cancel crash detection
            Plugin._cancel_crash_detection()
            
            # 2. Save config immediately
            Plugin._save_config_immediate()
            
            # 3. If master == false, halt
            if not Plugin._master_switch:
                return
                
            # 4. Trigger Crash Detection
            Plugin._trigger_crash_detection()
            
            # 5. Execute apply_shader
            await Plugin._apply_shader_internal(Plugin._active_shader)
            
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Utility getters/setters for UI (Event D: on_ui_opened implicit syncing)
    # ------------------------------------------------------------------
    async def get_shader_params(self):
        shader = Plugin._active_shader
        if shader == "None":
            return []
        params = Plugin._parse_shader_params(shader)
        Plugin._params_meta[shader] = params
        saved = Plugin._shader_parameters.get(shader, {})
        result = []
        for p in params:
            entry = dict(p)
            entry["value"] = saved.get(p["name"], p["default"])
            result.append(entry)
        return result

    async def reset_shader_params(self):
        shader = Plugin._active_shader
        if shader == "None":
            return
        params = Plugin._parse_shader_params(shader)
        Plugin._params_meta[shader] = params
        Plugin._shader_parameters[shader] = {p["name"]: p["default"] for p in params}
        Plugin._save_config_immediate()
        
        # Trigger an apply if allowed
        if Plugin._master_switch:
             await Plugin._apply_shader_internal(Plugin._active_shader)

    async def get_master_enabled(self):
        return Plugin._master_switch

    async def get_current_shader(self):
        return Plugin._active_shader

    async def get_per_game(self):
        return Plugin._per_game_mode

    async def set_per_game(self, enabled: bool):
        logger.info(f"Setting per_game_mode: {enabled}")
        
        # Replicates Event C logic conceptually when mode flips
        Plugin._per_game_mode = enabled
        if enabled:
            Plugin._save_config_immediate()
        else:
            # Revert to global
            try:
                if os.path.exists(config_file):
                    with open(config_file, "r") as f:
                        data = json.load(f)
                    if Plugin._current_appid not in data:
                        data[Plugin._current_appid] = {}
                    data[Plugin._current_appid]["per_game"] = False
                    with open(config_file, "w") as f:
                        json.dump(data, f, indent=4)
            except Exception:
                pass
            Plugin._load_config_state(Plugin._current_appid)
            
        # Re-apply
        if Plugin._master_switch:
            await Plugin._apply_shader_internal(Plugin._active_shader)

    async def get_game_info(self):
        return {
            "appid": Plugin._current_appid,
            "appname": Plugin._appname,
            "per_game": Plugin._per_game_mode,
            "active_category": Plugin._active_category,
        }

    async def set_active_category(self, category: str):
        if category != Plugin._active_category:
            Plugin._active_category = category
            Plugin._save_config_immediate()

    async def get_crash_detected(self):
        return Plugin._crash_detected

    async def get_old_version_exists(self):
        old_dir = decky_plugin.DECKY_USER_HOME + "/homebrew/plugins/Reshadeck"
        return os.path.isdir(old_dir)

    async def get_shader_list(self, category: str = "Default"):
        temp_pattern = re.compile(r"^.+_[A-Za-z0-9]{6}\.fx$")
        target_dir = Path(destination_folder)
        if category not in ("Default", "None"):
             target_dir = target_dir / category
        if not target_dir.exists():
            return []
        files = target_dir.glob("*.fx")
        results = []
        for p in files:
            if p.name.startswith("."): continue
            if not temp_pattern.match(p.name):
                if category == "Default": results.append(p.name)
                else: results.append(f"{category}/{p.name}")
        return sorted(results, key=str.lower)

    async def get_shader_packages(self):
        p = Path(destination_folder)
        if not p.exists(): return ["Default"]
        dirs = [x.name for x in p.iterdir() if x.is_dir() and not x.name.startswith(".")]
        dirs = [d for d in dirs if d.lower() != "default"]
        return ["Default"] + sorted(dirs, key=str.lower)

    async def get_current_effect(self):
        try:
            env = {"DISPLAY": ":0"}
            proc = await asyncio.create_subprocess_exec(
                'xprop', '-root', 'GAMESCOPE_RESHADE_EFFECT',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode() if stdout else ""
            if proc.returncode == 0 and "=" in output:
                effect = output.split('=', 1)[1].strip().strip('"')
                return {"effect": effect}
            else:
                return {"effect": "None"}
        except Exception:
            return {"effect": "None"}

    async def reset_reshade_directory(self):
        reshade_root = Path(destination_folder).parent 
        if reshade_root.exists():
            try:
                shutil.rmtree(reshade_root)
            except Exception as e:
                logger.error(f"Failed to delete reshade directory: {e}")
                return False
        Plugin._install_resources()
        return True

    async def reset_configuration(self):
        try:
            if os.path.exists(config_file): os.remove(config_file)
            if os.path.exists(crash_file): os.remove(crash_file)
        except Exception:
            return False

        Plugin._master_switch = True
        Plugin._active_shader = "None"
        Plugin._per_game_mode = False
        Plugin._active_category = "Default"
        Plugin._shader_parameters = {}
        Plugin._params_meta = {}
        Plugin._crash_detected = False
        
        if Plugin._debounce_task:
            Plugin._debounce_task.cancel()
            Plugin._debounce_task = None
            
        await Plugin._apply_shader_internal("None")
        return True

    @staticmethod
    def _install_resources():
        try:
            Path(destination_folder).mkdir(parents=True, exist_ok=True)
            try:
                shutil.copytree(shaders_folder, destination_folder, dirs_exist_ok=True)
            except Exception:
                pass
            for root, dirs, files in os.walk(destination_folder):
                for f in files:
                    if f.endswith((".fx", ".fxh", ".sh")):
                        try:
                            path = os.path.join(root, f)
                            os.chmod(path, 0o644)
                            if f.endswith(".sh"):
                                os.chmod(path, 0o755)
                        except: pass
            if Path(textures_folder).exists():
                try:
                    shutil.copytree(textures_folder, textures_destination, dirs_exist_ok=True)
                    for root, dirs, files in os.walk(textures_destination):
                        for f in files: os.chmod(os.path.join(root, f), 0o644)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to install resources: {e}")

