# Implementation assumptions

- The service runs on Windows and uses NSSM with `scripts/up.ps1` as the entrypoint.
- Port is `20031`, taken from `../homelab-infra/registry.yaml` for service name `rtx`.
- The REST endpoint is `GET /api/health` (also `/api`) and returns formatted strings for Homepage. `GET /` serves an HTML landing page with a live chart.
- GPU metrics are read from the first line of `nvidia-smi --query-gpu=temperature.gpu,memory.free,utilization.gpu` (GPU index 0 if multiple GPUs are present).
- API response fields are formatted with units (`C`, `MiB`, `%`) and include a timestamp.
- Metrics logging is CSV at `logs/gpu-metrics.csv` with numeric values for graphing; interval defaults to 30 seconds.
- The process attempts to set a low (below-normal) Windows priority class; failure is ignored.
- Errors from `nvidia-smi` return HTTP 503 with a `status: error` payload.
