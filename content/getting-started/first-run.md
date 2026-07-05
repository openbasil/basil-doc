+++
title = "First run: basil config init"
weight = 30
+++

# First run: `basil config init`

Starting from nothing? `basil config init` scaffolds a minimal, valid, **least-privilege** starter set
into a target directory so you don't hand-author JSON/TOML from scratch. It writes **configuration
only**: never secret material, and **not** the sealed bundle (which needs interactive unlock
material). It prints the bundle command shape for your chosen unlock method instead.

```sh
# OpenBao + a BIP39 break-glass slot, scaffolded under ./basil
basil config init --backend openbao --unlock bip39 --dir ./basil
```

## What it writes

Into the target dir (refusing to overwrite an existing file unless `--force`):

- **`catalog.json`** holds one working example `example.signing_key`: an Ed25519 signing key with
  `missing: generate`, so the broker's startup reconcile creates it in place on the first run.
- **`policy.json`** grants only the uid that ran `init` a narrow signer role
  (`sign` / `verify` / `get_public_key`) over only that one key. Everything else is default-deny.
- **`basil-agent.toml`** is a commented config pointing at the catalog/policy/bundle/socket paths, with
  socket mode `0600` (owner-only) by default and the placeholders you must fill clearly marked.

| Flag | Meaning | Default |
| --- | --- | --- |
| `--backend` | `openbao` \| `vault` \| `keystore`: picks the backend kind and starter config. | `openbao` |
| `--unlock` | `bip39` \| `passphrase` \| `tpm` \| `age-yubikey`: which `bundle create` slot the next steps print (init never seals); `bip39` and `age-yubikey` are in default builds, while `tpm` needs an `unlock-tpm` build. | `bip39` |
| `--dir` | Target directory (created if absent). | `./basil` |
| `--addr` | Backend HTTP URL (vault/openbao only). | `http://127.0.0.1:8200` |
| `--transit-mount` | Transit mount the example key lives under (vault/openbao only). | `transit` |
| `--passphrase-file` | Existing `0600` passphrase file to bake into the config and the printed `bundle create` command. Only valid with `--unlock passphrase` (see below). | placeholder |
| `--force` | Overwrite existing target files (otherwise init refuses and names them). | off |

The catalog/policy are produced by serializing the real schema types, so the output is valid by
construction and passes the same loader `check`/`run` use (init re-validates the pair before writing).

## The full new-user flow

1. **Scaffold:** `basil config init --backend openbao --unlock bip39 --dir ./basil`.
2. **Fill inputs & create the bundle** (init prints the exact command). For OpenBao with a BIP39 slot
   and a dev token:

   ```sh
   printf '%s\n' '<backend-token>' > ./basil/backend-token
   chmod 600 ./basil/backend-token
   basil bundle create ./basil/bundle.sealed \
       --slot bip39 \
       --backend id=primary,type=openbao,addr=http://127.0.0.1:8200,token-file=./basil/backend-token
   ```

   Point `bip39-phrase-file` in the TOML at a `0600` file holding the 24-word phrase init showed once.
   (For a dev backend: `bao secrets enable transit`, then reconcile creates `example.signing_key`
   on first run.)
3. **Validate:** `basil config check -c ./basil/basil-agent.toml`.
4. **Run:** `basil agent -c ./basil/basil-agent.toml`.
5. **Exercise:** `basil --socket ./basil/basil.sock sign --key-id example.signing_key 'hello basil'`.

This whole chain (`init` → `bundle create` → `check` → `run` → sign with the scaffolded
`example.signing_key`) is covered end to end against a live dev OpenBao and Vault, so the starter
set is proven usable, not just loadable.

For unattended startup, choose `--unlock passphrase`. By default `init` writes an
`unlock-passphrase-file` placeholder into the config and prints a matching
`basil bundle create --slot passphrase:file=…` placeholder. Both need a hand-edit before
`check`/`run` will work.
Add `--passphrase-file <PATH>` (only valid with `--unlock passphrase`) to bake an existing `0600`
passphrase file into both the generated `unlock-passphrase-file` line *and* the printed
`basil bundle create` shape, so the passphrase starter set is runnable with no hand-edit.

{% note() %}
The `keystore` backend scaffolds a local db-keystore (no external server) and emits a
`db-keystore-cipher` config line; build the agent with `--features db-keystore` to run it. The
`age-yubikey` unlock has no generated slot secret, so the printed command falls back to a BIP39
break-glass slot, and the hardware slot is enrolled out of band.
{% end %}

## Where to go next

- [OpenBao & Vault](/configuration/backend-openbao-vault/): the full backend setup this first run assumes.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): the credential the bundle holds.
- [The catalog](/configuration/catalog/) and [the policy](/configuration/policy/): what `init` scaffolds.
- [CLI command reference](/cli/command-reference/): every subcommand.
