+++
title = "Crypto: keys & algorithms"
weight = 5
+++

# Crypto: keys & algorithms

This page is the catalog of *what* Basil can do cryptographically (the key types, algorithms, and
identity formats it brokers) and *how* each one is custodied. Every operation here runs under the
same two gates: the kernel attests the caller and the catalog policy authorizes the
`(subject, op, key)` before any key is touched. The key itself is either used **in place** (the backend
does the math) or, for the materialize-to-use exception, fetched for exactly one operation and then
zeroed.

For the command surface, see the [CLI command reference](/cli/command-reference/); for which items
are implemented vs. roadmap, the [feature matrix](/reference/feature-matrix/).

## Signing

Basil signs a **raw message** (`message`), never a caller-prehashed `digest`: the broker controls
the hash so a caller can't substitute one.

| Algorithm               | JWS / use                  | Notes                                                                                                                           |
| ----------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Ed25519** / EdDSA     | generic signatures         | The default asymmetric signing key.                                                                                             |
| **RSA-2048** / RS256    | JWS, JWT-SVID issuer       | RSASSA-PKCS1-v1_5 over SHA-256.                                                                                                 |
| **ECDSA P-256** / ES256 | JWS, JWT-SVID issuer       | NIST P-256.                                                                                                                     |
| **ECDSA P-384** / ES384 | JWS, JWT-SVID issuer       | NIST P-384.                                                                                                                     |
| **ECDSA P-521** / ES512 | JWS (`sign`/`verify` only) | NIST P-521. Backend-native for generic signing, but **not** a JWT-SVID issuer: the Rust verifier stack cannot validate `ES512`. |
| **Ed25519-NKey**        | NATS `ed25519-nkey` JWTs   | An Ed25519 key encoded as a NATS NKey; see **NATS identity & credentials** below.                                               |

`verify` runs the matching verification with the key's public half. After a
[rotation](/operations/rotating-keys/), older versions still verify within the grace window.

## Authenticated encryption (AEAD)

Transit-backed symmetric encryption where Basil owns the nonce: a caller can't supply or reuse
one, which removes the classic AEAD footgun by construction.

| Algorithm             | Notes                      |
| --------------------- | -------------------------- |
| **AES-256-GCM**       | 96-bit broker-owned nonce. |
| **ChaCha20-Poly1305** | 96-bit broker-owned nonce. |

## Envelope encryption (KEM)

The `wrap` / `unwrap` model for sealing a payload to a recipient public key.

| Mechanism             | Notes                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------- |
| **X25519 sealed-box** | `wrap`/`unwrap`: X25519 ECDH → HKDF-SHA256 → ChaCha20-Poly1305.                               |
| **ML-KEM envelope**   | `ml-kem-512` / `768` / `1024` wrap/unwrap for software-custodied sealing keys (post-quantum). |

X25519 and ML-KEM sealing keys are **materialize-to-use**: their private half is provisioned or
custodied out of band and used in-process for one unwrap, then zeroized. `GetPublicKey` for ML-KEM
returns the public encapsulation key without materializing the seed. See
[Backends & custody](/introduction/backends-and-custody/).

## NATS identity & credentials

NATS is powerful, but its **NKey** seeds and `.creds` files sprawl across disks. Basil gives NATS
secrets the same custody, rotation, and audit treatment as every other credential: the seed stays in
the backend, and Basil brokers the signing operation rather than handing out the key.

You can reach these operations three ways:

- Over the local socket, using gRPC directly or through the Rust or Go client libraries.
- By sending a NATS message through the `basil-nats-bridge`.
- Through the `basil` CLI.

Basil holds NATS NKey signing keys and curve encryption keys in
custody, and mints NATS credentials without the seed ever leaving the backend. A NATS credential is a
JWT signed by an Ed25519 NKey; Basil builds the exact `ed25519-nkey` signing input a NATS server
expects, has the backend sign it in place (or materialize-to-use on a key store), and assembles
the token. The operator / account / user signing keys are brokered like every other key: used where
they live, never handed out. If you do need a `.creds` file on disk, Basil can generate one on-the-fly
from the signing key and user JWT, for the exact service that needs it,
gated by the process's attested identity and authz policy.

