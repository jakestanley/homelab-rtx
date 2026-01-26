# RECOVERY

## Prerequisites

- Windows host with NVIDIA drivers installed
- `nvidia-smi` on PATH
- Python 3.11+ available
- NSSM installed and on PATH

## Recovery order

1. Confirm `../homelab-infra/registry.yaml` still defines the `rtx` service and expected port.
2. Re-run dependency install:
   ```powershell
   .\scripts\up.ps1
   ```
3. Re-install or restart the NSSM service:
   ```powershell
   .\scripts\install-service.ps1 -Start
   ```
4. Check logs:
   - `logs/nssm-stdout.log`
   - `logs/nssm-stderr.log`
   - `logs/gpu-metrics.csv`

## Avoid

- Do not change ports or ingress here; update `homelab-infra` instead.
- Do not manage TLS in this service.
