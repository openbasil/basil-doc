+++
title = "Doctor (preflight checks)"
weight = 80
+++

# Doctor (preflight checks)

`basil doctor` answers "will the daemon even get off the ground here?" before you start it. It
resolves the *same* config the daemon does (`-c`/`--config` TOML plus
`--catalog`/`--policy`/`--bundle`/`--socket` overrides and the `BASIL_*` env vars), then runs a set of
**independent** read-only diagnostics (backend binary & reachability, socket sanity, sealed-bundle
readability/permissions/freshness, catalog/policy validation, and cargo-feature compatibility) and
reports each as `ok` / `warn` / `fail` with actionable remediation.

It is the single first-boot / pre-deploy preflight (the former `basil config check` is folded into
it). Its **offline** tier probes whether the *environment* is wired up at all: the catalog/policy
load, each backend can provide the capabilities its keys need, and any invocation
broker-identity/key bindings resolve. Adding `--keys` layers on an **authenticated** tier — doctor
unlocks the sealed bundle and runs the read-only per-key existence probe the old
`config check --require` performed.

{% note(title="Read-only, non-mutating, secret-free by default") %}
Default doctor never unlocks the bundle, binds the socket, reconciles, generates a key, or writes
the epoch sidecar. Every step handles its own error into a check result, so one failing check never
aborts the rest. The bundle checks report readability, permissions, and freshness only: no bundle
contents, key material, passphrases, or tokens ever reach stdout, the JSON, or an error string.
`--keys` is the deliberate boundary crossing: it unlocks the bundle to build the backend
manager, then performs only metadata/KV existence reads. It still never reconciles, generates,
rotates, imports, or writes the epoch sidecar.
{% end %}

## The subcommand & flags

```sh
basil doctor -c /etc/basil/agent.toml                  # human-readable, offline
basil doctor -c /etc/basil/agent.toml --json           # stable machine output
basil doctor -c /etc/basil/agent.toml --keys --json    # add the authenticated per-key probe
basil doctor -c /etc/basil/agent.toml --strict         # warnings exit non-zero too
```

| Flag | Meaning |
| --- | --- |
| `-c` / `--config` | The daemon TOML config to diagnose (same file `agent` loads). Individual paths can also be supplied via `--catalog`/`--policy`/`--bundle`/`--socket` or `BASIL_*`. |
| `--json` | Emit the stable, versioned JSON document instead of human-readable text. |
| `--keys` | Opt in to the authenticated key-material probe: unlock the bundle, build the manager, and read-only-check every catalog key. A missing required key is **fatal**; an optional (or `missing=generate`) key only **warns**. Emits an aggregate `key_material` row plus one `key_material:<key>` row per key. |
| `--strict` | Treat warnings as failures: exit non-zero if any check is a warning, not just on a fatal condition. |

## The checks

| `name` | What it means | fatal / warn |
| --- | --- | --- |
| `catalog_policy` | The catalog + policy load and validate via the same loader `agent` uses. | **fatal** if either does not load. |
| `capability` | Offline backend-capability enforcement: each backend provides what its catalog keys (and explicit `requires`) need. Honors `capability-policy`. | **fatal** on a capability gap under `strict`; relaxed to advisory under `degraded`/`off`. |
| `invocation_bindings` | Offline validation that, when invocation is enabled, its broker-identity and request/response key bindings resolve to catalog keys of the right shape. | **ok** when invocation is disabled or valid; **fatal** when enabled but a binding is invalid. |
| `feature_compatibility` | The binary's enabled cargo features cover the optional unlock slots and backends the config declares. | **fatal** on any mismatch; it names the exact missing feature. |
| `backend_binary` | For a `vault`-kind backend, `bao` or `vault` is on `PATH`. | **warn** if neither is found (the daemon talks HTTP and does not strictly need the CLI). |
| `socket` | Parent dir writable, mode not world-writable, `socket-group` resolves to a gid; the socket is **not** bound. | **fatal** on a bad parent or group; **warn** on a world-writable mode. |
| `bundle_readable` | The sealed bundle exists at the configured path and is readable. | **fatal** if absent/unreadable. |
| `bundle_perms` | The sealed bundle is strict `0600` (owner-only). | **fatal** on any broader mode. |
| `bundle_freshness` | The bundle's epoch is not behind the `.epoch` sidecar (anti-rollback). | **fatal** if the epoch is behind or corrupt; **warn** if the sidecar is absent (first boot). |
| `backend_reachability` | Each distinct `vault` address answers an unauthenticated `GET /v1/sys/health` within ~3s. | **fatal** on any unreachable address (it never hangs the run). |
| `key_material` | `--keys` only: probes every catalog key read-only, like startup reconcile; no writes. Emits an aggregate row plus one `key_material:<key>` row per key. | **fatal** on an absent required key or probe error; **warn** on absent optional / `missing=generate` keys. |

