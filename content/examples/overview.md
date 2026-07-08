+++
title = "Examples overview"
weight = 10
+++

# Examples overview

The Basil tree ships several examples that exercise the broker through the `basil` CLI and the
client libraries. The ones below are runnable end to end and are the fastest way to *see* the
model rather than read about it. More examples (COSE over NATS, streaming file encryption,
artifact signing, and the Go client) live under `examples/` and `clients/go/examples/` in the
repo; see [Running the examples](/getting-started/running-the-examples/) for the full list and how
to run each one.

## The dev fixture (quickstart)

The quickest way to see Basil work is the dev fixture: one script (`scripts/prefill-test-store.sh`)
boots a throwaway OpenBao/Vault dev backend, writes an example catalog + policy, pre-fills a few keys,
and seals a `0600` bundle, then prints the exact commands to run the broker and drive it. Under five
minutes, no production setup.

It demonstrates the **default in-place custody** path: signing and AEAD encryption where the private
key never leaves the backend.

→ [Quickstart](/getting-started/quickstart/)

## The db-keystore backend example

`examples/db-keystore/` runs the unified `basil` binary against the optional db-keystore backend
and uses the CLI surface to mint a JWT, encrypt/decrypt, and sign/verify. It builds `basil-bin` with
the `db-keystore` feature, generates a sealed bundle holding a `DbKeystoreDek`, starts
`basil agent` on a Unix socket, and drives the broker.

It demonstrates the **materialize-to-use custody** path: an embedded encrypted key store where Basil
materializes key bytes for a single operation, then zeroizes them.

→ [db-keystore backend example](/examples/db-keystore/)

## The COSE over NATS demo

`examples/cose-nats-demo/` starts OpenBao, NATS, `basil agent`, and `basil-nats-bridge`, then sends a
sealed COSE request/reply flow over NATS. It honors `BASIL_BIN` and `BASIL_NATS_BRIDGE_BIN` when you
want to test prebuilt binaries, and it removes `VAULT_TOKEN` from the broker and bridge
environments so the demo exercises the sealed bundle credentials.

## The web service examples (Rust and Go)

`examples/web-service-axum/` is a Rust axum service of about 50 lines that mints short-lived JWTs
through Basil; `clients/go/examples/web-service/` is the same service in Go `net/http`. Both show
the integration answer in miniature: the service connects to `BASIL_SOCKET`, asks for the minted
credential, and holds no key material anywhere.

→ [Your first integrated service](/clients/web-service/)

## The Python gRPC example

`examples/python-grpc/` generates client stubs from the broker protos with plain `grpcio` tooling
and drives the broker over the Unix socket. It is the proof-by-example for every language without
a dedicated client library.

→ [Other languages](/clients/other-languages/)

## The NixOS migration VM

`examples/nixos-vm/` is a before/after NixOS VM pair for the sops-nix migration: a host delivering
a secret with `sops-nix`, then the same host after the move to a Basil catalog key and policy
grant. Rehearse the cutover in a VM before touching a real machine.

→ [Migrating from sops-nix to Basil](/getting-started/sops-nix-to-basil/)

## Make it your own

When you're ready to move past the fixtures, `basil-example.nix` is a self-contained catalog + policy
+ NixOS module + foreground runner you can copy and edit: change the `keys` (the catalog) and the
`subjects` / `rules` (who may do what, resolved from uid/gid evidence).

→ [Make it your own](/getting-started/make-it-your-own/)

## Where to go next

- [Quickstart](/getting-started/quickstart/): boot a throwaway broker in under five minutes.
- [db-keystore backend example](/examples/db-keystore/): the materialize-to-use walkthrough.
- [Running the examples](/getting-started/running-the-examples/): prerequisites and `run.sh` mechanics.
- [Make it your own](/getting-started/make-it-your-own/): copy the catalog + policy and edit it.
