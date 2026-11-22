from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone


PHASES = {
    "queued": (0, "در صف اجرا"),
    "extracting": (10, "استخراج فریم‌ها"),
    "detecting": (35, "تشخیص اشیا با هوش مصنوعی"),
    "tracking": (65, "رهگیری اشیا با SORT"),
    "event_analysis": (78, "تحلیل رویدادهای امنیتی"),
    "rendering": (90, "ساخت ویدئوی تحلیل‌شده"),
    "completed": (100, "تحلیل کامل شد"),
    "failed": (100, "تحلیل با خطا متوقف شد"),
}


def exports_dir() -> Path:
    path = Path(settings.BASE_DIR) / "tracking_exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(asset_id: int) -> Path:
    return exports_dir() / f"video_analysis_asset_{int(asset_id)}.json"


def log_path(asset_id: int) -> Path:
    return exports_dir() / f"video_analysis_asset_{int(asset_id)}.log"


def _atomic_write_state(asset_id: int, payload: dict) -> dict:
    target = state_path(asset_id)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return payload


def write_state(asset_id: int, *, phase: str, status: str = "processing", **extra: Any) -> dict:
    progress, message = PHASES.get(phase, (0, phase))
    payload = {
        "asset_id": int(asset_id),
        "phase": phase,
        "status": status,
        "progress": progress,
        "message": message,
        "updated_at": timezone.now().isoformat(),
        **extra,
    }
    # Keep the worker PID across phase updates so a second browser request
    # cannot accidentally launch a duplicate pipeline for the same asset.
    if status in {"queued", "processing"} and "worker_pid" not in payload:
        try:
            previous = json.loads(state_path(asset_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if isinstance(previous, dict) and previous.get("status") in {"queued", "processing"}:
            for key in ("worker_pid", "worker_started_by"):
                if key in previous:
                    payload[key] = previous[key]
    return _atomic_write_state(asset_id, payload)


def read_state(asset_id: int) -> dict:
    path = state_path(asset_id)
    if not path.is_file():
        return write_state(asset_id, phase="queued", status="queued")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return {"asset_id": int(asset_id), "phase": "queued", "status": "queued", "progress": 0, "message": "در صف اجرا"}


def is_worker_running(pid: int) -> bool:
    """Best-effort process check that works on Windows and POSIX hosts."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            return f'"{pid}"' in completed.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def spawn_analysis_worker(asset_id: int) -> int:
    """Launch one detached pipeline process and avoid duplicate live workers."""
    base_dir = Path(settings.BASE_DIR)
    manage_py = base_dir / "manage.py"
    if not manage_py.is_file():
        raise RuntimeError(f"manage.py was not found under BASE_DIR: {base_dir}")

    state = read_state(asset_id)
    existing_pid = state.get("worker_pid")
    if state.get("status") in {"queued", "processing"} and existing_pid:
        try:
            pid = int(existing_pid)
        except (TypeError, ValueError):
            pid = 0
        if pid and is_worker_running(pid):
            return pid

    command = [sys.executable, str(manage_py), "run_video_analysis", "--asset-id", str(int(asset_id))]
    kwargs: dict[str, Any] = {
        "cwd": str(base_dir),
        "stdin": subprocess.DEVNULL,
        "env": os.environ.copy(),
        "close_fds": os.name != "nt",
    }
    log_file = open(log_path(asset_id), "ab", buffering=0)
    kwargs["stdout"] = log_file
    kwargs["stderr"] = subprocess.STDOUT
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)
    finally:
        log_file.close()

    # The child may already have advanced to extraction/detection. Preserve its
    # current phase instead of overwriting it with an older queued state.
    current = read_state(asset_id)
    if current.get("status") in {"queued", "processing"}:
        current["worker_pid"] = process.pid
        current["worker_started_by"] = os.getpid()
        _atomic_write_state(asset_id, current)
    return process.pid
