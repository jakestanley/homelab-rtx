<!-- VENDORED:BEGIN -->
generated-from: homelab-standards
do-not-edit: true
canonical-source: AGENTS.md
<!-- VENDORED:END -->

# AGENTS.md — Homelab Standards

## Scope

This document defines how automation agents (Codex, ChatGPT, generators,
scripts) are expected to behave when making changes to repositories prefixed
`homelab-*`.

It defines **rules of change**, not runtime state.

- Runtime state (ports, DNS, upstreams) is defined in `homelab-infra`
- This document defines how agents are allowed to interact with that state

---

## Authority

- This file lives in `homelab-standards`
- It is the canonical reference for agent behaviour
- Other repositories should reference this document rather than duplicate it

If an instruction conflicts with this document or with `homelab-infra`,
the agent should stop and request clarification.

---

Some agent-facing documentation may be vendored into consumer repositories under `imported/` for tool visibility; canonical versions live here.

---

## Core Principles

1. **Minimal change**
   - Make the smallest change required to achieve the goal
   - Avoid refactors, reformatting, or stylistic changes unless requested
   - Do not “improve” unrelated code

2. **Registry-led configuration**
   - `homelab-infra/registry.yaml` defines ports, DNS names, and upstream hosts
   - Agents should align services to the registry rather than invent values

3. **Prefer stability over redesign**
   - For fragile or historically problematic systems (VPN stacks, media
     servers, legacy services), alignment is preferred over correctness
   - Topology changes should not be made implicitly

4. **Exceptions are explicit**
   - Legacy services, native ports, and out-of-range ports are acceptable
     when declared
   - Implicit or hidden behaviour is discouraged

---

## Referencing This Document

- Service repositories may include a local `AGENTS.md`
- If present, it should defer to this document and link to it
- This document should not be copied verbatim into other repositories

Example reference:

> Canonical agent behaviour is defined in `homelab-standards/AGENTS.md`

---

## Repository Structure Conventions

Unless a repository explicitly documents otherwise, service repositories
are expected to contain:

```
.
├── docker-compose.yml        # if Docker-based
├── .env.example
├── .gitignore
├── scripts/
│   └── up.sh
├── README.md
├── RECOVERY.md
```

If a service is not Docker-based (e.g. Windows + NSSM, systemd),
this should be stated clearly in `README.md`.

New service repositories are expected to start from the canonical service 
template unless explicitly documented otherwise.

---

## Patterns

Some recurring service designs are documented as patterns under
`homelab-standards/PATTERNS/`.

Patterns are indexed in `PATTERNS/README.md` and describe **constraints and trade-offs**, not implementations.

When a change clearly matches an indexed pattern, agents SHOULD consult the relevant pattern document (via `imported/PATTERNS/README.md`) before proposing or implementing a solution.

Examples:
- Changes to `scripts/install-service.ps1` ⇒ consult the Windows NSSM service pattern, if indexed
- Multi-variant service layouts ⇒ consult the multi-variant services pattern, if indexed

---

## Secrets and Configuration

- Secrets should not be committed to version control
- `.env` and `.env.*` files should be excluded via `.gitignore`
- `.env.example` should exist and list all required variables with
  placeholder values

When modifying a repository, agents should:
- create `.env.example` if missing
- ensure secret-bearing files are ignored

---

## Runtime Conventions

### Linux Hosts
- Docker is the default runtime
- systemd services are acceptable for legacy or non-containerised software

### Windows Hosts
- Services are expected to run via **NSSM**
- Docker-on-Windows is generally avoided
- Services should expose a single HTTP port and not manage TLS internally

Runtime choice is documented in the service repository and is not inferred
from the registry.

#### Windows-hosted Services

For services running on Windows hosts:

- Services MUST bind to `0.0.0.0` or the host LAN IP
- If the service is accessed from another host (e.g. via nginx proxying),
  an inbound Windows Firewall rule MUST exist for the service port
- This MUST be implemented in `scripts/up.ps1` (PowerShell), idempotently:
  - When running elevated, `scripts/up.ps1` MUST ensure the firewall rule exists (create it if missing)
  - If the firewall rule already exists for the configured service port, it MUST not be recreated
  - If `scripts/up.ps1` is not running elevated, it MUST print a clear warning and print the exact `New-NetFirewallRule` PowerShell command (with the resolved port value) the user should run elevated to create the firewall rule
  - The firewall rule MUST be limited to TCP, the configured service port, and the Private profile

