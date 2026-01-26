<!-- VENDORED:BEGIN -->
# registry.yaml contract

This document describes the expected structure of `registry.yaml` in this repository.

This file is designed to be **vendored into sibling repos for agent consumption**.

Important: `registry.yaml` itself is **not** vendored/exported. Only `REGISTRY.md` and
`registry.schema.yaml` are intended for vendoring.

## What `registry.yaml` is for

`registry.yaml` is the canonical source of truth for homelab DNS names, reverse proxy routing, and
service placement. Consumers should treat the file as authoritative when generating downstream config.

## Service entries (`services.<name>`)

Each entry under `services` describes one service exposed in the homelab.

Required fields:

- `dns` (string): Internal DNS name for the service (e.g. `upsnap.stanley.arpa`).
- `proxy_host` (string): Host key (from `hosts`) where reverse proxy config is applied.
- `upstream` (object): Where the service actually listens.
  - `upstream.host` (string): Host key (from `hosts`) that runs the service.
  - `upstream.port` (int): Port the service listens on.
  - `upstream.scheme` (string): `http` or `https`.

Optional fields (currently used):

- `healthcheck_path` (string): Path used for simple HTTP health checks (e.g. `/`).
- `native_ports` (object): Ports that must be exposed outside the homelab port range for client
  compatibility (e.g. Plex). Keys may include `tcp` and/or `udp`, each a list of integers.

## Example

```yaml
services:
  upsnap:
    dns: upsnap.stanley.arpa
    proxy_host: adler
    upstream:
      host: adler
      port: 20014
      scheme: http
```

## Schema format

`registry.schema.yaml` is a **JSON Schema (draft 2020-12)** document serialized as YAML.
This keeps the file readable and diff-friendly while still matching the JSON Schema ecosystem.
<!-- VENDORED:END -->
