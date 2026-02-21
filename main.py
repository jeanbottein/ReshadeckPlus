import decky_plugin
import json
import os
import shutil
import asyncio
import time
import re
import sys
from pathlib import Path

# Add current directory to path so local imports work
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Import our separated modules
from utils.constants import logger, destination_folder, shaders_folder, textures_folder, textures_destination, config_file, crash_file
from utils.state import State
from utils.config import save_config_immediate, load_config_state
from utils.shader import parse_shader_params, apply_shader_internal
from utils.crash import trigger_crash_detection, cancel_crash_detection, read_crash_data, write_crash_data

class Plugin:

    # ------------------------------------------------------------------
    # Async Event Handlers (Called from UI or Lifecycle)
    # ------------------------------------------------------------------
    
    # Event A: on_plugin_load()
    async def _main(self):
        try:
            Plugin._install_resources()
            logger.info("Plugin Initialized (Event A: on_plugin_load)")
            
            # 1. Load config
            load_config_state(State.current_appid)
            
            # 1.5. Force disable if old version exists
            old_dir = decky_plugin.DECKY_USER_HOME + "/homebrew/plugins/Reshadeck"
            if os.path.isdir(old_dir):
                State.master_switch = False
                save_config_immediate()
            
            # 2. Startup Canary Check
            if State.master_switch and State.active_shader != "None":
                crash_data = read_crash_data()
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
                    State.master_switch = False
                    State.crash_detected = True
                    save_config_immediate()
                    write_crash_data(1, str(time.time()))
                    return # Exit without applying
                
            # 3. Apply shader
            if State.master_switch and State.active_shader != "None":
                await asyncio.sleep(3) # Give X time to initialize
                await apply_shader_internal(State.active_shader)
                
        except Exception:
            logger.exception("main")

    # Event B: on_master_switch_changed(is_enabled)
    async def set_master_enabled(self, enabled: bool):
        logger.info(f"Event B: on_master_switch_changed({enabled})")
        
        old_dir = decky_plugin.DECKY_USER_HOME + "/homebrew/plugins/Reshadeck"
        if enabled and os.path.isdir(old_dir):
            enabled = False
        
        # 1. Cancel active crash detection
        cancel_crash_detection()
        
        # 2. Set crash_detected = false
        State.crash_detected = False
        
        # 3. Set master_switch = is_enabled
        State.master_switch = enabled
        
        # 4. If is_enabled == false
        if not enabled:
            await apply_shader_internal("None")
            
        # 5. If is_enabled == true AND active_shader != "None"
        elif enabled and State.active_shader != "None":
            trigger_crash_detection()
            await apply_shader_internal(State.active_shader)
            
        # 6. Save config to disk
        save_config_immediate()

    # Event C: on_active_app_changed(appid)
    async def set_current_game_info(self, appid: str, appname: str):
        if appid in ["Unknown", "", "undefined", "0"]:
            appid = "steamos"
            appname = "SteamOS"
            
        if appname in ["Loading...", "Unknown"]:
            return
            
        logger.info(f"Event C: on_active_app_changed({appid})")

        # 1. Cancel any pending debounce tasks
        if State.debounce_task:
            State.debounce_task.cancel()
            State.debounce_task = None
            
        # 2. Set current_appid
        State.current_appid = appid
        State.appname = appname
        
        # 3. If master_switch == false -> Halt execution
        if not State.master_switch:
             # Still load config so the UI updates correctly
             load_config_state(appid)
             return
             
        # 4,5,6. Load config profile
        load_config_state(appid)
        
        # 7. Execute apply_shader
        await apply_shader_internal(State.active_shader)

    # Event E: on_shader_changed(new_shader)
    async def set_shader(self, shader_name: str):
        # We handle toggling/setting in the same handler
        logger.info(f"Event E: on_shader_changed({shader_name})")
        
        # 1. Cancel active crash detection tasks
        cancel_crash_detection()
        
        # 2. Update active_shader
        State.active_shader = shader_name
        
        # 3. Save config
        save_config_immediate()
        
        # 4. If master_switch == false -> Halt execution
        if not State.master_switch:
            # We must still clear current shaders visually if they picked None
            if shader_name == "None":
                 await apply_shader_internal("None")
            return
            
        # 5. Trigger Crash Detection
        if shader_name != "None":
            trigger_crash_detection()
            
        # 6. Execute apply_shader
        await apply_shader_internal(State.active_shader)

    async def toggle_shader(self, shader_name: str):
        await self.set_shader(shader_name)

    # Event F: on_parameters_changed(new_parameters)
    async def set_shader_param(self, name: str, value):
        shader = State.active_shader
        if shader == "None":
            return
            
        # Coerce type
        meta_list = State.params_meta.get(shader)
        if meta_list:
            for p in meta_list:
                if p["name"] == name:
                    if p["type"] == "float": value = float(value)
                    elif p["type"] == "bool": value = bool(value)
                    elif p["type"] == "int": value = int(value)
                    break

        # 1. Update shader_parameters
        if shader not in State.shader_parameters:
            State.shader_parameters[shader] = {}
        State.shader_parameters[shader][name] = value
        
        # Do not apply here; frontend will call apply_shader manually.

    async def apply_shader(self):
        logger.info("Event G: apply_shader (Manual from UI)")
        
        cancel_crash_detection()
        save_config_immediate()
        
        if not State.master_switch:
            return
            
        trigger_crash_detection()
        await apply_shader_internal(State.active_shader)

    # ------------------------------------------------------------------
    # Utility getters/setters for UI (Event D: on_ui_opened implicit syncing)
    # ------------------------------------------------------------------
    async def get_shader_params(self):
        shader = State.active_shader
        if shader == "None":
            return []
        params = parse_shader_params(shader)
        State.params_meta[shader] = params
        saved = State.shader_parameters.get(shader, {})
        result = []
        for p in params:
            entry = dict(p)
            entry["value"] = saved.get(p["name"], p["default"])
            result.append(entry)
        return result

    async def reset_shader_params(self):
        shader = State.active_shader
        if shader == "None":
            return
        params = parse_shader_params(shader)
        State.params_meta[shader] = params
        State.shader_parameters[shader] = {p["name"]: p["default"] for p in params}
        save_config_immediate()
        
        # Trigger an apply if allowed
        if State.master_switch:
             await apply_shader_internal(State.active_shader)

    async def get_master_enabled(self):
        return State.master_switch

    async def get_current_shader(self):
        return State.active_shader

    async def get_per_game(self):
        return State.per_game_mode

    async def set_per_game(self, enabled: bool):
        logger.info(f"Setting per_game_mode: {enabled}")
        
        # Replicates Event C logic conceptually when mode flips
        State.per_game_mode = enabled
        if enabled:
            save_config_immediate()
        else:
            # Revert to global
            try:
                if os.path.exists(config_file):
                    with open(config_file, "r") as f:
                        data = json.load(f)
                    if State.current_appid not in data:
                        data[State.current_appid] = {}
                    data[State.current_appid]["per_game"] = False
                    with open(config_file, "w") as f:
                        json.dump(data, f, indent=4)
            except Exception:
                pass
            load_config_state(State.current_appid)
            
        # Re-apply
        if State.master_switch:
            await apply_shader_internal(State.active_shader)

    async def get_game_info(self):
        return {
            "appid": State.current_appid,
            "appname": State.appname,
            "per_game": State.per_game_mode,
            "active_category": State.active_category,
        }

    async def set_active_category(self, category: str):
        if category != State.active_category:
            State.active_category = category
            save_config_immediate()

    async def get_crash_detected(self):
        return State.crash_detected

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

        State.master_switch = True
        State.active_shader = "None"
        State.per_game_mode = False
        State.active_category = "Default"
        State.shader_parameters = {}
        State.params_meta = {}
        State.crash_detected = False
        
        if State.debounce_task:
            State.debounce_task.cancel()
            State.debounce_task = None
            
        await apply_shader_internal("None")
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
