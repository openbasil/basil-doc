+++
title = "1Password"
weight = 48
+++

# 1Password

You already run 1Password, and you would rather keep a handful of Basil secrets in a vault your team
governs than stand up a second store for them. Basil can treat a **1Password** vault as a `keystore`
backend: a place it reads secrets from at the moment of use. This page sets that up end to end, from
the 1Password side to the Basil catalog and sealed bundle.

Be clear about custody first, because it is the whole reason to choose a backend. 1Password is a
**value store**, not an in-place crypto engine. Where a `vault` transit backend signs and encrypts
*inside* the backend so key bytes never cross the wire, 1Password only hands back a stored string.
So the `keystore` kind is **materialize-to-use**: Basil validates the caller (kernel attestation) and
the authorization (catalog policy), fetches the secret briefly into its own memory, performs the one
operation, then zeroes it. The material is used *in place* from the caller's point of view (Basil
never returns a private half to a client), but it does transit Basil's address space, which a transit
backend avoids. See [Backends & custody](/introduction/backends-and-custody/) for that tradeoff in
full, and [Backends & capabilities](/configuration/backends/) for where the `keystore` kind sits.

{% caution(title="Scope: textual secrets, and a lightly-travelled path") %}
Two honesty notes up front. First, the 1Password backend is **string-only**: it stores each secret as
the text of a Secure Note field, and a write of non-UTF-8 bytes fails closed. That makes it a good fit
for stored *value* secrets (an API token, a connection string, a passphrase) and a poor fit for raw
binary key material such as an Ed25519 seed or an X25519 private half, unless you consistent pass each
write/read through base64 encode/decode. For
materialize-to-use *signing* and *sealing* keys, use [`db-keystore`](/examples/db-keystore/), which
handles binary keys directly.
Second, Basil's 1Password integration is exercised only by offline unit tests (URI parsing,
item addressing); a live end-to-end run needs an authenticated `op` CLI and a real vault, which the
test lane does not provide. Treat the live path as **untested** and validate it in a staging vault
before you depend on it.
{% end %}

## What Basil actually talks to

Basil does not use 1Password Connect or the REST API. It shells out to the **1Password CLI** (`op`)
as a child process and parses `op item ... --format json`. That has one consequence worth internalising
before you provision anything: the machine running `basil agent` must have `op` on its `PATH` (or you
point Basil at it with the `BASIL_OP_CLI_PATH` environment variable), and `op` must be able to
authenticate non-interactively.

For a long-running server, non-interactive means a **service account**. When Basil's provider URI
carries a token, Basil sets `OP_SERVICE_ACCOUNT_TOKEN` in the child `op` environment for you;
otherwise `op` inherits whatever token is already in the broker's environment. Either way the
authenticating identity is a 1Password service account, and every grant below is a grant *to that
account*.

{% note() %}
Do not confuse the 1Password *backend* (this page, where secrets Basil brokers live in a vault) with
using 1Password to fetch Basil's own *unlock passphrase* (`op read` writing a file that a passphrase
slot reads). The latter is covered under [Automated boot unlock](/operations/automated-boot-unlock/)
and is independent of whether you run this backend.
{% end %}

## Creating the service credential with least privilege

Least privilege is the point of a broker, so build the credential narrowly.

**1. Create a dedicated vault (UI or CLI).** Give Basil its own vault, not a shared one. The service
account token is a bearer credential; if it leaks, its blast radius is exactly the vaults it can reach,
so keep that to one vault that holds only Basil's brokered secrets. In the CLI:

```sh
op vault create "Basil"
```

**2. Decide read-only versus read-write from what Basil will do.** Basil's read operations run
`op item get` and `op item list`; its write operations run `op item create` and `op item edit`.
So the grant follows directly from your catalog:

| If Basil only... | It runs | Grant the service account |
| --- | --- | --- |
| Reads existing secrets (`get`, and any read op) | `op item get`, `op item list` | `read_items` |
| Also creates or updates items (a writable value, `rotate`/`set`) | `op item create`, `op item edit` | `read_items,write_items` |

