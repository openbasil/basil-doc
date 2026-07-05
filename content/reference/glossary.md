+++
title = "Glossary"
weight = 20
+++

# Glossary

| Term | Meaning |
| --- | --- |
| **AEAD** | Authenticated Encryption with Associated Data (AES-256-GCM, ChaCha20-Poly1305). Basil owns the nonce so a caller can't reuse one. |
| **Anti-rollback epoch** | A monotonic counter in the bundle, checked against a sidecar file, that refuses an older bundle restored over a newer one. |
| **Attestation** | Establishing the caller's identity. Basil uses `SO_PEERCRED`: the kernel's uid/gid/pid for the socket peer. |
| **BYOK** | Bring Your Own Key: provisioning a caller-supplied key via `import` (write-only; the reply carries only the public half). |
| **Capability policy** | The startup check that each backend provides the engines/capabilities/mintable key types the catalog requires (`strict`/`degraded`/`off`). |
| **Catalog** | The inventory of keys: one entry per key naming its class, algorithm, backend, engine, and path. Basil routes every request through it. |
| **Default-deny** | Nothing is permitted until a policy rule grants it. |
| **Engine** | A backend capability surface: `transit` (sign/encrypt in place), `kv2` (stored values), `pki` (X.509 leaf issuance), and Basil's own `nats` (NATS identity minting + JWT signing). |
| **Generation** | A monotonic id advanced on each successful hot reload; pinned per request so a reload can't mix an old catalog with a new policy. |
| **Grace window** | How many recent key versions still verify/decrypt after a rotation (`grace-versions`). |
| **In-place custody** | The default custody model: private-key operations happen inside the backend; key bytes never enter Basil. |
| **JWKS** | JSON Web Key Set (RFC 7517), the public-key document Basil can optionally publish so plain verifiers validate JWT-SVID signatures. |
| **KEM** | Key Encapsulation Mechanism: the `wrap`/`unwrap` envelope model (X25519 sealed-box; ML-KEM wrap/unwrap). |
| **Lease** | A short-lived, narrowly-scoped credential (NATS JWT, SPIFFE token) that expires on its own. |
| **Materialize-to-use** | The sanctioned exception (design §17.7): for algorithms the backend can't run in place, the private is materialized in-process for one op, then zeroized. Its public half is provisioned out of band. |
| **NKey** | A NATS Ed25519 key encoding used by NATS identity JWTs. |
| **PDP** | Policy Decision Point: the component that evaluates `(subject, op, key)` against the policy. `basil config explain` drives the same PDP the broker enforces with. |
| **Policy** | The default-deny allow-list mapping resolved subjects to operations on keys. |
| **Reconcile** | The startup check that every catalog key actually exists in its backend, per its `missing` policy. |
| **Sealed bundle** | The encrypted file holding the backend credential, opened by an unlock slot at startup. |
| **`SO_PEERCRED`** | A Unix-socket option that reports the connected peer process's real uid, gid, and pid, as vouched for by the kernel. Basil's attestation anchor. |
| **SPIFFE** | Secure Production Identity Framework For Everyone: the open standard Basil implements for workload identity. |
| **Subject** | A named actor in policy, resolved from authentication evidence such as Unix `SO_PEERCRED`. Rules grant to subjects, and audit records name the authorized subject. |
| **SVID** | SPIFFE Verifiable Identity Document, an X.509 certificate or JWT proving a workload's SPIFFE ID. |
| **Transit** | The backend engine that signs/encrypts *in place*. The key never leaves it. |
| **Trust domain** | The SPIFFE namespace a set of identities share, e.g. `example.org`; an SVID's `iss`/ID is `spiffe://<trust domain>/...`. |
| **Unlock slot** | A way to recover the bundle's master key: age/YubiKey, file-sourced passphrase, BIP39 break-glass, or TPM (feature-gated `unlock-tpm`). |
| **Workload API** | The standard SPIFFE API that issues SVIDs to workloads. Basil serves it over the local socket. |

## Where to go next

- [What is Basil?](/introduction/what-is-basil/): the model in one page.
- [The catalog](/configuration/catalog/) and [the policy](/configuration/policy/): the two config inputs.
- [Feature matrix](/reference/feature-matrix/): implemented vs. roadmap.
