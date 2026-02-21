import os
import re
import asyncio
from pathlib import Path
from utils.constants import logger, shaders_folder, destination_folder
from utils.state import State

# ---------------------------------------------------------------------------
# Regex patterns for parsing .fx uniform parameters
# ---------------------------------------------------------------------------

_RE_ANNOTATED = re.compile(
    r"uniform\s+(float|bool|int)\s+(\w+)\s*<\s*([^>]*)\s*>\s*=\s*(.*?)\s*;",
    re.DOTALL,
)

_RE_PLAIN = re.compile(
    r"uniform\s+(float|bool|int)\s+(\w+)\s*=\s*([-+]?\d+\.?\d*)\s*;",
)

_RE_UI = {
    "ui_type":  re.compile(r'ui_type\s*=\s*"(\w+)"'),
    "ui_min":   re.compile(r'ui_min\s*=\s*([-+]?\d+\.?\d*)'),
    "ui_max":   re.compile(r'ui_max\s*=\s*([-+]?\d+\.?\d*)'),
    "ui_step":  re.compile(r'ui_step\s*=\s*([-+]?\d+\.?\d*)'),
    "ui_label": re.compile(r'ui_label\s*=\s*"([^"]*)"'),
}

_RE_UI_ITEMS = re.compile(r'ui_items\s*=\s*"((?:[^"\\]|\\0)*)"')

_RE_SOURCE = re.compile(r'source\s*=\s*"')

def apply_shader_transformations(text: str) -> str:
    """Transforms upstream .fx files to be compatible by injecting UI annotations."""
    # Remove the ReShadeUI include as it's not needed/causes errors if missing
    text = re.sub(r'#include "ReShadeUI\.fxh"', "", text)
    
    # Transform different uniform types
    # 1. Sliders (FLOAT/INT) -> ui_type = "drag"
    text = re.sub(r'<\s*__UNIFORM_SLIDER_(?:FLOAT|INT)[1-3]', r'<\n    ui_type = "drag";', text)
    
    # 2. Colors -> ui_type = "color"
    text = re.sub(r'<\s*__UNIFORM_COLOR_FLOAT[1-3]', r'< ui_type = "color";', text)
    
    # 3. Combos -> ui_type = "combo"
    text = re.sub(r'<\s*__UNIFORM_COMBO_INT1', r'<\n    ui_type = "combo";', text)
    
    # 4. Inputs/Drags (BOOL/Drag Float) -> ui_type = "drag"
    text = re.sub(r'<\s*__UNIFORM_INPUT_BOOL1', r'<\n    ui_type = "drag";', text)
    text = re.sub(r'<\s*__UNIFORM_DRAG_FLOAT[1-2]', r'<\n    ui_type = "drag";', text)
    
    return text

def parse_shader_params(shader_name: str) -> list[dict]:
    """Parse all user-tuneable uniform parameters from a .fx file."""
    source_file = Path(shaders_folder) / shader_name
    dest_file = Path(destination_folder) / shader_name
    fx_file = source_file if source_file.exists() else dest_file
    if not fx_file.exists():
        logger.warning(f"Shader file not found: {shader_name}")
        return []

    text = fx_file.read_text(encoding="utf-8", errors="replace")
    
    text = apply_shader_transformations(text)
        
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


def apply_params_to_content(text: str, params: dict) -> str:
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


def generate_staging_shader(shader_name: str) -> str:
    """Read source shader, patch in memory, write to fixed staging file .reshadeck.fx"""
    source_file = Path(shaders_folder) / shader_name
    if not source_file.exists():
        source_file = Path(destination_folder) / shader_name
        
    if not source_file.exists():
        logger.error(f"Generate staging: Source {shader_name} not found")
        return shader_name

    text = source_file.read_text(encoding="utf-8", errors="replace")
    text = apply_shader_transformations(text)
    
    params = State.shader_parameters.get(shader_name, {})
    patched_text = apply_params_to_content(text, params)
    
    staging_filename = ".reshadeck.fx"
    full_dest_path = Path(destination_folder) / staging_filename
    full_dest_path.write_text(patched_text, encoding="utf-8")
    
    return staging_filename


async def apply_shader_internal(target_shader: str):
    """
    Pure dumb function that takes target_shader and shells out to set_shader.sh.
    Does NOT contain logical checks for whether it should run.
    """
    staging_file = target_shader
    if target_shader != "None":
        staging_file = generate_staging_shader(target_shader)
        
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
