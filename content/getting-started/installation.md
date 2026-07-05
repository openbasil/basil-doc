+++
title = "Installation"
weight = 20
+++

# Installation

Basil is two things on disk: the **`basil` binary** (the broker daemon *and* the CLI: one binary,
several subcommands) and a **Vault-compatible backend** it talks to.

## Prerequisites

- A **Vault-compatible backend CLI** on your `PATH`: OpenBao (`bao`) or HashiCorp Vault (`vault`).
  Basil treats both as one `vault` backend kind, so either works. The daemon speaks the HTTP API; the
  CLI is needed for out-of-band provisioning and the dev fixture.
- **Rust 1.96** (edition 2024), the toolchain the repo pins in `rust-toolchain.toml`, to build from
  source, or the project's Nix dev shell. (Individual crates declare lower MSRVs, 1.85 or 1.88, but
  the workspace builds against the pinned 1.96.)

## Build the binary

```sh
# from a checkout of the Basil repo
cargo build --release
# the binary lands at target/release/basil
```

Or build from the Nix dev shell, which pins the toolchain and every system dependency for a
reproducible build (`flake.lock` pins those inputs).

## Man pages and Debian package

The source tree can generate roff man pages for `basil`, `basil-nats-bridge`, and their subcommands.
Use the `just` recipe for the default output directory, or call the `cargo xtask` alias directly when
packaging:

```sh
just man-pages
just man-pages dist/man
cargo xtask -o dist/man
```

`just man-pages` writes `target/man/*.1` by default. The generated pages are named per command, such
as `basil.1`, `basil-agent.1`, and `basil-nats-bridge.1`.

On Linux, the flake also exposes a Nix-native Debian package:

```sh
nix build .#basil-deb
dpkg-deb --contents result/*.deb
```

The package installs the binaries under `/usr/bin` and gzipped man pages under
`/usr/share/man/man1`. It is assembled from Nix-store binaries, so the runtime linker paths still
point at the Nix store. Use it for Nix-based hosts or controlled internal distribution unless you
have checked that the target host has the required store paths.

## Build defaults and opt-in features

The default `basil-bin` build talks to OpenBao/Vault, includes SPIFFE and PQC support, and enables
the 1Password backend plus the `age`/YubiKey and BIP39 unlock slots. Some integrations stay opt-in
because they add a network listener, cloud SDKs, hardware-specific code, or telemetry dependencies:

| Capability | Build with | Notes |
| --- | --- | --- |
| JWKS HTTP listener | `--features http` | Required for `[jwks] enable = true`; no HTTP port opens unless the config opts in. |
| JWKS native TLS | `--features http-tls` | Also enables `http`; use a reverse proxy instead if you prefer. |
| `db-keystore` | `--features db-keystore` | Embedded encrypted SQLite-compatible store (turso). |
| AWS KMS | `--features aws-kms` | In-place cloud KMS backend; pulls in the AWS SDK. |
| Google Cloud KMS | `--features gcp-kms` | In-place cloud KMS backend; pulls in the Google Cloud KMS SDK. |
| TPM unlock | `--features unlock-tpm` | TPM 2.0 sealed-bundle unlock slot. |
| OTLP / OpenTelemetry logs | `--features otlp` | Enables the `[logging.opentelemetry]` sink. |

The 1Password and `db-keystore` backends are **materialize-to-use** custody choices. See
[Backends & custody](/introduction/backends-and-custody/). The
[db-keystore example](/examples/db-keystore/) builds and drives one end to end.

## Verify your environment

Before starting the daemon, `basil doctor` checks that the environment is wired up: backend binary
and reachability, socket sanity, bundle readability/permissions/freshness, catalog/policy validity,
and that the binary's cargo features match what the config asks for. See [Doctor](/operations/doctor/).

```sh
basil doctor -c /etc/basil/agent.toml
```

## Running the tests

Default package checks run offline tests only. Integration tests that boot live OpenBao/Vault dev
servers are gated behind the `basil-tests/live-e2e` feature so downstream package builds don't need
`bao` or `vault` on `PATH`. Run the live suite explicitly when those engine CLIs are available:

```sh
just cargo-live-e2e
```

## Where to go next

- [Quickstart](/getting-started/quickstart/): the throwaway dev fixture, end to end.
- [First run: basil config init](/getting-started/first-run/): scaffold a real least-privilege config.
