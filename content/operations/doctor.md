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

It is the first-boot / pre-deploy companion to `basil config check`: `check` probes whether the *keys*
exist in a reachable backend; default `doctor` probes whether the *environment* is wired up at all.
When an operator explicitly adds `--check-keys`, doctor also unlocks the sealed bundle and runs the
same authenticated read-only key-existence probe that powers `basil config check --require`.

{% note(title="Read-only, non-mutating, secret-free by default") %}
Default doctor never unlocks the bundle, binds the socket, reconciles, generates a key, or writes
the epoch sidecar. Every step handles its own error into a check result, so one failing check never
aborts the rest. The bundle checks report readability, permissions, and freshness only: no bundle
contents, key material, passphrases, or tokens ever reach stdout, the JSON, or an error string.
`--check-keys` is the deliberate boundary crossing: it unlocks the bundle to build the backend
manager, then performs only metadata/KV existence reads. It still never reconciles, generates,
rotates, imports, or writes the epoch sidecar.
{% end %}

## The subcommand & flags

```sh
basil doctor -c /etc/basil/agent.toml            # human-readable
basil doctor -c /etc/basil/agent.toml --json     # stable machine output
basil doctor -c /etc/basil/agent.toml --check-keys --json
```

| Flag | Meaning |
| --- | --- |
| `-c` / `--config` | The daemon TOML config to diagnose (same file `run` loads). Individual paths can also be supplied via `--catalog`/`--policy`/`--bundle`/`--socket` or `BASIL_*`. |
| `--json` | Emit the stable, versioned JSON document instead of human-readable text. |
| `--check-keys` | Opt in to the authenticated key-material probe: unlock the bundle, build the manager, and read-only-check every catalog key. Required missing keys fail; optional keys warn. |

## The checks

| `name` | What it means | fail / warn |
| --- | --- | --- |
| `catalog_policy` | The catalog + policy load and validate via the same loader `check`/`run` use. | **fail** if either does not load. |
| `feature_compatibility` | The binary's enabled cargo features cover the optional unlock slots and backends the config declares. | **fail** on any mismatch; it names the exact missing feature. |
| `backend_binary` | For a `vault`-kind backend, `bao` or `vault` is on `PATH`. | **warn** if neither is found (the daemon talks HTTP and does not strictly need the CLI). |
| `socket` | Parent dir writable, mode not world-writable, `socket-group` resolves to a gid; the socket is **not** bound. | **fail** on a bad parent or group; **warn** on a world-writable mode. |
| `bundle_readable` | The sealed bundle exists at the configured path and is readable. | **fail** if absent/unreadable. |
| `bundle_perms` | The sealed bundle is strict `0600` (owner-only). | **fail** on any broader mode. |
| `bundle_freshness` | The bundle's epoch is not behind the `.epoch` sidecar (anti-rollback). | **fail** if the epoch is behind or corrupt; **warn** if the sidecar is absent (first boot). |
| `backend_reachability` | Each distinct `vault` address answers an unauthenticated `GET /v1/sys/health` within ~3s. | **fail** on any unreachable address (it never hangs the run). |
| `key_material` | `--check-keys` only: probes every catalog key read-only, like startup reconcile; no writes. | **fail** on an absent required key or probe error; **warn** on absent optional keys. |

`feature_compatibility` checks the unlock-slot features (`unlock-bip39`, `unlock-age-yubikey`) and the
backend features (`keystore-backend`, `aws-kms`, `gcp-kms`), naming any the binary lacks. A normal
default build includes 1Password, BIP39, and `age`/YubiKey support; this check matters most for
`--no-default-features`, cloud KMS, and other custom builds.

## Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | No `fail` check. Advisory `warn`s alone still exit `0`. |
| `1` | At least one **blocking** (`fail`) check: a misconfiguration that would prevent (or endanger) a clean start. |

## JSON schema (`--json`)

The document is **versioned and stable**. Operators script against the field names and the `status`
tokens.

```json
{
  "schema_version": 1,
  "checks": [
    { "name": "backend_reachability", "status": "fail",
      "detail": "1 of 1 vault backend address(es) unreachable: http://127.0.0.1:8200",
      "remediation": "Start/reach the backend (OpenBao/Vault) at the configured address, or fix `addr` …" }
  ],
  "summary": { "total": 8, "ok": 6, "warn": 0, "fail": 2, "blocking": true }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | uint | Document schema version (currently `1`). |
| `checks[]` | array | One object per check, in a deterministic order. |
| `checks[].name` | string | Stable machine identifier (e.g. `backend_reachability`). |
| `checks[].status` | string | `ok` / `warn` / `fail`. |
| `checks[].detail` | string | Human-readable finding (no secret bytes). |
| `checks[].remediation` | string | Actionable fix for a non-`ok` result (empty for `ok`). |
| `summary.total` / `ok` / `warn` / `fail` | uint | Per-status counts. |
| `summary.blocking` | bool | `true` iff any check is `fail`: the run exits `1`. |

{% best() %}
Run `basil doctor` on every node as a pre-start gate (e.g. a systemd `ExecStartPre=` or a first-boot
provisioning step) so a missing run dir, a wrong bundle mode, an unreachable backend, or a
feature-mismatched binary is caught *before* the daemon tries to unlock and bind. Scrape the `--json`
document if you orchestrate fleets: assert `summary.blocking == false`, or alert on any
`checks[].status == "fail"`. Add `--check-keys` when the pre-start environment has access to the same
unlock material as the daemon. Pair it with [policy explain](/operations/policy-explain/) for full
pre-deploy coverage.
{% end %}

## Where to go next

- [Capability policy & reconcile](/configuration/capability-and-reconcile/): what a clean start checks.
- [Health & readiness probes](/operations/health-and-readiness/): the *running* equivalents.
- [Policy explain / dry-run](/operations/policy-explain/): preview authorization outcomes.
