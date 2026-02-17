#!/bin/bash

FXNAME="$1"
SHADER_DIR="$2"
FORCE="${3:-true}"

if [ "$FXNAME" = "None" ] || [ -z "$FXNAME" ]; then
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT

else
    # Generic temp-file trick for ALL shaders to force gamescope reload
    BASENAME="${FXNAME%.fx}"
    RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 6)
    TEMPFX="${BASENAME}_${RAND}.fx"

    if [ "$FORCE" = "false" ]; then
        CURRENTFX=$(DISPLAY=:0 xprop -root GAMESCOPE_RESHADE_EFFECT 2>/dev/null \
            | awk -F'"' '/GAMESCOPE_RESHADE_EFFECT/ {print $2}')
        # Extract base name (strip _XXXXXX suffix) from current effect
        CURRENT_BASE=$(echo "$CURRENTFX" | sed -E 's/_[A-Za-z0-9]{6}\.fx$/.fx/')
        [ "$CURRENT_BASE" = "$FXNAME" ] && exit 0
    fi

    cp "$SHADER_DIR/$FXNAME" "$SHADER_DIR/$TEMPFX"
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$TEMPFX"

    # Clean up old temp files for this shader (keep only the one we just created)
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/${BASENAME}_[A-Za-z0-9]{6}\.fx" ! -name "$TEMPFX" -exec rm {} \;
fi
