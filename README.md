# homelab-rtx

Host-run NVIDIA GPU telemetry service that exposes current status over HTTP for Homepage customapi widgets.

## Runtime

- Linux: `systemd` via `systemd/rtx.service` and `scripts/up.sh`
- Windows: NSSM via `scripts/install-service.ps1` and `scripts/up.ps1`
- HTTP only; TLS, ingress, DNS, and port ownership are managed in `homelab-infra`
- Service identifier: `rtx`

## Endpoints

- `GET /health` (also `/`)
  - Returns:
    - `status` (ok/error)
    - `temperature` (formatted, e.g. `65 C`)
    - `memory_available` (formatted, e.g. `8123 MiB`)
    - `gpu_utilization` (formatted, e.g. `34 %`)

## Configuration

Configuration is via environment variables.

- Local/manual runs: `.env` (see `.env.example`)
- Linux `systemd`: `/etc/rtx/rtx.env` (see `systemd/rtx.env.example`)

Supported variables:

- `RTX_PYTHON_EXE`: absolute Python interpreter path for Linux `scripts/up.sh`
- `RTX_BIND_HOST`: bind host for the HTTP listener
- `RTX_PORT`: bind port for the HTTP listener
- `RTX_LOG_PATH`: metrics CSV path; relative paths resolve from the working directory
- `RTX_LOG_INTERVAL_SECONDS`: background GPU sampling interval
- `RTX_QUERY_TIMEOUT_SECONDS`: `nvidia-smi` timeout per query

## Linux systemd

This repo ships first-class Linux `systemd` assets under `systemd/`. The examples below assume the repo is deployed at `/srv/rtx` to match the committed unit file. If you deploy elsewhere, update `WorkingDirectory=` and `ExecStart=` in the unit accordingly.

### Required runtime dependencies

- `systemd`
  - Verify: `systemctl --version && systemd-analyze --version`
- `nvidia-smi`
  - Verify: `command -v nvidia-smi`
- Python interpreter used by `ExecStart`
  - Verify: `test -x /srv/rtx/.venv/bin/python`

### Canonical entrypoint

```sh
./scripts/up.sh
```

`scripts/up.sh` is non-interactive and expects a ready Python environment. By default it uses `.venv/bin/python`; override with `RTX_PYTHON_EXE=/absolute/path/to/python` when needed.

### Install the unit

1. Deploy the repo to `/srv/rtx`.
2. Create the dedicated runtime account:
   ```sh
   sudo useradd --system --home /srv/rtx --shell /usr/sbin/nologin rtx
   ```
3. Create the Python environment and install app dependencies:
   ```sh
   python3 -m venv /srv/rtx/.venv
   /srv/rtx/.venv/bin/pip install -r /srv/rtx/requirements.txt
   ```
4. Ensure the service account can read the repo and write `logs/`:
   ```sh
   sudo chown -R rtx:rtx /srv/rtx
   ```
5. Install the optional environment file template and adjust values if needed:
   ```sh
   sudo install -d /etc/rtx
   sudo cp systemd/rtx.env.example /etc/rtx/rtx.env
   ```
6. Install the unit:
   ```sh
   sudo cp systemd/rtx.service /etc/systemd/system/rtx.service
   sudo systemctl daemon-reload
   ```

### Enable and start

```sh
sudo systemctl enable --now rtx.service
```

### Logs

```sh
journalctl -u rtx.service -f
```

The service also writes GPU history to `logs/gpu-metrics.csv` by default.

### Configure it

- Working directory: `/srv/rtx`
- Unit file location: `/etc/systemd/system/rtx.service`
- Host env file: `/etc/rtx/rtx.env`
- App env template: `.env.example`
- The service port should be supplied through env/config that aligns with `homelab-infra`; do not change ingress or exposure here.

## Run manually

Linux:

```sh
./scripts/up.sh
```

Windows:

```powershell
.\scripts\up.ps1
```

## Install / update service (elevated PowerShell)

```powershell
.\scripts\install-service.ps1 -Start
```

## Uninstall service

```powershell
.\scripts\install-service.ps1 -Stop -Uninstall
```

## Logging

- GPU metrics are logged every 30 seconds (default) to `logs/gpu-metrics.csv`.
- Linux `systemd` logs go to journald.
- Windows NSSM stdout/stderr are logged to `logs/`.

## Notes

- `nvidia-smi` must be available on PATH for metrics collection.
- This service assumes a single primary NVIDIA GPU (index 0).
- If the service is accessed from another host on Windows, `scripts/up.ps1` ensures the Windows Firewall rule exists when run elevated.
- Do not add reverse proxy config, firewall rules, DNS, or registry changes in this repo; those belong in `homelab-infra`.