`feature_compatibility` checks the unlock-slot features (`unlock-bip39`, `unlock-age-yubikey`) and the
backend features (`keystore-backend`, `aws-kms`, `gcp-kms`), naming any the binary lacks. A normal
default build includes 1Password, BIP39, and `age`/YubiKey support; this check matters most for
`--no-default-features`, cloud KMS, and other custom builds.

## Exit codes

The exit code is derived from the worst severity among the checks that ran. Only a **fatal**
condition — one that would stop the broker from starting — exits non-zero on its own; every other
finding is a report-only **warning**.

| Exit | Meaning |
| --- | --- |
| `0` | No `fatal` check. Advisory `warn`s alone still exit `0` (unless `--strict`). |
| non-zero | At least one **fatal** check: catalog/policy won't load, a backend is unreachable, the bundle won't unlock or is stale, a capability gap under `strict`, or a `missing=error` key the probe can't satisfy. With `--strict`, a `warn` (e.g. a `missing=generate` key, `bao` not on PATH, loose bundle perms) also exits non-zero. |

## JSON schema (`--json`)

The document is **versioned and stable** (`schema_version` is currently `2`; version 1 used a `fail`
status token and carried no `fatal` count). Operators script against the field names and the `status`
tokens.

```json
{
  "schema_version": 2,
  "checks": [
    { "name": "backend_reachability", "status": "fatal",
      "detail": "1 of 1 vault backend address(es) unreachable: http://127.0.0.1:8200",
      "remediation": "Start/reach the backend (OpenBao/Vault) at the configured address, or fix `addr` …" }
  ],
  "summary": { "total": 11, "ok": 9, "warn": 0, "fatal": 2, "blocking": true }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | uint | Document schema version (currently `2`). |
| `checks[]` | array | One object per check, in a deterministic order. |
| `checks[].name` | string | Stable machine identifier (e.g. `backend_reachability`, or `key_material:<key>` for a per-key row under `--keys`). |
| `checks[].status` | string | `ok` / `warn` / `fatal`. |
| `checks[].detail` | string | Human-readable finding (no secret bytes). |
| `checks[].remediation` | string | Actionable fix for a non-`ok` result (empty for `ok`). |
| `summary.total` / `ok` / `warn` / `fatal` | uint | Per-status counts. |
| `summary.blocking` | bool | `true` iff any check is `fatal`: the run exits non-zero. |

{% best() %}
Run `basil doctor` on every node as a pre-start gate (e.g. a systemd `ExecStartPre=` or a first-boot
provisioning step) so a missing run dir, a wrong bundle mode, an unreachable backend, or a
feature-mismatched binary is caught *before* the daemon tries to unlock and bind. Scrape the `--json`
document if you orchestrate fleets: assert `summary.blocking == false`, or alert on any
`checks[].status == "fatal"`. Add `--keys` when the pre-start environment has access to the same
unlock material as the daemon. Pair it with [policy explain](/operations/policy-explain/) for full
pre-deploy coverage.
{% end %}

## Where to go next

- [Capability policy & reconcile](/configuration/capability-and-reconcile/): what a clean start checks.
- [Production hardening checklist](/operations/production-hardening/): the go-live items doctor
  cannot check for you.
- [Health & readiness probes](/operations/health-and-readiness/): the *running* equivalents.
- [Policy explain / dry-run](/operations/policy-explain/): preview authorization outcomes.
