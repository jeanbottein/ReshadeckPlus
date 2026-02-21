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
        
        saved_params = {}
        if State.active_shader in State.shader_parameters:
            saved_params[State.active_shader] = State.shader_parameters[State.active_shader]

        entry = {
            "appname": State.appname if State.per_game_mode else "Global",
            "current": State.active_shader,
            "active_category": State.active_category,
            "params": saved_params,
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
        State.active_shader = config.get("current", "None")
        State.active_category = config.get("active_category", "Default")
        State.shader_parameters = config.get("params", {})
        
    except Exception as e:
        logger.error(f"Failed to read config: {e}")
