+++
title = "Quickstart"
weight = 10
+++

# Quickstart

The quickest way to see Basil work end to end is the **dev fixture**: one script boots a throwaway
backend, writes an example catalog + policy, pre-fills a few keys, and creates a sealed bundle, then
prints the exact commands to run the broker and drive it. Under five minutes.

{% tip(title="Zero setup: basil demo") %}
No backend CLI handy? `basil demo` runs a guided tour with nothing but the `basil` binary: it
scaffolds a throwaway broker on the built-in keystore backend and drives a scripted
sign → verify → denied read → explain → mint sequence, audit trail included. See
[The five-minute demo](/getting-started/demo/).
{% end %}

## Prerequisites

- A **Vault-compatible backend CLI** on your `PATH`: OpenBao (`bao`) or HashiCorp Vault (`vault`).
- The Basil binary (`basil`). Build it with `cargo build` (Rust 1.96) or from the Nix dev shell. See
  [Installation](/getting-started/installation/).

## 1. Boot a dev backend + example config (one command)

```sh
# Boots a dev `bao` in -dev mode, writes an example catalog/policy, pre-fills
# keys, and seals a 0600 bundle. Prints the run + CLI commands when it finishes.
scripts/prefill-test-store.sh --engine openbao      # or: --engine vault
```

Basil treats OpenBao and HashiCorp Vault as one `vault` backend kind, so either engine works.

## 2. Run the broker

Copy the `basil agent …` invocation the script printed. It wires the generated TOML config, backend
address, and socket. The config points at the catalog, policy, sealed bundle, and generated
passphrase unlock file:

```sh
basil agent \
  --config <printed>/fixtures/basil-agent.toml \
  --vault-addr http://127.0.0.1:8210 \
  --socket /tmp/basil.sock
```

{% tip(title="Sharing the socket with local services") %}
For shared local deployments, configure the socket in the agent TOML instead of a post-start
`chmod`. The socket mode/group only controls which local users can *open* the transport; Basil still
authorizes each RPC from kernel peer credentials and catalog policy.
{% end %}

```toml
socket = "/run/basil/basil.sock"
socket-mode = "0660"
socket-group = "basil-clients"
```

## 3. Drive it

The broker resolves your **kernel-attested uid/gid** to a policy subject, and the example policy grants
the user that ran the script. Talk to the broker over its socket with the `basil` CLI:

```sh
basil --socket /tmp/basil.sock status
# sign a message with a key whose private half never leaves the backend:
basil --socket /tmp/basil.sock sign --key-id web.tls.signing_key 'hello'
# AEAD-encrypt; Basil generates the nonce, so you can't reuse one:
basil --socket /tmp/basil.sock encrypt --key-id app.aead 'backup-bytes'
# mint a short-lived TLS leaf, leaving the issuing CA key in the backend:
basil --socket /tmp/basil.sock issue-cert --key-id web.tls.cert_issuer \
  --common-name svc.example.org --dns-san svc.example.org --ttl-secs 3600
```

That's the whole loop: your shell proved who it was to the kernel, policy said yes, and the
Vault-compatible backend did the crypto in place. No private key ever crossed the socket.

## Where to go next

- [First run: basil init](/getting-started/first-run/): scaffold your own least-privilege
  starter set instead of the throwaway fixture.
- [Make it your own](/getting-started/make-it-your-own/): the self-contained `basil-example.nix`.
- [The policy](/configuration/policy/): how the broker decided your shell was allowed.
- [db-keystore example](/examples/db-keystore/): the embedded materialize-to-use path.
