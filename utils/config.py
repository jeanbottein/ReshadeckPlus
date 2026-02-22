import os
import json
from pathlib import Path
from utils.constants import config_file, logger
from utils.state import State

def config_key():
    return State.current_appid if State.per_game_mode else "_global"

def save_config_immediate():
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

        key = config_key()
        
        shaders = []
        if State.active_shader != "None":
            shaders.append({
                "shader": State.active_shader,
                "category": State.active_category,
                "parameters": State.shader_parameters.get(State.active_shader, {})
            })

        entry = {
            "appname": State.appname if State.per_game_mode else "Global",
            "active_category": State.active_category,
            "shaders": shaders,
        }
        if State.per_game_mode:
            entry["per_game"] = True
        data[key] = entry
        
        data["master_enabled"] = State.master_switch

        if State.per_game_mode and key == State.current_appid:
            if State.current_appid not in data or not isinstance(data[State.current_appid], dict):
                 data[State.current_appid] = {}
            data[State.current_appid]["per_game"] = True

        if not State.per_game_mode:
            if State.current_appid not in data:
                data[State.current_appid] = {}
            data[State.current_appid]["per_game"] = False
            data[State.current_appid]["appname"] = State.appname

        with open(config_file, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write config: {e}")

def load_config_state(appid: str):
    """Load state from file into memory based on appid."""
    try:
        if not os.path.exists(config_file):
            return
        with open(config_file, "r") as f:
            data = json.load(f)

        app_config = data.get(appid, {})
        is_per_game = app_config.get("per_game", False)
        State.per_game_mode = is_per_game

        config = app_config if is_per_game else data.get("_global", {})

        State.master_switch = data.get("master_enabled", True)
        
        State.active_category = config.get("active_category", "Default")
        
        shaders = config.get("shaders", [])
        if shaders and isinstance(shaders, list) and len(shaders) > 0:
            first_pass = shaders[0]
            State.active_shader = first_pass.get("shader", "None")
            if "category" in first_pass:
                State.active_category = first_pass.get("category", State.active_category)
            # Convert to dictionary keyed by shader name as expected by the rest of the application
            State.shader_parameters = {State.active_shader: first_pass.get("parameters", {})} if State.active_shader != "None" else {}
        else:
            State.active_shader = "None"
            State.shader_parameters = {}
            
    except Exception as e:
        logger.error(f"Failed to read config: {e}")