Reading and writing are separate 1Password permissions, exactly as they are separate Basil ops, so
grant `write_items` only if you actually want Basil to mutate the vault. Most deployments provision the
secrets out of band and give Basil **read-only** access.

**3. Create the service account scoped to that one vault.** The token prints once; capture it into a
`0600` file and never echo it:

```sh
# read-only broker (the common case)
op service-account create "basil-broker" --expires-in 90d --vault "Basil:read_items"

# read-write broker (only if Basil must create or rotate items in the vault)
op service-account create "basil-broker" --expires-in 90d --vault "Basil:read_items,write_items"
```

{% caution(title="Service accounts are immutable and expiring") %}
A 1Password service account cannot be edited after creation: to change its vault permissions or extend
its life you revoke it and create a new one, then re-seal the new token into Basil's bundle. Pick an
`--expires-in` you can rotate on schedule, and treat that rotation as credential rotation for the whole
backend. Exact `op` flags vary by CLI version; confirm against your installed `op --version`.
{% end %}

## Item conventions Basil expects

Basil addresses each secret as a **Secure Note** whose *title* is computed, not free-form. The title
template is:

```text
basil/{project}/{profile}/{key}
```

where `{project}` and `{profile}` are the values you configure for the backend (below), and `{key}` is
the catalog key's `path` (the backend-native locator). So a catalog key with `path` `app/stripe-key`,
under project `prod` and profile `agent`, resolves to an item titled `basil/prod/agent/app/stripe-key`
in the configured vault.

The secret itself lives in a field. On read, Basil prefers the field **labelled `value`**; failing
that it falls back to any Concealed field, or a field whose id is `password`. When Basil *creates* an
item it writes a Secure Note with three string fields (`project`, `key`, `value`) and tags it
`automated` plus the project name.

A worked example: to provision `app.stripe-key` by hand for a read-only broker, create one Secure Note
in the `Basil` vault:

| Item property | Value |
| --- | --- |
| Vault | `Basil` |
| Category | Secure Note |
| Title | `basil/prod/agent/app/stripe-key` |
| Field label | `value` |
| Field contents | the Stripe secret key (text) |

With the `op` CLI, the same item is:

```sh
op item create --vault "Basil" --category "Secure Note" \
  --title "basil/prod/agent/app/stripe-key" \
  "value[text]=sk_live_..."
```

{% note(title="Vault name in the URI is percent-encoded") %}
The vault is named in Basil's provider URI. A vault whose name contains a space, such as `Basil Secrets`,
is written `onepassword://Basil%20Secrets`. A bare `onepassword://localhost` (or no host) leaves the
vault unset and Basil falls back to the `Private` vault, which is almost never what you want on a
server; name the vault explicitly.
{% end %}

## Configuring Basil

### Build status

The 1Password backend is enabled in the default cargo features.

`basil doctor` fails closed if a catalog declares a `keystore` backend but the binary lacks the
feature, so a custom-build mismatch is caught before startup rather than at first use.

### Declare the backend and keys in the catalog

Add a `keystore`-kind backend and route value keys to it. The 1Password addressing lives in the sealed
credential and the agent config, not in the catalog, so the backend's `addr` here is required by the
schema but ignored by the 1Password arm; a short label keeps it readable.

```json
{
  "backends": {
    "op": { "kind": "keystore", "addr": "1password" }
  },
  "keys": {
    "app.stripe-key": {
      "class": "value",
      "backend": "op",
      "engine": "kv2",
      "path": "app/stripe-key",
      "writable": false,
      "missing": "error",
      "description": "Stripe secret key, read in place from 1Password"
    }
  }
}
```

This is a `class: value` key on the `kv2` engine: Basil brokers `get` (and, only if `writable` were
true, `set`/`rotate`). `writable: false` caps writes off entirely, matching a read-only service
account. `missing: "error"` tells reconcile to fail closed if the item is absent rather than trying to
mint one, because Basil cannot generate a value into 1Password for you. See
[The catalog (keys)](/configuration/catalog/) for the full key schema.

