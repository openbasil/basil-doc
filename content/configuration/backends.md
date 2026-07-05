+++
title = "Backends & capabilities"
weight = 40
+++

# Backends & capabilities

A backend declares what it *provides* (engines, capabilities, and mintable transit key types, usually
from a version preset); Basil derives what the catalog *requires* and enforces **`required ⊆
provided`**. There are two backend kinds.

## Backend kinds

| Kind | Backends | Custody | Engines / notes |
| --- | --- | --- | --- |
| `vault` | OpenBao · HashiCorp Vault CE | In-place backend crypto | `transit`, `kv2`, `pki`, and Basil's `nats` capability (see below) |
| `aws-kms` / `gcp-kms` | AWS KMS · GCP Cloud KMS | In-place cloud KMS crypto | Provider-held signing and AEAD keys; Basil brokers operations without receiving private key bytes. |
| `keystore` | `db-keystore` (turso, encrypted SQLite on disk) · `1password` | Materialize-to-use | Key **store** only, no in-place engine; for smaller / low-memory deployments |

The `vault` kind is the default strong-custody path: private-key operations happen inside the backend
and key bytes never cross the socket. It exposes `transit` (sign/encrypt in place), `kv2` (stored
values), and `pki` (X.509 leaf issuance), plus Basil's `nats` capability (NATS identity minting and
`ed25519-nkey` JWT signing over in-place NKey custody). The `keystore` kind targets smaller or
low-memory deployments
where a full transit backend isn't warranted. Because those backends only *store* keys, every
private operation is **materialize-to-use**: Basil validates the caller (kernel attestation) and the
authorization (catalog policy), fetches the key briefly to perform the one operation, then zeroes it.
See [Backends & custody](/introduction/backends-and-custody/) for the custody tradeoff in full.

## Build inclusion

The default `basil-bin` build includes the common local and Vault-compatible paths. Cloud KMS and the
embedded db-keystore backend are opt-in to keep default builds smaller.

| Backend | Build inclusion |
| --- | --- |
| OpenBao / HashiCorp Vault CE (`vault`) | Always included. |
| 1Password (`keystore` with `1password`) | Included in the default build. |
| db-keystore (`keystore` with `db-keystore`) | Requires `--features db-keystore`. |
| AWS KMS (`aws-kms`) | Requires `--features aws-kms`. |
| Google Cloud KMS (`gcp-kms`) | Requires `--features gcp-kms`. |

{% note(title="HashiCorp Vault Enterprise") %}
Basil speaks the Vault wire API and is tested against OpenBao and HashiCorp Vault CE.
HashiCorp Vault Enterprise is untested: <span class="pill gap">roadmap</span>.
{% end %}

## Authenticating to the backend

The bundle carries the backend credential. For the `vault` kind there are three credential types:

| Credential | Use |
| --- | --- |
| `VaultToken` | A static token. Simplest; for dev or tightly controlled automation. |
| `VaultAppRole` | A `role_id` + `secret_id` exchanged for a short-lived token. The standard production choice. |
| `SpiffeSigner` | The broker self-mints a JWT-SVID and exchanges it at `auth/<mount>/login`, with no static backend secret at all. |

The cloud KMS kinds use ambient provider identity by default. `GcpKms` can also seal a whole
service-account JSON key in the bundle when ambient credentials are not available.

The `keystore` kind doesn't authenticate to a transit server; instead the bundle seals the backend's
own config: `DbKeystoreDek` (the db-keystore database encryption key) or `OnePassword` (provider URI,
project, and profile). See [Unlock & the sealed bundle](/configuration/unlock-and-bundle/).

For `SpiffeSigner`, set config keys `jwt-auth-mount` (default `jwt`), `jwt-role` (**required**, no
default, fails closed if empty), `jwt-audience` (default `openbao`), and `svid-ttl-secs` (default 300).
The same TTL also controls how often Workload API X.509-SVID streams reissue fresh leaf material.

{% tip() %}
`SpiffeSigner` is the credential with the least to steal: there's no long-lived backend secret on disk,
just a signing key that mints short-lived logins on demand. If you've already stood up SPIFFE, this
is the tidiest way to authenticate the broker itself.
{% end %}

## Where to go next

- Backend how-tos: [OpenBao & Vault](/configuration/backend-openbao-vault/),
  [AWS KMS](/configuration/backend-aws-kms/), [Google Cloud KMS](/configuration/backend-gcp-kms/),
  [1Password](/configuration/backend-1password/): zero-to-working setup with least-privilege policies.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): where the backend credential lives.
- [Capability policy & reconcile](/configuration/capability-and-reconcile/): `required ⊆ provided` at startup.
- [Backends & custody](/introduction/backends-and-custody/): engines and the materialize-to-use exception.
