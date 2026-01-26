import csv
import ctypes
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from waitress import serve

load_dotenv()

APP_NAME = "homelab-rtx"
DEFAULT_PORT = 20031
DEFAULT_HOST = "0.0.0.0"
DEFAULT_LOG_INTERVAL_SECONDS = 30
DEFAULT_LOG_PATH = "logs/gpu-metrics.csv"
DEFAULT_QUERY_TIMEOUT_SECONDS = 5

QUERY_FIELDS = ["temperature.gpu", "memory.free", "utilization.gpu"]
QUERY_CMD = [
    "nvidia-smi",
    f"--query-gpu={','.join(QUERY_FIELDS)}",
    "--format=csv,noheader,nounits",
]

app = Flask(APP_NAME)


def _iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat()


def _set_low_priority_best_effort() -> None:
    if os.name != "nt":
        return
    below_normal_priority = 0x00004000
    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, below_normal_priority)
    except Exception:
        pass


def _read_gpu_metrics() -> dict:
    try:
        result = subprocess.run(
            QUERY_CMD,
            capture_output=True,
            text=True,
            timeout=_query_timeout_seconds(),
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("nvidia-smi not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("nvidia-smi timed out") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(stderr or "nvidia-smi failed") from exc

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("nvidia-smi returned no data")

    values = [value.strip() for value in lines[0].split(",")]
    if len(values) != 3:
        raise RuntimeError("unexpected nvidia-smi output")

    temperature_c, memory_free_mib, utilization_percent = values
    return {
        "temperature_c": int(float(temperature_c)),
        "memory_free_mib": int(float(memory_free_mib)),
        "utilization_percent": int(float(utilization_percent)),
    }


def _format_payload(metrics: dict) -> dict:
    return {
        "status": "ok",
        "temperature": f"{metrics['temperature_c']} C",
        "memory_available": f"{metrics['memory_free_mib']} MiB",
        "gpu_utilization": f"{metrics['utilization_percent']} %",
        "timestamp": _iso_timestamp(),
    }


def _log_path() -> Path:
    return Path(os.getenv("RTX_LOG_PATH", DEFAULT_LOG_PATH))


def _log_interval_seconds() -> int:
    try:
        return int(os.getenv("RTX_LOG_INTERVAL_SECONDS", DEFAULT_LOG_INTERVAL_SECONDS))
    except ValueError:
        return DEFAULT_LOG_INTERVAL_SECONDS


def _query_timeout_seconds() -> int:
    try:
        return int(os.getenv("RTX_QUERY_TIMEOUT_SECONDS", DEFAULT_QUERY_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_QUERY_TIMEOUT_SECONDS


def _ensure_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp",
                "temperature_c",
                "memory_free_mib",
                "utilization_percent",
                "status",
                "error",
            ]
        )


def _append_log_row(metrics: dict | None, error: str | None) -> None:
    path = _log_path()
    _ensure_log_file(path)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if metrics:
            writer.writerow(
                [
                    _iso_timestamp(),
                    metrics["temperature_c"],
                    metrics["memory_free_mib"],
                    metrics["utilization_percent"],
                    "ok",
                    "",
                ]
            )
        else:
            writer.writerow([_iso_timestamp(), "", "", "", "error", error or "unknown"])


def _metrics_loop(stop_event: threading.Event) -> None:
    interval = _log_interval_seconds()
    while not stop_event.is_set():
        try:
            metrics = _read_gpu_metrics()
            _append_log_row(metrics, None)
        except Exception as exc:
            _append_log_row(None, str(exc))
        stop_event.wait(interval)


@app.route("/")
@app.route("/health")
def health() -> tuple:
    try:
        metrics = _read_gpu_metrics()
        return jsonify(_format_payload(metrics)), 200
    except Exception as exc:
        return (
            jsonify({"status": "error", "error": str(exc), "timestamp": _iso_timestamp()}),
            503,
        )


def _bind_host() -> str:
    return os.getenv("RTX_BIND_HOST", DEFAULT_HOST)


def _bind_port() -> int:
    try:
        return int(os.getenv("RTX_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


if __name__ == "__main__":
    _set_low_priority_best_effort()
    stop_event = threading.Event()
    thread = threading.Thread(target=_metrics_loop, args=(stop_event,), daemon=True)
    thread.start()

    serve(app, host=_bind_host(), port=_bind_port())
