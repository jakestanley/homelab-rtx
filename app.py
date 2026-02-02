import csv
import ctypes
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string
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


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _read_log_rows() -> list[dict]:
    path = _log_path()
    _ensure_log_file(path)
    rows: list[dict] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "timestamp": row.get("timestamp", ""),
                    "temperature_c": _safe_int(row.get("temperature_c")),
                    "memory_free_mib": _safe_int(row.get("memory_free_mib")),
                    "utilization_percent": _safe_int(row.get("utilization_percent")),
                    "status": row.get("status", ""),
                    "error": row.get("error", ""),
                }
            )
    return rows


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
def landing() -> str:
    return render_template_string(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>homelab-rtx</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f172a;
      --card: #111827;
      --line: #22c55e;
      --line2: #38bdf8;
      --line3: #fb7185;
      --muted: #94a3b8;
      --text: #e2e8f0;
      --grid: #1f2937;
      --accent: #60a5fa;
    }
    body {
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #1e293b, var(--bg) 55%);
      color: var(--text);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 20px;
      box-sizing: border-box;
    }
    .card {
      width: min(1120px, 100%);
      background: color-mix(in srgb, var(--card) 95%, black);
      border: 1px solid #253042;
      border-radius: 14px;
      padding: 18px;
    }
    h1 { margin: 0 0 6px; font-size: 1.1rem; }
    .sub { color: var(--muted); margin-bottom: 12px; font-size: 0.92rem; }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      align-items: center;
      margin: 0 0 10px;
      font-size: 0.88rem;
      color: var(--muted);
    }
    .btn-group { display: flex; gap: 6px; }
    button {
      border: 1px solid #334155;
      background: #0f172a;
      color: var(--text);
      padding: 4px 10px;
      border-radius: 999px;
      cursor: pointer;
      font-size: 0.82rem;
    }
    button.active {
      background: color-mix(in srgb, var(--accent) 20%, #0f172a);
      border-color: var(--accent);
    }
    label { display: inline-flex; align-items: center; gap: 5px; }
    .chart-wrap {
      position: relative;
      border-radius: 10px;
      border: 1px solid #1f2a3b;
      background: #0b1220;
      overflow: hidden;
    }
    canvas { width: 100%; height: min(460px, 60vh); display: block; }
    .tooltip {
      position: absolute;
      pointer-events: none;
      background: rgba(2, 6, 23, 0.92);
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      font-size: 0.78rem;
      color: var(--text);
      min-width: 190px;
      transform: translate(10px, -50%);
      display: none;
      white-space: nowrap;
    }
    .err { color: #fecaca; margin-top: 8px; font-size: 0.9rem; }
  </style>
</head>
<body>
  <main class="card">
    <h1>GPU Metrics History</h1>
    <div class="sub">Live API: <code>/api</code> | Raw history: <code>/api/history</code></div>

    <div class="controls">
      <span>Range</span>
      <div class="btn-group" id="rangeButtons">
        <button type="button" data-minutes="60" class="active">1h</button>
        <button type="button" data-minutes="360">6h</button>
        <button type="button" data-minutes="1440">24h</button>
        <button type="button" data-minutes="0">All</button>
      </div>
      <span>Series</span>
      <label><input type="checkbox" id="toggleTemp" checked> Temp (C)</label>
      <label><input type="checkbox" id="toggleUtil" checked> Util (%)</label>
      <label><input type="checkbox" id="toggleMem" checked> Mem Free (MiB / 100)</label>
    </div>

    <div class="chart-wrap" id="chartWrap">
      <canvas id="chart" width="1080" height="460"></canvas>
      <div id="tooltip" class="tooltip"></div>
    </div>
    <div id="err" class="err"></div>
  </main>

  <script>
    const canvas = document.getElementById("chart");
    const ctx = canvas.getContext("2d");
    const errEl = document.getElementById("err");
    const tooltip = document.getElementById("tooltip");
    const chartWrap = document.getElementById("chartWrap");
    const rangeButtons = [...document.querySelectorAll("#rangeButtons button")];

    const state = {
      minutes: 60,
      rows: [],
      series: { temp: true, util: true, mem: true },
      hoverIndex: null,
    };

    function drawGrid(x0, y0, w, h) {
      ctx.strokeStyle = "#1f2937";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 5; i++) {
        const y = y0 + (h / 5) * i;
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x0 + w, y);
        ctx.stroke();
      }
    }

    function drawSeries(values, color, scale, x0, y0, w, h) {
      if (!values.length) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      values.forEach((v, i) => {
        const x = x0 + (i * w) / Math.max(1, values.length - 1);
        const y = y0 + h - Math.max(0, Math.min(1, v / scale)) * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    function getFilteredRows() {
      const okRows = state.rows.filter((r) => r.status === "ok");
      if (!state.minutes) return okRows;
      const cutoff = Date.now() - state.minutes * 60 * 1000;
      return okRows.filter((r) => {
        const ts = Date.parse(r.timestamp || "");
        return Number.isFinite(ts) && ts >= cutoff;
      });
    }

    function redraw() {
      const rows = getFilteredRows();
      const temp = rows.map((r) => r.temperature_c ?? 0);
      const util = rows.map((r) => r.utilization_percent ?? 0);
      const mem = rows.map((r) => (r.memory_free_mib ?? 0) / 100);

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const x0 = 56, y0 = 26, w = canvas.width - 76, h = canvas.height - 62;
      drawGrid(x0, y0, w, h);

      if (state.series.temp) drawSeries(temp, "#22c55e", 100, x0, y0, w, h);
      if (state.series.util) drawSeries(util, "#38bdf8", 100, x0, y0, w, h);
      if (state.series.mem) drawSeries(mem, "#fb7185", 100, x0, y0, w, h);

      if (state.hoverIndex == null || !rows.length) {
        tooltip.style.display = "none";
        return;
      }

      const i = Math.max(0, Math.min(rows.length - 1, state.hoverIndex));
      const x = x0 + (i * w) / Math.max(1, rows.length - 1);
      ctx.strokeStyle = "#475569";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y0 + h);
      ctx.stroke();

      const row = rows[i];
      tooltip.innerHTML = [
        `<strong>${new Date(row.timestamp).toLocaleString()}</strong>`,
        `Temp: ${row.temperature_c ?? "-"} C`,
        `Util: ${row.utilization_percent ?? "-"} %`,
        `Mem: ${row.memory_free_mib ?? "-"} MiB`,
      ].join("<br>");
      tooltip.style.display = "block";
    }

    function pointerToIndex(clientX) {
      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const x0 = 56;
      const w = canvas.width - 76;
      const nx = (x / rect.width) * canvas.width;
      const rows = getFilteredRows();
      if (!rows.length) return null;
      const clamped = Math.max(x0, Math.min(x0 + w, nx));
      return Math.round(((clamped - x0) / w) * (rows.length - 1));
    }

    async function load() {
      try {
        const resp = await fetch("/api/history");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        state.rows = body.data || [];
        redraw();
        errEl.textContent = "";
      } catch (err) {
        errEl.textContent = `Failed to load chart data: ${err.message}`;
      }
    }

    rangeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        state.minutes = Number(btn.dataset.minutes);
        rangeButtons.forEach((b) => b.classList.toggle("active", b === btn));
        state.hoverIndex = null;
        redraw();
      });
    });

    document.getElementById("toggleTemp").addEventListener("change", (e) => {
      state.series.temp = e.target.checked;
      redraw();
    });
    document.getElementById("toggleUtil").addEventListener("change", (e) => {
      state.series.util = e.target.checked;
      redraw();
    });
    document.getElementById("toggleMem").addEventListener("change", (e) => {
      state.series.mem = e.target.checked;
      redraw();
    });

    canvas.addEventListener("mousemove", (e) => {
      state.hoverIndex = pointerToIndex(e.clientX);
      tooltip.style.left = `${e.offsetX}px`;
      tooltip.style.top = `${e.offsetY}px`;
      redraw();
    });

    canvas.addEventListener("mouseleave", () => {
      state.hoverIndex = null;
      tooltip.style.display = "none";
      redraw();
    });

    load();
    setInterval(load, 15000);
  </script>
</body>
</html>"""
    )


@app.route("/api")
@app.route("/api/health")
def health() -> tuple:
    try:
        metrics = _read_gpu_metrics()
        return jsonify(_format_payload(metrics)), 200
    except Exception as exc:
        return (
            jsonify({"status": "error", "error": str(exc), "timestamp": _iso_timestamp()}),
            503,
        )


@app.route("/api/history")
def history() -> tuple:
    data = _read_log_rows()
    return jsonify({"status": "ok", "count": len(data), "data": data}), 200


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
