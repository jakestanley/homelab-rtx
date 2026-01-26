# homelab-rtx

Windows service that exposes current NVIDIA GPU status over HTTP for Homepage customapi widgets.

## Runtime

- Platform: Windows
- Service manager: NSSM (see `scripts/install-service.ps1`)
- HTTP only; TLS and ingress are managed in `homelab-infra`
- Port and DNS are defined in `../homelab-infra/registry.yaml` (service name: `rtx`)

## Endpoints

- `GET /health` (also `/`)
  - Returns:
    - `status` (ok/error)
    - `temperature` (formatted, e.g. `65 C`)
    - `memory_available` (formatted, e.g. `8123 MiB`)
    - `gpu_utilization` (formatted, e.g. `34 %`)

## Configuration

Configuration is via environment variables (see `.env.example`).

## Run manually

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
- NSSM stdout/stderr are logged to `logs/`.

## Notes

- `nvidia-smi` must be available on PATH for metrics collection.
- If the service is accessed from another host, `scripts/up.ps1` ensures the Windows Firewall rule exists when run elevated.
