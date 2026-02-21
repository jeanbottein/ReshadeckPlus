import decky_plugin

logger = decky_plugin.logger

destination_folder = decky_plugin.DECKY_USER_HOME + "/.local/share/gamescope/reshade/Shaders"
textures_destination = decky_plugin.DECKY_USER_HOME + "/.local/share/gamescope/reshade/Textures"
shaders_folder = decky_plugin.DECKY_PLUGIN_DIR + "/shaders"
textures_folder = decky_plugin.DECKY_PLUGIN_DIR + "/textures"
config_file = decky_plugin.DECKY_PLUGIN_SETTINGS_DIR + "/config.json"
crash_file = decky_plugin.DECKY_PLUGIN_SETTINGS_DIR + "/crash.json"
