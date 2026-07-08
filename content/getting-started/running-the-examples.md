+++
title = "Running the examples"
weight = 45
+++

# Running the examples

The Basil repo ships runnable examples in two places: Rust examples under `examples/` and Go
examples under `clients/go/examples/`. Each one is self-contained: a `run.sh` boots a throwaway
OpenBao/Vault dev backend, provisions a catalog, policy, and sealed bundle, starts `basil agent`,
drives the scenario through the client or CLI, and prints `PASS`. Every script exits non-zero on
failure, so they double as smoke tests.

## Prerequisites

- OpenBao (`bao`) or HashiCorp Vault (`vault`) on your `PATH`. Every script resolves
  `bao` first, then falls back to `vault`.
- `cargo` (Rust 1.96) to build the broker, or a prebuilt binary via `BASIL_BIN=/path/to/basil`.
- `nats-server` on your `PATH` for the NATS examples.
- `go` for the Go examples.

Run any example directly (`examples/artifact-signing/run.sh`), or run every Rust example that
ships a `run.sh` in one command from the repo root:

```sh
just run-examples
```

## Rust examples

Each lives in its own crate under `examples/` with a `README.md` for the full walkthrough.

- **`artifact-signing`**: signs and verifies a release manifest with a transit-backed Ed25519 key
  that never leaves the vault, checks tamper rejection locally with `ed25519-dalek`, and proves
  the policy gate by expecting `PermissionDenied` on an ungranted key.
- **`stream-file-encryption`**: encrypts a multi-chunk file with `basil::stream`, where Basil owns
  every nonce. Covers an `AES-256-GCM` round-trip, an ML-KEM-768 pass with the content key wrapped
  to a broker-custodied key, and a fail-closed tamper check. Needs a `pqc`-built binary; the
  script builds one.
- **`cose-nats-telemetry`**: two services exchange signed `COSE_Sign1` telemetry over NATS using
  only Basil-minted leases: a minted operator/account/user JWT chain, in-place NKey nonce signing
  at connect, and in-place telemetry signatures verified (and tamper-rejected) by the subscriber.
  Needs `nats-server`.
- **`cose-nats-demo`**: Alice and Bob exchange sealed COSE invocations over NATS through
  `basil-nats-bridge`: signed with each party's transit-backed key, opened with a custodied X25519
  key, and answered with a sealed reply. Needs `nats-server`.
- **`db-keystore`**: runs the broker against the optional embedded `db-keystore` backend and
  drives the CLI to mint a JWT, encrypt/decrypt, and sign/verify. The materialize-to-use custody
  path; see the [db-keystore walkthrough](/examples/db-keystore/).
- **`nix`**: a self-contained catalog + policy + NixOS module + foreground runner to copy and
  edit. No `run.sh`; see [Make it your own](/getting-started/make-it-your-own/).

There is also a cargo example, `stream_cli` in the `basil` client crate, used by
`just test-stream-interop` to prove the streaming container format is byte-identical between Rust
and Go. It needs no broker or backend.

## Go examples

Each lives under `clients/go/examples/` and follows the same `run.sh` pattern.

- **`secrets-and-aead`**: the KV and AEAD data plane from Go: `SetSecret`/`GetSecret`/
  `RotateSecret` version a KV-v2 secret, `Encrypt`/`Decrypt` use a broker-owned `AES-256-GCM` key
  where Basil owns the nonce, and a mismatched-AAD decrypt fails closed.
- **`stream-file-encryption`**: the Go mirror of the Rust streaming example via the `stream`
  package: chunked `AES-256-GCM`, ML-KEM-768 with the content key recovered through the broker,
  and a tamper check. The container is wire-identical to `basil::stream`.
- **`cose-nats-telemetry`**: the Go mirror of the Rust telemetry example: minted NATS JWT chain,
  in-place NKey nonce signing, and broker-backed `COSE_Sign1` signatures via `veraison/go-cose`.
  Needs `nats-server`.
- **`nats-cose-courier`**: an interop courier that builds a sealed-invocation request, sends it to
  `basil-nats-bridge` over NATS, and opens the sealed response. No `run.sh`; it is driven by a
  harness that supplies the NATS URL and recipient keys via environment variables.

The Go client also ships `cmd/basil-sign`, a minimal runnable command that connects to a broker
socket, signs a message, verifies it, and prints the public key:

```sh
cd clients/go
go run ./cmd/basil-sign -socket /tmp/basil.sock -key web.tls.signing_key -message hello
```

{% tip(title="Testing a prebuilt binary") %}
Every `run.sh` honors `BASIL_BIN` (and the bridge demo honors `BASIL_NATS_BRIDGE_BIN`), so you can
point the examples at release binaries instead of a fresh `cargo build`. The bridge demo also
strips `VAULT_TOKEN` from the broker and bridge environments, so it exercises the sealed-bundle
credential path, not an ambient token.
{% end %}

## Where to go next

- [Quickstart](/getting-started/quickstart/): the throwaway dev fixture, end to end.
- [db-keystore backend example](/examples/db-keystore/): the materialize-to-use walkthrough.
- [Go client](/clients/go/) and [Rust client](/clients/rust/): the libraries the examples drive.
- [Streaming encryption](/clients/stream/): the container format two of the examples exercise.
