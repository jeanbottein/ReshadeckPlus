class State:
    master_switch = True
    active_shader = "None"
    shader_parameters = {}  # {shader_name: {param_name: value, ...}}
    crash_detected = False
    per_game_mode = False
    current_appid = "Unknown"
    
    # State related to packages and caching
    appname = "Unknown"
    active_category = "Default"
    params_meta = {}  # cache: {shader_name: [param_dict, ...]}
    
    # Task Management
    active_crash_monitor_task = None
    debounce_task = None
