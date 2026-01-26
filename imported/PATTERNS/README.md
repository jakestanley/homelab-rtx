<!-- VENDORED:BEGIN -->
generated-from: homelab-standards
do-not-edit: true
canonical-source: PATTERNS/README.md
<!-- VENDORED:END -->

> Note: Pattern documents are vendored into consumer repositories under
> `imported/PATTERNS/` for agent visibility. Canonical versions live here.

## Patterns

Patterns in `homelab-standards` describe recurring design constraints,
not projects, frameworks, or implementations.

They exist to:
- prevent scope creep
- avoid duplicated or diverging stacks
- guide decisions when a known class of problem appears

Patterns:
- live under `homelab-standards/PATTERNS/`
- are optional and situational
- use MUST / SHOULD / MUST NOT language where helpful
- define constraints, trade-offs, and non-goals
- avoid prescribing frameworks or speculative extensibility

Patterns may be referenced by `AGENTS.md`, but `AGENTS.md` remains focused
on agent behaviour rather than architecture.

## Pattern index

- `windows-nssm-service.md`
  - Applies when creating or changing `scripts/install-service.ps1` or Windows service install behaviour.