Basil presents this as its fourth engine, `nats`, alongside `transit`, `kv2`, and `pki`: a
Basil-designed transit engine for NATS NKeys that also mints identities and signs their JWTs.

### The NATS bridge

While local services usually connect over a Unix socket, you can reach Basil services over NATS using
the `basil-nats-bridge`. Messages over NATS are encrypted and signed using COSE standards, to
guarantee message privacy, integrity, and authenticity across trusted or untrusted intermediate
networks.

{% note(title="No seeds to hold") %}
Tools that issue NATS credentials normally need to hold operator and account signing seeds. Basil
doesn't: the NKey is a catalog key (`keyType: ed25519-nkey`) under in-place custody, and Basil brokers
the signing operation, not the seed. You get `nsc`-style credentials with the same kernel
attestation, default-deny policy, audit trail, and short-lived leases as the rest of your secrets.
{% end %}

### NKey roles

A public NKey carries its role in its first base32 character (the prefix letter):

| Role           | Prefix | Used for                                                  |
| -------------- | ------ | --------------------------------------------------------- |
| Operator       | `O`    | Top of the trust chain; signs accounts.                   |
| Account        | `A`    | Signs users; owns exports/imports and limits.             |
| User           | `U`    | The connecting client identity.                           |
| Server         | `N`    | NATS server identity.                                     |
| Cluster        | `C`    | Cluster identity.                                         |
| Curve / x25519 | `X`    | `xkey` encryption key (sealed-sender), not a signing key. |

### Minting & signing CLI

When you use the `basil` CLI to perform NATS minting and signing operations,
its identity is verified just like that of any other workload, using the local socket
and `SO_PEERCRED`. The process must
run under the uid of the service that needs the operation performed, and the operation must
be allowed under the authz policy.

| Command | What it does |
| --- | --- |
| `mint-nats-user --key-id … --user-nkey …` | Mints a user JWT, with `--pub-allow`/`--pub-deny`/`--sub-allow`/`--sub-deny` subject permissions. |
| `sign-nats-jwt --key-id … (--claims-json … \| --claims-file …)` | Validates a caller-supplied JSON claim document, normalizes its `jti`/`iat`/`iss`, and signs it with the `ed25519-nkey` profile. |
| `issue-nats-creds (--jwt-file … \| --jwt …) (--seed-file … \| --seed …) --out-file …` | Locally assembles the signed user JWT plus user seed into a canonical `nsc`-style `.creds` file. |

Minting the account, operator, signer, server, and curve identities is available through the gRPC
`NatsService` RPCs and the Rust and Go client libraries, not as `basil` CLI subcommands.

The issuer key's role comes from its catalog `nats_type` label, and Basil checks the issuer ↔ subject
role relationship (an operator signs accounts, an account signs users) before signing. It won't mint
a credential the trust chain doesn't allow.

The rich signer sends the claim object as raw JSON bytes, so integer-valued NATS limits and
timestamps are not converted through protobuf floating-point numbers. See
[NATS integration](/clients/nats/) for the Rust and Go client shapes.

NATS JWT validation verifies the signature and claims against catalog-held or raw public NKey
candidates. See [NATS integration](/clients/nats/).

## Post-quantum

PQC support is built into Basil. ML-DSA signing and ML-KEM envelope operations are available without a
separate cargo feature. The current custody mode is software custody, guarded by the explicit
`op:use_software_custody` policy grant.

| Capability                                            | Status                                                                                                    |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| ML-DSA-44/65/87 sign and verify                       | <span class="pill impl">implemented</span>                                                                |
| ML-KEM-512/768/1024 envelope wrap and unwrap          | <span class="pill impl">implemented</span>                                                                |
| `NewKey` provisioning for ML-DSA and ML-KEM           | <span class="pill impl">implemented</span>                                                                |
| `GetPublicKey` for software-custody ML-DSA and ML-KEM | <span class="pill impl">implemented</span>                                                                |
| Backend-native PQC custody                            | <span class="pill gap">roadmap</span>: no transit engine Basil supports today ships native ML-DSA/ML-KEM. |
| ML-KEM import                                         | <span class="pill gap">roadmap</span>                                                                     |