{% caution(title="Why the signing and sealing arms are not shown here") %}
The catalog does support materialize-to-use private keys (a `sealing` X25519 key, or an
`asymmetric` key on `engine: kv2`), each carrying a required `publicPath` for its public half. Those
arms are generic across `keystore` backends in the code, but 1Password's string-only storage cannot
hold the raw seed or the raw public bytes (both are non-UTF-8), and the path is untested with `op`. If
you need broker-mediated signing or sealing with local custody, use
[`db-keystore`](/examples/db-keystore/), which stores arbitrary bytes in an encrypted local database.
{% end %}

### Seal the 1Password credential into the bundle

The backend credential lives in the sealed bundle as an `OnePassword` entry carrying the provider URI,
project, and profile. Seal it at bundle-create time alongside your unlock slots. All three fields are
required by the CLI:

```sh
basil bundle create /var/lib/basil/bundle.sealed \
  --slot passphrase:file=/run/secrets/basil-unlock-passphrase \
  --backend id=op,type=1password,provider-uri=onepassword://Basil,project=prod,profile=agent
```

The `id` must match the catalog backend name (`op` above). To inject the service account token, put it
in the provider URI with the `onepassword+token` scheme, so the token travels *inside* the encrypted
bundle rather than sitting in the environment:

```sh
basil bundle create /var/lib/basil/bundle.sealed \
  --slot passphrase:file=/run/secrets/basil-unlock-passphrase \
  --backend id=op,type=1password,provider-uri=onepassword+token://OPS_TOKEN@Basil,project=prod,profile=agent
```

Alternatively, leave the token out of the URI (`onepassword://Basil`) and provide
`OP_SERVICE_ACCOUNT_TOKEN` in the broker's own environment (for example a systemd credential); the
child `op` inherits it. Rotate the backend credential in place with `bundle set-backend`, and see
[Unlock & the sealed bundle](/configuration/unlock-and-bundle/) for deposits and the credential
lifecycle.

The three fields can also be supplied as agent-config defaults, used when a sealed field is left empty:

```toml
onepassword-provider-uri = "onepassword://Basil"
onepassword-project = "prod"
onepassword-profile = "agent"
```

## Verifying

Run the environment preflight before you start the daemon. `doctor` confirms the `keystore` support is
built in and the catalog is coherent without unlocking the bundle or touching the vault:

```sh
basil doctor -c /etc/basil/agent.toml
```

A `keystore`-only catalog has no transit server to reach, so `doctor` skips backend reachability for it;
the live check is that `op` can actually read the item. After the daemon starts, gate traffic on
readiness (a broker can be alive yet not ready if a `missing: error` key is absent):

```sh
basil health          # liveness: the process answers
basil ready           # readiness: required keys resolved
```

See [Doctor (preflight checks)](/operations/doctor/) and
[Health & readiness probes](/operations/health-and-readiness/) for the full check lists and their exit
codes.

## Security caveats

{% caution(title="Read before you depend on this backend") %}
The material Basil brokers here is **materialized into Basil's memory** to be used, then zeroized. That
is a weaker custody position than an in-place `vault`, `aws-kms`, or `gcp-kms` backend, where the
private half never leaves the backend. Choose 1Password for stored value secrets whose exposure you
have already accepted living in a password manager, not for keys that demand hardware or in-place
custody.

The service account token is a standing bearer credential. Anyone who holds it can reach every item in
every vault the account can read, so scope it to a **dedicated vault**, grant `read_items` unless you
have a concrete reason to grant `write_items`, set a short `--expires-in`, and rotate it on a schedule.
Sealing the token into the bundle (the `onepassword+token` scheme) keeps it encrypted at rest instead
of loose in the environment.

Finally, honour the untested caveat from the top of this page: exercise the full path against a staging
vault before production, because the live `op` integration is not covered by Basil's automated tests.
{% end %}

## Where to go next

- [Backends & custody](/introduction/backends-and-custody/): in-place versus materialize-to-use, and why it matters.
- [Backends & capabilities](/configuration/backends/): the `keystore` kind next to `vault` and cloud KMS.
- [db-keystore backend](/examples/db-keystore/): the materialize-to-use path for signing and sealing keys.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): where the `OnePassword` credential lives and how to rotate it.
