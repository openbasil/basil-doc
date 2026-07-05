+++
title = "The catalog (keys)"
weight = 20
+++

# The catalog (keys)

The catalog is the inventory: one entry per key, naming what it is and where it lives. Basil routes
every request through it.

| Field | Meaning |
| --- | --- |
| `class` | `asymmetric` · `symmetric` · `value` · `public` · `sealing`. Selects the default op surface. |
| `keyType` | Algorithm. Required for crypto classes; see [Key types](#key-types) below for the accepted values. |
| `backend` | Names a declared backend instance. |
| `engine` | `transit` · `kv2` · `pki`. Inferred from `class` when omitted (crypto→transit, stored→kv2). |
| `path` | Backend-native locator (transit key name / KV path / `pki/issue/<role>`). |
| `publicPath` | KV path holding the public half of a materialize-to-use key. **Required** for `sealing` and `asymmetric`+`engine=kv2`; forbidden elsewhere. |
| `writable` | Catalog-level cap on broker-mediated writes (see [Approvals & change control](/configuration/approvals/)). |
| `missing` | `error` (default) · `warn` · `generate`. What reconcile does if the material is absent. |
| `generate` | Recipe for `value`/`public` material (`ascii-printable`, `base64`, `hex`, `age-x25519`, `self-signed-tls`, `self-signed-tls-pair-of`). |
| `sealingPin` | Optional COSE unseal-context pin for a `sealing` key; narrows what an `op:decrypt` grant authorizes on `UnsealCose` (see below). Forbidden on non-sealing keys. |
| `labels` | Free-form tags; a few are reserved (e.g. `nats_type`, `svid_kind`, `revocation_store`). |
| `description` | Human note. Validated non-empty. |

{% note(title="There is no `engine: nats`; a NATS key is `ed25519-nkey` on `transit`") %}
The docs call NATS minting Basil's [`nats` engine](/introduction/backends-and-custody/), but that's a
**capability name**, not a catalog value: the `engine` field only accepts `transit`/`kv2`/`pki`.
Declare a NATS signing key as `keyType: ed25519-nkey` on `transit` (engine inferred) with a
`nats_type=<role>` label, e.g. `nats_type=A` for an account issuer. Keeping one canonical spelling
avoids a `nats`/`transit` alias the validator would otherwise have to accept both ways.
{% end %}

{% caution(title="What missing=generate can and can't make") %}
Reconcile generates Ed25519, Ed25519-NKey, RSA-2048, ECDSA P-256, ECDSA P-384, ECDSA P-521,
AES-256-GCM, and ChaCha20-Poly1305 in place. It will not generate X25519/ML-KEM sealing keys or
value-store Ed25519 seeds: those are provisioned out of band or imported. Basil refuses rather than
silently minting authority with an in-broker key it shouldn't own.
{% end %}

{% best(title="Split the op surface per key") %}
One key, one job. A signing key shouldn't also be a value you can `get`. Reading and writing are
separate permissions, and `rotate`/`import` are never implied by read. Basil enforces that by class,
so least privilege is the path of least resistance.
{% end %}

## Key types

The `keyType` field names the algorithm. The accepted values, grouped by what they do:

- **Signing (`asymmetric`)**: `ed25519`, `ed25519-nkey` (NATS NKey), `rsa-2048`, `ecdsa-p256`,
  `ecdsa-p384`, `ecdsa-p521`, `ml-dsa-44`, `ml-dsa-65`, and `ml-dsa-87`. The ML-DSA keys are
  software-custodied signing keys: their private seed is materialized in-process, gated by
  `op:use_software_custody`).
- **AEAD (`symmetric`)**: `aes-256-gcm`, `chacha20-poly1305`.
- **KEM recipient (`sealing`)**: `x25519`, `ml-kem-512`, `ml-kem-768`, and `ml-kem-1024`.

## Pinning the unseal context of a sealing key

A `sealing` key can be opened through the broker with `AeadService.UnsealCose`, gated by `op:decrypt`
on the key. Without a further constraint, that one grant is a decrypt oracle for *any* `COSE_Encrypt`
addressed to the key. A `sealingPin` narrows it to envelopes bound to a specific protocol context, so
the grant stays least-privilege:

```json
{
  "keys": {
    "peer.inbox": {
      "class": "sealing",
      "keyType": "x25519",
      "backend": "bao",
      "engine": "kv2",
      "path": "secret/data/peer/inbox/private",
      "publicPath": "secret/data/peer/inbox/public",
      "missing": "error",
      "description": "peer seal-only inbox",
      "sealingPin": {
        "parties": { "partyU": "content.publisher", "partyV": "basil://prod/agent-a" },
        "externalAad": ["v1"]
      }
    }
  }
}
```

| Facet | Meaning |
| --- | --- |
| `parties` | Pins the COSE KDF `partyU`/`partyV` identities. An envelope's KDF parties must exactly equal both slots. Omit a slot's field to pin the nil (anonymous) slot; never use an empty string. |
| `externalAad` | Allowed encryption-layer `external_aad` values. The caller-supplied `external_aad` must byte-match one entry. A single `""` entry pins the empty-AAD default. |

Both facets are optional, but a pin must set at least one. The loader rejects an all-empty pin, an
empty party-identity string, and any `sealingPin` on a non-sealing key. If the pin is absent, behavior
is unchanged: any envelope addressed to the key can be opened. A mismatch fails closed with
`PermissionDenied`, and the `externalAad` facet is checked *before* the private key is materialized, so
a refused unseal never touches key material.

## Where to go next

- [Capability policy & reconcile](/configuration/capability-and-reconcile/): what `missing` drives at startup.
- [Backends & capabilities](/configuration/backends/): the engines a key can live in.
- [Backends & custody](/introduction/backends-and-custody/): in-place vs. materialize-to-use, and `publicPath`.