Failure to configure firewall access is a common cause of unreachable
services and should be addressed before diagnosing proxy or DNS issues.

#### Windows Services (NSSM)

Goal: a running service that survives reboots and restarts.

For Windows-hosted homelab-* services:

- Repos MUST provide `scripts/install-service.ps1` which installs/updates the service using **NSSM**
- `scripts/install-service.ps1` MUST default `-ServiceName` to the repo folder name if not provided
- `scripts/install-service.ps1` MUST accept `-Start` to ensure the service is running after install/update
  - `-Start` MUST prefer a clean restart: restart when the service is already running (or otherwise not stopped), and start only when stopped
  - Rationale: `nssm start` may report “already running” and leave a wedged service untouched (observed with `homelab-ollama`)
- `scripts/install-service.ps1` MUST set NSSM `AppDirectory` to the repo root
- `scripts/install-service.ps1` MUST log stdout/stderr to `logs/` (ensure the directory exists)
- `scripts/install-service.ps1` MUST be idempotent (safe to re-run)


Entrypoint selection:

- NSSM SHOULD run PowerShell invoking `scripts/up.ps1` as the canonical entrypoint
- NSSM MAY run a Python entrypoint directly if more practical for the repo (for example: `.venv\Scripts\python.exe app.py`).
  - Using python app.py without an explicit interpreter path is discouraged, as Windows services do not activate virtual environments or inherit shell PATH state.
- If not using `scripts/up.ps1`, the repo MUST document the chosen entrypoint and reason in `README.md`

Process-wrapper services MAY manage third-party runtimes and SHOULD prefer conservative detection over strict ownership.

---

## Technology Preferences (Defaults)

When creating new services, scripts, or tooling, the following defaults
are preferred unless there is a clear reason to deviate.

These are preferences rather than requirements.

### Backend / Services

- Language: Python
- Environment: project-local `venv`
- Dependencies: `requirements.txt`
- Configuration: `python-dotenv`
- HTTP framework: Flask

Alternative frameworks (e.g. FastAPI) are reasonable when justified.

Agents should:
- document environment setup in `README.md`
- avoid reliance on global Python installations

---

### Configuration Formats

- Simple configuration: environment variables
- Structured configuration: YAML (via PyYAML)

Mixing multiple configuration formats should be avoided without good reason.

---

### Frontend / UI

- Preferred framework: Vue.js
- Intended scope: lightweight internal dashboards and admin UIs

Introducing a frontend should be proportional to the problem being solved;
static HTML is often sufficient.

---

## Ports and Networking

- The homelab port range is reserved for HTTP services
- Ports outside that range should be declared explicitly (e.g. native ports)
- Gateway-published ports (VPN / gluetun) are valid exceptions

### Host Networking

Host networking is acceptable when a service must interact directly with the host’s network interface (e.g. Wake-on-LAN, broadcast discovery, low-level protocols).

In these cases:
- For Docker-based services, Docker host networking (`network_mode: host`) may be used
- The decision must live in infrastructure configuration
- The service itself must remain network-agnostic
- Host networking SHOULD be treated as an explicit exception and documented at the point of use

Agents should align service configurations to the registry rather than
reassigning ports or altering network topology.

---

## Gateway / VPN-Published Services

For services routed through a gateway container (e.g. gluetun):

- The gateway container publishes host ports
- Dependent services do not publish ports directly
- Existing topology should be preserved unless change is explicitly requested

---

## Preflight Dependency Checks

Service repositories are expected to perform a preflight check that verifies:

- `homelab-infra`
  - is a git repository
  - has no uncommitted changes
  - is at the default branch HEAD
- `homelab-standards`
  - same checks as above

If checks fail, the user should be warned and prompted before continuing.
Automatic pulls or resets are avoided.

---

## Scripts

### scripts/up.sh

- Acts as the canonical startup entrypoint
- Is executable
- May run preflight dependency checks before starting services

Startup logic should not live solely in README instructions.

---

## Documentation

### README.md
Should state:
- what the service does
- how it is run (Docker / NSSM / systemd)
- that ingress and ports are defined in `homelab-infra`
- any notable exceptions or constraints

### RECOVERY.md
Should describe:
- prerequisites
- high-level recovery order
- areas that should not be changed casually

---

## Intent

These standards exist to reduce cognitive load, preserve working systems,
and make recovery predictable.

They are intentionally conservative.
