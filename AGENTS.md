# Agent Notes

## Stability contract

Two consumers depend on this repo's surface and must keep working:

1. **Docker Compose** — `docker-compose.yml` + `Dockerfile`.
2. **Ansible NSSM deployment** in `jakestanley/windows` (the `shrike` repo).
   Its `ansible/roles/services/tasks/main.yml` clones this repo into
   `C:\homelab\homelab-rtx\`, seeds `.env` from `.env.example`, and runs
   `scripts/up.ps1`.

Do not rename, move, or remove the following without a paired PR to both
consumers:

- `docker-compose.yml`, `Dockerfile`, `requirements.txt`
- `.env.example` — the single canonical config template for compose,
  NSSM, and systemd
- `scripts/up.ps1` — idempotent NSSM install / update / start; accepts
  `-Restart`
- `scripts/uninstall.ps1`

Reserved env keys in `.env.example`:

- `RTX_PYTHON_EXE` — matches shrike's `^([A-Z_]+_PYTHON_EXE)=` seed
  pattern and is rewritten to the discovered `python.exe` path on first
  clone. Renaming this key breaks auto-seeding.
- `RTX_PORT` — declared port used by the firewall rule in `up.ps1`.
- `NSSM_SERVICE_NAME`, `NSSM_DISPLAY_NAME`, `NSSM_DESCRIPTION` — namespace
  reserved for NSSM service identity. Filtered out of `AppEnvironmentExtra`
  before being passed to the app process.

Do not reintroduce parallel config templates (e.g. `systemd/rtx.env.example`).
`.env.example` is the single source of truth.
