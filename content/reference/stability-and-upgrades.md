+++
title = "Stability & upgrades"
weight = 50
+++

# Stability & upgrades

Basil is **pre-1.0** (currently 0.7.x) and under active development. This page says plainly what
that means for adopting it: which surfaces you can script against today, which can still change
between minor versions, and how to upgrade a running broker safely.

## What pre-1.0 means here

The wire protocol and config formats can still change between minor versions. Every breaking
change is called out explicitly in the
[CHANGELOG](https://github.com/openbasil/basil/blob/main/CHANGELOG.md); nothing breaks silently in
a patch release. The Rust crates (`basil`, `basil-proto`, `basil-cose`, `basil-nats`) and the Go
module (`basil-go`) version together with the broker, and pre-1.0 the safest posture is to run
clients and broker from the same minor release.

## What is stable today

| Surface | Stability |
| --- | --- |
| Catalog & policy files | Versioned (`schemaVersion`); parsing fails closed on unknown fields, so a file written for a newer schema is rejected rather than half-read. |
| `basil doctor --json` | Versioned and stable (`schema_version`, currently `2`); safe to script against. |
| Streaming container format | Specified normatively in the repo (`docs/specs/streaming-encryption-format.md`); the Rust and Go implementations are wire-identical. |
| gRPC proto (`basil-proto`) | Can still change between minor versions; enums are not yet frozen. |
| Sealed bundle | No cross-version format guarantee is documented yet. Recreating a bundle with `basil bundle create` is cheap; treat that as the migration path if a release notes a bundle change. |

The standards Basil implements are targets, not a frozen contract: see
[RFC compatibility](/reference/rfc-compatibility/).

## Upgrading a running broker

[Hot reload](/operations/hot-reload/) covers catalog/policy changes; a **binary upgrade is a
restart**. The safe sequence:

```sh
# 1. read the CHANGELOG for the releases you are crossing
# 2. preflight the NEW binary against the CURRENT config
/path/to/new/basil doctor -c /etc/basil/agent.toml
# 3. confirm the bundle still opens (non-destructive)
/path/to/new/basil bundle verify /var/lib/basil/bundle.sealed --open <slot>
# 4. swap the binary, restart the unit, confirm readiness
basil ready
```

Doctor's `feature_compatibility` check catches an upgrade footgun early: a new binary built
without a cargo feature your config depends on (a cloud KMS backend, an unlock slot) fails the
preflight by name instead of failing the unlock at restart. State on disk (the bundle, the epoch
sidecar, audit logs) is left in place by an upgrade; only the binary changes.

Because Basil is a single-host broker, there is no fleet-wide coordination to sequence: upgrade
host by host, and let each host's [readiness probe](/operations/health-and-readiness/) gate its
return to service.

## Breaking changes so far

The CHANGELOG is authoritative; the pattern so far, as a calibration for what "pre-1.0" has meant
in practice:

- **0.7.0**: `MintJwt` extra claims moved to raw JSON bytes (`extra_claims_json`); the Rust
  client's sealed-invocation mint surface changed; decoders and verifiers got stricter
  (deterministic CBOR, ES256 high-S rejection, `AEAD_ALGORITHM_UNSPECIFIED` rejected on decrypt).
- **0.6.1**: the Rust client crate was renamed from `basil-client` to `basil`.
- **0.6.0**: the `basil config` CLI namespace was flattened (`basil config check` became
  `basil doctor`, `basil config init` became `basil init`), and `basil_nats::seal_nats_curve` now
  takes an explicit `rng` parameter.

Most breaking changes have been client-API and CLI shape changes, plus validators getting
stricter. None so far has required re-provisioning keys: key material lives in the backend and is
untouched by a broker upgrade.

## Where to go next

- [Hot reload & admin reload](/operations/hot-reload/): what changes without a restart, and the
  routing-shape guard.
- [Doctor (preflight checks)](/operations/doctor/): the pre-restart gate.
- [Backup & disaster recovery](/operations/backup-and-recovery/): protect the bundle before you
  touch the host.
- [Feature matrix](/reference/feature-matrix/): the implemented/roadmap split.
