<!-- VENDORED:BEGIN -->
generated-from: homelab-standards
do-not-edit: true
canonical-source: PATTERNS/windows-nssm-service.md
<!-- VENDORED:END -->

# Windows NSSM Service

Use this pattern when a service must run long-term on Windows and be installable as a Windows Service.

## Principles
- Installation is idempotent and reversible
- Service wiring (ports/exposure) is owned by homelab-infra
- The service must run manually without NSSM
- Prefer running `scripts/up.ps1` as the NSSM target unless the repo explicitly documents another entrypoint

## Requirements
- `nssm` available on PATH
- PowerShell available
- Repo provides:
  - `scripts/up.ps1` (starts the service in the intended mode)
  - `scripts/install-service.ps1` (installs/updates the NSSM service)

## Install / Update
From an elevated PowerShell prompt:

```powershell
.\scripts\install-service.ps1 -Start
```

## Uninstall

```
.\scripts\install-service.ps1 -Stop -Uninstall
```