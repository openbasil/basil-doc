+++
title = "Backends & custody"
weight = 30
+++

# Backends & custody

Basil's job is to broker operations without handing out keys. *How* a key is held depends on the
backend. There are two custody models, and Basil makes the tradeoff explicit.

## In-place custody (the default and strongest model)

The primary backend kind is **`vault`**: a Vault-compatible engine ([OpenBao](https://openbao.org)
or HashiCorp Vault CE) over the same wire API. (HashiCorp Vault Enterprise is untested,
<span class="pill gap">roadmap</span>.) It exposes these engines:

| Engine | Role |
| --- | --- |
| `transit` | Sign / encrypt / decrypt **in place**: the key never leaves the backend. |
| `kv2` | Stored values (KV-v2). |
| `pki` | X.509 leaf certificate issuance; the issuing CA stays in place. |
| `nats` | A transit engine for NATS **NKeys** that also mints NATS identities (operator, account, user, signer, server, curve) and signs their `ed25519-nkey` JWTs, all in place. |

{% note(title="`nats` logical engine") %}
`nats` is a logical engine combining NATS-related API services:

- It is a **transit engine for NATS NKeys**: an NKey is an Ed25519 key, and Basil signs with it
  *in place*, so the seed never leaves the backend.
- It **mints NATS identities**: operator, account, user, signer, server, or curve.
- It **signs and validates NATS JWTs** in the `ed25519-nkey` profile, and encrypts/decrypts NATS
  curve `xkv1` boxes through custodied xkeys.

Those capabilities are grouped in `NatsService`. In the catalog, declare a signing key as
`keyType: ed25519-nkey` on `transit` with a `nats_type` label: `nats` is the capability name, not an
`engine:` value. See [NATS integration](/clients/nats/) and [the catalog](/configuration/catalog/).
{% end %}

With in-place custody, private-key operations happen *inside* the backend. Basil sends the message to
sign or the ciphertext to decrypt; the backend does the math and returns the result. The key bytes
never enter Basil's process and never cross the socket. This is the custody model to prefer wherever
it fits.

## Materialize-to-use custody (the sanctioned exception)

Some algorithms a transit backend simply can't run in place. For those, Basil uses
**materialize-to-use** custody (design §17.7): it materializes the private key in-process for
exactly one operation, then zeroizes it. The public half is provisioned out of band so public
operations never touch the private.

This applies to:

- **X25519 / ML-KEM unseal** (sealing keys), and
- **Ed25519 signing on a plain value store** (`engine: kv2`).

{% caution(title="Materialize-to-use is an explicit, narrow choice") %}
Materialize-to-use means key bytes briefly exist in Basil's memory, for exactly one operation, then
are zeroized. These two arms (X25519/ML-KEM unseal and `engine: kv2` Ed25519 signing) are core code
in every build. Whenever in-place custody is available, prefer it.
{% end %}

The end-to-end materialization path is **`Zeroizing`** from the backend read through to the wipe, so
no un-zeroized copy of a private key lingers in a response buffer, a parsed JSON value, or a decoded
byte vector.

## Key-store backends

For smaller or low-memory deployments where a full transit backend isn't warranted, Basil can be
built with key-store backends. Both use catalog backend kind `keystore`, live behind
`basil-keystore-backend`, and are materialize-to-use. 1Password is enabled in the default binary;
`db-keystore` is opt-in.

| Backend | Build status | Custody |
| --- | --- | --- |
| **`db-keystore`** | `db-keystore` | Keys in an embedded encrypted SQLite-compatible database (turso), on local disk. The database encryption key is sealed in the bundle as `DbKeystoreDek`. |
| **`1password`** | default | Keys stored/fetched through a 1Password provider. Provider config is sealed in the bundle as `OnePassword`. |

Because these are key stores rather than transit engines, the operation is materialize-to-use:
Basil validates the caller (kernel attestation) and the authorization (catalog policy), fetches the
key briefly to perform the one operation, then zeroes it. A custom build that disables the keystore
features will fail closed if the catalog still declares a `keystore` backend.

## What Basil will and won't generate

Reconcile (the startup check) can generate these in place when a catalog key is marked
`missing: generate`: Ed25519, Ed25519-NKey, RSA-2048, ECDSA P-256, ECDSA P-384, ECDSA P-521,
AES-256-GCM, ChaCha20-Poly1305.

It will **not** generate X25519/ML-KEM sealing keys or value-store Ed25519 seeds: those are
provisioned out of band or imported. Basil refuses rather than silently minting authority with an
in-broker key it shouldn't own.

## Backend roadmap

AWS KMS and Google Cloud KMS are implemented as in-place transit backends. Azure Key Vault,
PKCS#11/HSM, native AWS Secrets Manager / Google Cloud Secret Manager value backends, and native
HashiCorp Vault Enterprise integration are <span class="pill gap">roadmap</span>. See the
[feature matrix](/reference/feature-matrix/) for the full list.

## Where to go next

- [Backends & capabilities](/configuration/backends/): declaring backends and authenticating to them.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): how the backend credential is held.
- [db-keystore example](/examples/db-keystore/): a runnable materialize-to-use walkthrough.
