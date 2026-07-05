+++
title = "db-keystore backend"
weight = 20
+++

# db-keystore backend

This example runs the unified `basil` binary against the optional `db-keystore` backend and uses
the same binary as the CLI to mint a JWT, encrypt/decrypt, and sign/verify. It lives at
`examples/db-keystore/` in the Basil tree.

## What it shows

`db-keystore` stores keys in an embedded encrypted SQLite-compatible database (turso). It's a
**materialize-to-use** custody choice: a different, explicit tradeoff from the default in-place
Vault-compatible backend. See [Backends & custody](/introduction/backends-and-custody/).

{% note() %}
The default build does not include `db-keystore`. Basil must be compiled with
`--features db-keystore`, so building the example's `run.sh` needs the Rust toolchain the workspace
pins (Rust 1.96) installed.
{% end %}

## The files

| File                    | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `catalog.template.json` | A small catalog with one `kind: "keystore"` backend. |
| `policy.template.json`  | A policy template rendered for your current uid.     |
| `db-keystore.env`       | Paths and key names used by the runner.              |
| `basil-agent.toml`      | Generated under the workdir by `run.sh`.             |
| `README.md`             | The example's own walkthrough.                       |
| `run.sh`                | The end-to-end driver.                               |

## Running it

Run it from the repository root or from the example directory:

```bash
examples/db-keystore/run.sh
```

The runner:

1. builds `basil-bin` with the `db-keystore` feature (or uses a prebuilt binary when `BASIL_BIN`
   is exported),
2. creates a sealed bundle containing a generated `DbKeystoreDek` with `basil bundle create`,
3. writes a TOML agent config,
4. starts the daemon with `basil agent` on a Unix socket,
5. waits for **startup reconcile** to generate the demo signing and AEAD keys, then
6. exercises the broker through the `basil` CLI (`mint-jwt`, `sign`/`verify`, `encrypt`/`decrypt`).

Runtime files are written under `/tmp/basil-db-keystore-example` by default. Set
`BASIL_EXAMPLE_WORKDIR` before running to use another directory.

## Where to go next

- [Backends & capabilities](/configuration/backends/): how a `keystore`-kind backend is declared.
- [1Password](/configuration/backend-1password/): the other keystore-kind backend, set up end to end.
- [Quickstart](/getting-started/quickstart/): the in-place (Vault-compatible) path for comparison.
