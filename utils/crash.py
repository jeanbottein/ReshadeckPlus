import os
import time
import json
import asyncio
from pathlib import Path
from utils.constants import logger, crash_file
from utils.state import State
from utils.shader import apply_shader_internal
from utils.config import save_config_immediate

def read_crash_data():
    try:
        if os.path.exists(crash_file):
            with open(crash_file, "r") as f:
                data = json.load(f)
                return {"count": data.get("count", 0), "last_timestamp": data.get("last_timestamp", "0")}
    except Exception:
        pass
    return {"count": 0, "last_timestamp": "0"}

def write_crash_data(count: int, last_timestamp: str):
    try:
        with open(crash_file, "w") as f:
            json.dump({"count": count, "last_timestamp": last_timestamp}, f)
    except Exception:
        pass

async def crash_detection_subroutine():
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
                
                State.master_switch = False
                State.crash_detected = True
                save_config_immediate()
                await apply_shader_internal("None")
                
                # Record the crash timestamp so we don't trip on it at startup
                write_crash_data(1, str(latest_timestamp))
                
                return # Exit subroutine
                
        logger.info("Crash Detection Subroutine cleanly expired (no crash).")
    except asyncio.CancelledError:
        logger.info("Crash Detection Subroutine cancelled.")
    except Exception as e:
        logger.error(f"Error in Crash Detection Subroutine: {e}")

def trigger_crash_detection():
    if State.active_crash_monitor_task:
        State.active_crash_monitor_task.cancel()
    State.active_crash_monitor_task = asyncio.create_task(crash_detection_subroutine())

def cancel_crash_detection():
    if State.active_crash_monitor_task:
        State.active_crash_monitor_task.cancel()
        State.active_crash_monitor_task = None
