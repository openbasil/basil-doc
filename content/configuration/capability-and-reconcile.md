+++
title = "Capability policy & reconcile"
weight = 50
+++

# Capability policy & reconcile

Two startup checks keep you from booting a broker that can't do its job:

- **Capability policy** (`capability-policy`): does each backend provide the engines, capabilities, and
  mintable key types the catalog needs? Pure catalog math, no backend I/O.
- **Reconcile**: does each key actually exist in its backend? Honors each key's `missing` policy.

| Setting | Behavior |
| --- | --- |
| `capability-policy = "strict"` | *Default.* Any unmet requirement aborts startup. Every gap is reported together. |
| `capability-policy = "degraded"` | Defer to each key's `missing`: a gap on a `missing=error` key is still fatal; others are logged and the broker serves the rest. |
| `capability-policy = "off"` | Skip the capability check entirely. |
| `missing: error` (per key) | Absent material aborts startup. The default: a required key can't go missing silently. |
| `missing: warn` (per key) | Log and continue; ops on that key fail until it exists. |
| `missing: generate` (per key) | Create the material at startup (within the limits in [the catalog](/configuration/catalog/)). |
| `no-reconcile = true` | Skip the existence probe entirely. A missing key then surfaces at request time instead of at boot. |

## Mintable key types

Backends declare mintable transit key types with `mintKeyTypes`. Basil checks catalog `generate`,
`import`, and `new_key` requests against that static list before it asks the backend to create
material. A backend that only declares `ed25519` cannot mint `rsa-2048`, `ecdsa-p256`,
`ecdsa-p384`, `ecdsa-p521`, `ed25519-nkey`, or PQC key types until its `mintKeyTypes` declaration
includes them.

This is a fail-closed startup guard. In `strict` mode an undeclared mint type aborts startup with the
rest of the capability-policy report; in `degraded` mode it still follows the affected key's
`missing` policy. Runtime dispatch keeps the same backstop, so a request never relies on a backend
to discover an unsupported generated key type after policy has allowed it.

{% danger(title="These loosen fail-closed") %}
`degraded`/`off` and `no-reconcile = true` trade a loud startup failure for a quiet runtime one.
They're for recovery and known-divergent backends, not steady state. The runtime `UNSUPPORTED` backstop
still catches an op that hits a missing capability, but you'd rather find out before traffic does.
{% end %}

{% best() %}
Production runs `capability-policy = "strict"` with reconcile on. If you need an escape hatch to
recover, scope it tightly (a one-off invocation), record why, and remove it once the backend converges.
{% end %}

## Where to go next

- [The catalog](/configuration/catalog/): where each key's `missing` policy is set.
- [Doctor](/operations/doctor/): preflight the environment before the daemon tries to unlock and bind.
- [Incident runbook](/troubleshooting/incident-runbook/): using these hatches during recovery.