### Software custody

Today's PQC custody is **software custody** through `LocalSoftwareProvider`. The private seed is stored
as an encrypted `SoftwareCustodyKeyRecord`: Basil AEAD-seals it under the catalog `pqc_storage_key`,
materializes it into zeroizing buffers for one operation, then drops it. The reserved catalog labels
are:

| Label                     | Meaning                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| `crypto_provider`         | Pin a provider such as `local-software`; future native providers use this same seam.        |
| `crypto_provider_policy`  | Provider routing policy: `backend-preferred`, `backend-required`, or local software policy. |
| `pqc_custody`             | Custody mode, today `software-encrypted`.                                                   |
| `pqc_storage_key`         | AEAD key used to encrypt software-custody records.                                          |
| `crypto_provider_version` | Provider record version bound into custody metadata.                                        |

Using software custody requires two policy grants: the underlying operation (`sign`, `verify`,
`encrypt`, `decrypt`, or `new_key`) and `op:use_software_custody` on the same key. That grant is
deliberately excluded from wildcard expansion, so even a root `*/*` break-glass rule does not imply
software custody. Grant it only to callers that should be allowed to bring PQC private material into
the broker process for one operation.

### Provider routing and migration

Provider selection reads the catalog policy/custody labels and the backend capability probe:

| Policy shape                               | Behavior                                                                                                                                    |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend-required`                         | Use a native backend provider only; fail closed when the backend lacks the algorithm.                                                       |
| `backend-preferred`                        | Use native backend support when available, otherwise route to software custody if the key is software-custodied and policy grants allow it. |
| `local-software` / pinned software custody | Use the software-custody record path.                                                                                                       |

The backend-native migration seam already exists:
`Backend::supports_native_algorithm`, `create_named_pqc_key`, `sign_pqc`, and `verify_pqc` default to
unsupported. Migration is **rotation**, not an in-place re-route: provision a new native key version,
publish/serve the new public half, and retire the old software-custody record through the normal
grace/retention path. `describe_provider(key_id)` reports the active custody/provider and whether a
native migration target is available. Every provider operation emits a secret-free
`basil.audit.provider_operation` audit event.

### `KemEnvelope` shape

ML-KEM wrap returns a self-describing `KemEnvelope`:

| Field                | Meaning                                                                                                              |
| -------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `kem_algorithm`      | `ml-kem-512`, `ml-kem-768`, or `ml-kem-1024`.                                                                        |
| `envelope_algorithm` | The AEAD protecting the wrapped payload: `AES-256-GCM` or `ChaCha20-Poly1305`, echoing the request. |
| `key_version`        | Ignored for software-custody ML-KEM unwrap; clients send `0`, and the broker materializes the latest custody record. |
| `encapsulated_key`   | ML-KEM ciphertext / encapsulated key.                                                                                |
| `nonce`              | AEAD nonce for the wrapped payload.                                                                                  |
| `ciphertext`         | Wrapped plaintext plus authentication tag.                                                                           |

## What reconcile can generate

When a catalog key is marked `missing: generate`,
[reconcile](/configuration/capability-and-reconcile/) generates it in place: Ed25519,
Ed25519-NKey, RSA-2048, ECDSA P-256, ECDSA P-384, ECDSA P-521, AES-256-GCM, ChaCha20-Poly1305.

It will not generate X25519 sealing keys or value-store Ed25519 seeds. PQC keys are provisioned
through `NewKey`, where storage/custody stay operator-controlled through the catalog rather than
caller-chosen request fields.

## Where to go next

- [CLI command reference](/cli/command-reference/): the full flag surface for each operation.
- [Backends & custody](/introduction/backends-and-custody/): in-place vs. materialize-to-use.
- [Rotating keys](/operations/rotating-keys/) · [Importing (BYOK) keys & sets](/operations/importing-byok/).
- [Feature matrix](/reference/feature-matrix/): implemented vs. roadmap.
