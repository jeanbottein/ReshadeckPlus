#!/bin/bash

# Clean up any legacy randomized files we might have left behind
cleanup_legacy() {
    local SHADER_DIR="$1"
    find "$SHADER_DIR" -maxdepth 1 -type f -name ".reshadeck.active.*.fx" -delete
}

FXNAME="$1"
SHADER_DIR="$2"

if [ "$FXNAME" = "None" ] || [ -z "$FXNAME" ]; then
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT
    cleanup_legacy "$SHADER_DIR"
    exit 0
fi

if [ ! -f "$SHADER_DIR/$FXNAME" ]; then
    echo "Shader file $FXNAME not found in $SHADER_DIR"
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT
    cleanup_legacy "$SHADER_DIR"
    exit 1
fi

cleanup_legacy "$SHADER_DIR"

# Apply the directly to Gamescope. Gamescope observes the file using inotify,
# so when the python backend writes to the staging file, it auto reloads.
# No need to generate randomized active files or have a 'force' argument!
if ! DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$FXNAME"; then
    echo "Failed to set xprop"
    exit 1
fi

exit 0
