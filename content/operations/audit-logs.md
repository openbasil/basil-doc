+++
title = "Audit logs"
weight = 40
+++

# Audit logs

With config key `audit-log = "<FILE>"`, Basil appends one JSON line per authorization decision. The
file is opened `O_APPEND|O_CREATE` at `0600` once at startup; if it can't be opened, startup aborts
(fail closed: you don't run blind). Decisions are also emitted via `tracing` when no file is set.

## Record shape

| Field | Meaning |
| --- | --- |
| `event_kind` / `event_version` | Stable event identity: `basil.audit.authz` version `2`. |
| `occurred_at` | UTC timestamp for the decision record. |
| `generation` | Policy/catalog generation that made the decision. |
| `op` | The gated operation (`sign`, `mint`, `rotate`, …). |
| `target_kind` / `target_id` | The target type (`catalog_key`) and dotted catalog key. |
| `actor_kind` / `actor_id` | The actor Basil authorized. Today this is a policy `subject`, such as `svc.nats`. |
| `authenticated_by` | Evidence summaries that established the actor, such as `unix_peercred:svc.nats` or a `signature-key` proof for a sealed invocation. |
| `presenter_kind` / `presenter_id` | The immediate presenter, such as `unix_peercred` and `svc-nats(9002)`. For bridged requests this is the bridge process, not the signed actor. |
| `decision` / `outcome` | `allow` or `deny`. `decision` is present for consumers that treat authz as a decision stream; `outcome` is retained as the audit outcome spelling. |
| `reason` | A short stable token: on allow, *what* granted it (`subject:<name>` / `public_class`); on deny, *which* check failed (`unknown_key` / `not_writable` / `not_permitted`). |

Example:

```json
{
	"event_kind": "basil.audit.authz",
	"event_version": 2,
	"occurred_at": "2026-06-30T00:00:00Z",
	"generation": 3,
	"op": "sign",
	"target_kind": "catalog_key",
	"target_id": "nats.account",
	"actor_kind": "subject",
	"actor_id": "svc.nats",
	"authenticated_by": ["unix_peercred:svc.nats"],
	"presenter_kind": "unix_peercred",
	"presenter_id": "svc-nats(9002)",
	"decision": "allow",
	"outcome": "allow",
	"reason": "subject:svc.nats"
}
```

{% best() %}
Ship the audit file to an append-only store and alert on `deny` spikes and on any `operator`-role
`allow` (rotate/import/set). The record answers "who asked for what, on which key, and were they
allowed", and it never contains key material, so it's safe to forward and back up.
{% end %}

For sealed or bridged invocation, treat `actor_*` as the authorized subject and `presenter_*` as the
transport process that delivered the request. The bridge's Unix subject is useful operational context,
but it does not inherit the actor's data-plane grants and cannot make an unsigned COSE message
authorize.
For the NATS bridge, `authenticated_by` summarizes the sealed `signature-key` actor proof, while
`presenter_id` names the bridge process that delivered the message (presenting needs no policy
grant of its own).

## Sinks

| Sink                           | Status                                     |
| ------------------------------ | ------------------------------------------ |
| Local JSONL file (`audit-log`) | <span class="pill impl">implemented</span> |
| OTLP / OpenTelemetry           | <span class="pill impl">implemented</span> |
| journald                       | <span class="pill impl">implemented</span> |
| syslog                         | <span class="pill gap">roadmap</span>      |
| NATS                           | <span class="pill gap">roadmap</span>      |
| Prometheus metrics             | <span class="pill gap">roadmap</span>      |

Configure runtime tracing sinks under `[logging]`. `stdout` and `journald` are enabled by default;
disable either with `[logging.stdout].enable = false` or `[logging.journald].enable = false`.

OTLP log export is compiled behind the default-off `otlp` cargo feature. A binary built with that
feature accepts:

```toml
[logging.opentelemetry]
enable = true
endpoint = "http://localhost:4317"
protocol = "grpc" # "grpc", "http-binary", or "http-json"
```

If `logging.opentelemetry.enable = true` is set on a binary built without `otlp`, startup fails
closed instead of silently dropping telemetry.

## Where to go next

- [Incident runbook](/troubleshooting/incident-runbook/): using the audit trail during a response.
- [The policy](/configuration/policy/): how subjects and `reason` map to grants.
- [NATS bridge](/clients/nats-bridge/): bridge-specific actor and presenter semantics.
