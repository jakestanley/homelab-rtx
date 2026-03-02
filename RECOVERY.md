# RECOVERY

## Prerequisites

- Linux host with `systemd` or Windows host with NSSM
- NVIDIA drivers installed
- `nvidia-smi` on PATH
- Python 3.11+ available
- Linux: Python environment for `/srv/rtx` and a dedicated `rtx` user/group
- Windows: NSSM installed and on PATH

## Recovery order

1. Confirm `../homelab-infra/registry.yaml` still defines the `rtx` service and expected port.
2. Restore repo files to the expected working directory:
   - Linux: `/srv/rtx`
   - Windows: repo checkout path used by NSSM
3. Rebuild the Python environment if needed:
   - Linux:
     ```sh
     python3 -m venv /srv/rtx/.venv
     /srv/rtx/.venv/bin/pip install -r /srv/rtx/requirements.txt
     ```
   - Windows:
     ```powershell
     .\scripts\up.ps1
     ```
4. Restore service configuration files:
   - Linux unit: `/etc/systemd/system/rtx.service`
   - Linux env file: `/etc/rtx/rtx.env`
   - Linux service user/group: `rtx:rtx`
5. Re-enable or restart the service:
   - Linux:
     ```sh
     sudo systemctl daemon-reload
     sudo systemctl enable --now rtx.service
     ```
   - Windows:
     ```powershell
     .\scripts\install-service.ps1 -Start
     ```
6. Verify logs and runtime state:
   - Linux: `journalctl -u rtx.service -f`
   - Linux metrics CSV: `/srv/rtx/logs/gpu-metrics.csv`
   - Windows NSSM logs: `logs/nssm-stdout.log`, `logs/nssm-stderr.log`
   - Windows metrics CSV: `logs/gpu-metrics.csv`

## Linux verification

- `getent passwd rtx >/dev/null`
- `getent group rtx >/dev/null`
- `test -x /srv/rtx/.venv/bin/python`
- `command -v nvidia-smi`
- `systemctl status rtx.service`

## Windows verification

Re-run the service entrypoint or installer if you need to restore dependencies or the NSSM registration:

```powershell
.\scripts\up.ps1
.\scripts\install-service.ps1 -Start
```

## Avoid

- Do not change ports or ingress here; update `homelab-infra` instead.
- Do not manage TLS in this service.
- Do not change `/srv/rtx`, `/etc/systemd/system/rtx.service`, or `/etc/rtx/rtx.env` casually on Linux without updating the unit to match.
