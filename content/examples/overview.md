+++
title = "Examples overview"
weight = 10
+++

# Examples overview

The Basil tree ships several examples that exercise the broker through the `basil` CLI. The two
below are runnable end to end and are the fastest way to *see* the model rather than read about it.
More examples (COSE over NATS, streaming file encryption, artifact signing, and the Go client) live
under `examples/` and `clients/go/examples/` in the repo.

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

## Make it your own

When you're ready to move past the fixtures, `basil-example.nix` is a self-contained catalog + policy
+ NixOS module + foreground runner you can copy and edit: change the `keys` (the catalog) and the
`subjects` / `rules` (who may do what, resolved from uid/gid evidence).

→ [Make it your own](/getting-started/make-it-your-own/)

## Where to go next

- [Quickstart](/getting-started/quickstart/): boot a throwaway broker in under five minutes.
- [db-keystore backend example](/examples/db-keystore/): the materialize-to-use walkthrough.
- [Make it your own](/getting-started/make-it-your-own/): copy the catalog + policy and edit it.
