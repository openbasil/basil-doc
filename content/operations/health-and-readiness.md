+++
title = "Health & readiness probes"
weight = 60
+++

# Health & readiness probes

Basil exposes two probes over its existing peer-cred-attested Unix-socket admin gRPC surface; no
extra port is opened. They are deliberately distinct:

- **Health (liveness)** - is the broker *process* up and serving the socket? Cheap,
  always-answerable, and does **no backend I/O**. Reaching the handler means the accept loop and gRPC
  stack are alive. It says nothing about whether data-plane ops can succeed.
- **Readiness** - can the broker actually *serve*? It runs the read-only existence probe over every
  catalog key and reports whether serving would **fail closed**: an unreachable/rejecting backend, or
  a `missing=error` key whose material is absent. Either makes the broker not ready. Absent keys
  are classified against the **currently serving** generation, so a hot reload that flips a key's
  `missing` policy (say `warn` to `error`) changes the verdict on the next probe, without a restart.
  The probe result is cached for a short window (a couple of seconds); a hot reload (generation
  change) invalidates the cache immediately.

Both probes are **ungated** for any socket peer. Readiness returns a non-secret summary only:
counts, a coarse reason category, and the active generation id. It never returns key names, key
material, or the catalog inventory, so it cannot be used to enumerate secrets.

## CLI surface

```sh
# Liveness: exit 0 if the agent answers, nonzero on connect/RPC failure.
basil health
basil health --json     # {"alive":true,"version":"0.1.0"}

# Readiness: exit 0 if ready, 1 if not ready, other nonzero on connect/RPC failure.
basil ready
basil ready --json      # one-line JSON object (schema below)
```

## Exit codes

| Command        | Exit 0                   | Exit 1                                                       | Other nonzero                                  |
| -------------- | ------------------------ | ------------------------------------------------------------ | ---------------------------------------------- |
| `basil health` | Process alive (answered) | -                                                            | Connect/RPC failure (socket gone, daemon down) |
| `basil ready`  | Ready to serve           | **Not ready** (backend unreachable or a required key absent) | Connect/RPC failure                            |

The "not ready" (exit 1) and "cannot reach the agent" (other nonzero) cases are distinct, so a probe
can tell a broker that is *up but not ready* from one that is *down*.

## `basil ready --json` schema

| Field                   | Type   | Meaning                                                                                     |
| ----------------------- | ------ | ------------------------------------------------------------------------------------------- |
| `ready`                 | bool   | `true` iff serving would not fail closed for any key and every backend is reachable.        |
| `reason`                | string | Coarse category: `ready`, `backend_unreachable`, or `required_key_missing`.                 |
| `generation`            | uint   | The currently serving catalog/policy generation id (bumped on each hot reload).             |
| `keys_total`            | uint   | Total catalog keys probed (`0` when the backend was unreachable before any per-key detail). |
| `keys_present`          | uint   | Keys whose material is present.                                                             |
| `keys_required_missing` | uint   | Absent `missing=error` keys (ops fail closed). Non-zero ⇒ not ready.                        |
| `keys_optional_missing` | uint   | Absent `warn`/`generate` keys (reported; do not block readiness).                           |

`basil health --json` emits `{"alive":<bool>,"version":"<build>"}`.

## Wiring it into your supervisor

**systemd** - gate startup on readiness, and keep a liveness check:

```ini
[Service]
# Block "started" until the broker can actually serve (readiness).
ExecStartPost=/usr/bin/basil ready
# Optional periodic liveness check via a companion timer/healthcheck:
# ExecCondition or a timer calling: /usr/bin/basil health
```

**Container `HEALTHCHECK`** - readiness as the health signal:

```dockerfile
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s \
  CMD basil ready || exit 1
```

**Kubernetes** - map each probe to its kind via an `exec` probe. The probes have no HTTP port, so use
the CLI against the mounted socket. The only HTTP surface is the opt-in
[JWKS endpoint](/configuration/jwks/), which requires an `http` build and `jwks.enable = true`:

```yaml
livenessProbe:
  exec:
    command: ["basil", "health"]
  periodSeconds: 10
readinessProbe:
  exec:
    command: ["basil", "ready"]
  periodSeconds: 10
  failureThreshold: 3
```

{% note(title="Run the CLI under a peer with socket access") %}
The probe CLI connects over the same attested Unix socket as every client, so the probe process must
be able to reach it (socket mode/group, see [Configuration overview](/configuration/overview/)). The
probes are ungated, so any peer that can open the socket can run them; they return only the non-secret
summary above.
{% end %}

{% best() %}
Use readiness (not liveness) for traffic gating and rollout health: a broker can be alive yet not
ready (backend still warming, a required key not yet provisioned). Reserve liveness for "is the
process wedged?" so a transient backend blip does not trigger a restart loop. A `backend_unreachable`
readiness is usually transient infra; a persistent `required_key_missing` is a provisioning gap.
{% end %}

## Where to go next

- [Doctor (preflight checks)](/operations/doctor/): diagnose the environment *before* startup.
- [Hot reload](/operations/hot-reload/): the generation id readiness reports.
- [Incident runbook](/troubleshooting/incident-runbook/): backend-unreachable response.
