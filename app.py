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
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 14px;
      margin: 0 0 10px;
      font-size: 0.8rem;
      color: var(--muted);
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: opacity 120ms ease;
    }
    .legend-item.off { opacity: 0.45; }
    .swatch {
      width: 14px;
      height: 0;
      border-top: 3px solid;
      border-radius: 999px;
    }
    .swatch.temp { border-color: var(--line); }
    .swatch.util { border-color: var(--line2); }
    .swatch.mem { border-color: var(--line3); }
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
      overflow: visible;
    }
    canvas { width: 100%; height: min(460px, 60vh); display: block; }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 8px;
      margin: 0 0 10px;
    }
    .stat {
      border: 1px solid #223046;
      border-radius: 8px;
      background: #0b1220;
      padding: 8px 10px;
    }
    .stat .label {
      color: var(--muted);
      font-size: 0.75rem;
      margin-bottom: 4px;
    }
    .stat .value {
      font-size: 0.95rem;
      font-weight: 600;
    }
    .stat .meta {
      color: var(--muted);
      font-size: 0.72rem;
      margin-top: 4px;
    }
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
      display: none;
      white-space: nowrap;
      z-index: 10;
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
        <button type="button" data-minutes="5">5m</button>
        <button type="button" data-minutes="10">10m</button>
        <button type="button" data-minutes="15">15m</button>
        <button type="button" data-minutes="30">30m</button>
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

    <div class="legend" aria-label="Chart legend">
      <span class="legend-item" id="legendTemp"><span class="swatch temp"></span>Temp (C)</span>
      <span class="legend-item" id="legendUtil"><span class="swatch util"></span>Util (%)</span>
      <span class="legend-item" id="legendMem"><span class="swatch mem"></span>Mem Free (MiB / 100)</span>
    </div>

    <div class="stats">
      <div class="stat">
        <div class="label">Status</div>
        <div class="value" id="statStatus">Loading...</div>
        <div class="meta" id="statTime">--</div>
      </div>
      <div class="stat">
        <div class="label">Temperature</div>
        <div class="value" id="statTemp">--</div>
      </div>
      <div class="stat">
        <div class="label">GPU Utilization</div>
        <div class="value" id="statUtil">--</div>
      </div>
      <div class="stat">
        <div class="label">Free Memory</div>
        <div class="value" id="statMem">--</div>
      </div>
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
    const statStatus = document.getElementById("statStatus");
    const statTime = document.getElementById("statTime");
    const statTemp = document.getElementById("statTemp");
    const statUtil = document.getElementById("statUtil");
    const statMem = document.getElementById("statMem");
    const legendTemp = document.getElementById("legendTemp");
    const legendUtil = document.getElementById("legendUtil");
    const legendMem = document.getElementById("legendMem");
    const SERIES_COLORS = { temp: "#22c55e", util: "#38bdf8", mem: "#fb7185" };

    const state = {
      minutes: 60,
      rows: [],
      series: { temp: true, util: true, mem: true },
      hoverIndex: null,
      hoverPoint: null,
    };

    function syncLegend() {
      legendTemp.classList.toggle("off", !state.series.temp);
      legendUtil.classList.toggle("off", !state.series.util);
      legendMem.classList.toggle("off", !state.series.mem);
    }

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

    function drawCanvasLegend(x0, y0, w, hoverRow) {
      const items = [
        { key: "temp", label: "Temp", color: SERIES_COLORS.temp, value: hoverRow ? `${hoverRow.temperature_c ?? "-"} C` : "" },
        { key: "util", label: "Util", color: SERIES_COLORS.util, value: hoverRow ? `${hoverRow.utilization_percent ?? "-"} %` : "" },
        { key: "mem", label: "Mem", color: SERIES_COLORS.mem, value: hoverRow ? `${hoverRow.memory_free_mib ?? "-"} MiB` : "" },
      ].filter((item) => state.series[item.key]);

      if (!items.length) return;

      const lineHeight = 18;
      const pad = 8;
      const boxW = hoverRow ? 210 : 118;
      const boxH = pad * 2 + items.length * lineHeight;
      const boxX = x0 + w - boxW - 8;
      const boxY = y0 + 8;

      ctx.fillStyle = "rgba(2, 6, 23, 0.88)";
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 1;
      ctx.fillRect(boxX, boxY, boxW, boxH);
      ctx.strokeRect(boxX, boxY, boxW, boxH);

      ctx.font = "12px Segoe UI, sans-serif";
      ctx.textBaseline = "middle";
      items.forEach((item, idx) => {
        const y = boxY + pad + idx * lineHeight + lineHeight / 2;
        ctx.strokeStyle = item.color;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(boxX + 8, y);
        ctx.lineTo(boxX + 22, y);
        ctx.stroke();

        ctx.fillStyle = "#cbd5e1";
        ctx.fillText(item.label, boxX + 28, y);
        if (hoverRow) {
          ctx.fillStyle = "#e2e8f0";
          ctx.fillText(item.value, boxX + 84, y);
        }
      });
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

      if (state.series.temp) drawSeries(temp, SERIES_COLORS.temp, 100, x0, y0, w, h);
      if (state.series.util) drawSeries(util, SERIES_COLORS.util, 100, x0, y0, w, h);
      if (state.series.mem) drawSeries(mem, SERIES_COLORS.mem, 100, x0, y0, w, h);

      let hoverRow = null;
      let hoverX = null;
      if (state.hoverIndex != null && rows.length) {
        const i = Math.max(0, Math.min(rows.length - 1, state.hoverIndex));
        hoverRow = rows[i];
        hoverX = x0 + (i * w) / Math.max(1, rows.length - 1);
      }
      drawCanvasLegend(x0, y0, w, hoverRow);

      if (!hoverRow) {
        tooltip.style.display = "none";
        return;
      }
      ctx.strokeStyle = "#475569";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(hoverX, y0);
      ctx.lineTo(hoverX, y0 + h);
      ctx.stroke();

      tooltip.innerHTML = [
        `<strong>${new Date(hoverRow.timestamp).toLocaleString()}</strong>`,
        `Temp: ${hoverRow.temperature_c ?? "-"} C`,
        `Util: ${hoverRow.utilization_percent ?? "-"} %`,
        `Mem: ${hoverRow.memory_free_mib ?? "-"} MiB`,
      ].join("<br>");
      tooltip.style.display = "block";
      if (state.hoverPoint) placeTooltip(state.hoverPoint.x, state.hoverPoint.y);
    }

    function placeTooltip(pointerX, pointerY) {
      const pad = 6;
      const gap = 12;
      const wrapRect = chartWrap.getBoundingClientRect();
      const tipRect = tooltip.getBoundingClientRect();

      let left = pointerX + gap;
      let top = pointerY - tipRect.height / 2;

      if (wrapRect.left + left + tipRect.width > window.innerWidth - pad) {
        left = pointerX - tipRect.width - gap;
      }

      left = Math.max(-wrapRect.left + pad, Math.min(left, window.innerWidth - wrapRect.left - tipRect.width - pad));
      top = Math.max(-wrapRect.top + pad, Math.min(top, window.innerHeight - wrapRect.top - tipRect.height - pad));

      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    }

    function renderCurrentStats(payload, errMessage) {
      if (errMessage) {
        statStatus.textContent = "Error";
        statTemp.textContent = "--";
        statUtil.textContent = "--";
        statMem.textContent = "--";
        statTime.textContent = errMessage;
        return;
      }

      statStatus.textContent = payload.status || "ok";
      statTemp.textContent = payload.temperature || "--";
      statUtil.textContent = payload.gpu_utilization || "--";
      statMem.textContent = payload.memory_available || "--";
      statTime.textContent = payload.timestamp ? new Date(payload.timestamp).toLocaleString() : "--";
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

    async function loadCurrent() {
      try {
        const resp = await fetch("/api");
        const body = await resp.json();
        if (!resp.ok || body.status !== "ok") throw new Error(body.error || `HTTP ${resp.status}`);
        renderCurrentStats(body, null);
      } catch (err) {
        renderCurrentStats(null, `Current stats unavailable: ${err.message}`);
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
      syncLegend();
      redraw();
    });
    document.getElementById("toggleUtil").addEventListener("change", (e) => {
      state.series.util = e.target.checked;
      syncLegend();
      redraw();
    });
    document.getElementById("toggleMem").addEventListener("change", (e) => {
      state.series.mem = e.target.checked;
      syncLegend();
      redraw();
    });

    canvas.addEventListener("mousemove", (e) => {
      state.hoverIndex = pointerToIndex(e.clientX);
      state.hoverPoint = { x: e.offsetX, y: e.offsetY };
      redraw();
    });

    canvas.addEventListener("mouseleave", () => {
      state.hoverIndex = null;
      state.hoverPoint = null;
      tooltip.style.display = "none";
      redraw();
    });

    load();
    loadCurrent();
    syncLegend();
    setInterval(() => {
      load();
      loadCurrent();
    }, 15000);
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


def main() -> int:
    _set_low_priority_best_effort()
    stop_event = threading.Event()
    thread = threading.Thread(target=_metrics_loop, args=(stop_event,), daemon=True)
    thread.start()

    serve(app, host=_bind_host(), port=_bind_port())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
