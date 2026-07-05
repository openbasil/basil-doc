+++
title = "Feature matrix"
weight = 10
+++

# Feature matrix

A per-feature breakdown of what Basil does today versus what's planned. Basil is under active
development: <span class="pill impl">implemented</span> items work in the current tree;
<span class="pill gap">roadmap</span> items are deliberate gaps.

[Backends](#backends) · [Unlock & bootstrap](#unlock-bootstrap) · [Identity & leases](#identity-leases) · [Crypto & custody](#crypto-custody) · [SPIFFE & SPIRE](#spiffe-spire-interoperability) · [Attestation sources](#attestation-sources) · [Identity protocols](#identity-protocols) · [Operations & policy](#operations-policy) · [Admin API](#admin-api) · [Developer ergonomics](#developer-client-ergonomics)

## Backends

| Status | Backend                                                             | Kind       | Build status   | Custody                        |
| ------ | ------------------------------------------------------------------- | ---------- | ------------- | ------------------------------ |
| ✅     | OpenBao transit/KV-v2/PKI                                           | `vault`    | default       | In-place backend crypto        |
| ✅     | HashiCorp Vault CE transit/KV-v2/PKI                                | `vault`    | default       | In-place backend crypto        |
| ✅     | Local encrypted SQLite-compatible key store (`db-keystore` / turso) | `keystore` | `db-keystore` | Materialize-to-use             |
| ✅     | 1Password provider key store                                        | `keystore` | default       | Materialize-to-use             |
| ✅     | AWS KMS signer/encrypter backend                                    | `aws-kms`  | opt-in `aws-kms` | In-place KMS operation       |
| ✅     | Google Cloud KMS backend                                            | `gcp-kms`  | opt-in `gcp-kms` | In-place KMS operation       |
| ☐      | HashiCorp Vault Enterprise (untested)                               | `vault`    | roadmap       | In-place backend crypto        |
| ☐      | SOPS/age file backend for static bootstrap                          | TBD        | TBD           | Planned                        |
| ☐      | AWS Secrets Manager native value backend                            | TBD        | TBD           | Planned value-store backend    |
| ☐      | Azure Key Vault backend                                             | TBD        | TBD           | Planned KMS/secret backend     |
| ☐      | Google Cloud Secret Manager native value backend                    | TBD        | TBD           | Planned value-store backend    |
| ☐      | PKCS#11 / HSM backend                                               | TBD        | TBD           | Planned in-place HSM operation |

OpenBao and HashiCorp Vault CE remain the default strong-custody path: the backend performs private
crypto in place and key bytes stay there. The `keystore` kind targets smaller / low-memory
deployments: `db-keystore` seals its database encryption key in the bundle as `DbKeystoreDek`, and
`1password` seals provider configuration as `OnePassword`. Both materialize key bytes for one
operation, then zeroize them. AWS KMS and GCP Cloud KMS are separate in-place transit backends. See
[Backends & custody](/introduction/backends-and-custody/).

## Unlock & bootstrap

| Status | Capability                                                                                                                                                                               |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ✅     | Sealed credential bundle with anti-rollback epoch sidecar                                                                                                                                |
| ✅     | Sealed `BackendCred` variants for vault-compatible backends, `db-keystore`, `1password`, AWS KMS, and GCP Cloud KMS. See [Unlock & the sealed bundle](/configuration/unlock-and-bundle/) |
| ✅     | Public-key credential deposits: signed contributor records, sealed allow-list, startup overlay, and explicit promotion                                                                   |
| ✅     | `age` / YubiKey unlock slot (default build)                                                                                                                                              |
| ✅     | Production file-sourced passphrase unlock slot                                                                                                                                           |
| ✅     | BIP39 break-glass unlock slot (default build)                                                                                                                                            |
| ✅     | TPM-sealed unlock slot (auto-unlocks at boot from the host TPM; behind the off-by-default `unlock-tpm` cargo feature)                                                                     |
| ☐      | Shamir split-key unlock                                                                                                                                                                  |

## Identity & leases

| Status | Capability                                                                                          |
| ------ | --------------------------------------------------------------------------------------------------- |
| ✅     | Generic JWT minting                                                                                 |
| ✅     | DNS/IP-SAN TLS leaf certificate issuance from backend PKI                                           |
| ✅     | X.509-SVID and JWT-SVID issuance                                                                    |
| ✅     | JWT-SVID revocation deny-list and `REVOKED` watch events                                            |
| ✅     | NATS user, account, operator, signer, server, and curve JWT minting                                 |
| ✅     | NATS JWT signing (`sign-nats-jwt`): validate, normalize, and sign a caller-supplied claim document  |
| ✅     | NATS JWT signature/claim **validation** (`ValidateNatsJwt`: verify a token against its issuer NKey) |

## Crypto & custody

### Signing

| Status | Capability                                                                                    |
| ------ | --------------------------------------------------------------------------------------------- |
| ✅     | Raw-message signing contract (`message`, not caller-prehashed `digest`)                       |
| ✅     | Ed25519 / EdDSA signing                                                                       |
| ✅     | RSA-2048 / RS256 JWS signing (generic `mint-jwt` + JWT-SVID issuer path)                      |
| ✅     | ECDSA P-256 / ES256 and P-384 / ES384 JWS signing (generic `mint-jwt` + JWT-SVID issuer path) |
| ✅     | ECDSA P-521 / ES512 backend-native signing (generic `sign`/`verify`; not a JWT issuer)        |
| ✅     | PQC ML-DSA-44/65/87 sign/verify: software custody, always built in                           |
| ☐      | RSA-PSS signing · Ed448 signing                                                               |

### Encryption & envelopes

| Status | Capability                                                                                                       |
| ------ | ---------------------------------------------------------------------------------------------------------------- |
| ✅     | Transit-backed AEAD encrypt/decrypt with broker-owned nonces (AES-256-GCM, ChaCha20-Poly1305)                    |
| ✅     | Client-side streaming encryption for files/large payloads (Rust `basil::stream`, Go `stream`)                    |
| ✅     | X25519 sealed-box envelope encryption (`wrap`/`unwrap` KEM: X25519 ECDH → HKDF-SHA256 → ChaCha20-Poly1305)       |
| ✅     | PQC ML-KEM-512/768/1024 envelope `WrapEnvelope`/`UnwrapEnvelope`: software-custodied sealing keys |
| ☐      | HPKE (RFC 9180) envelope encryption · JWS detached signatures                                                    |
| ☐      | HMAC generate/verify · KDF / key derivation · backend random-bytes API                                           |

### Key management & custody

| Status | Capability                                                                                                                     |
| ------ | ------------------------------------------------------------------------------------------------------------------------------ |
| ✅     | Backend-native RSA-2048, ECDSA P-256/P-384/P-521, and Ed25519-NKey generation                                                  |
| ✅     | BYOK key import for Ed25519, RSA-2048, ECDSA P-256/P-384/P-521 (single + all-or-nothing batch `import-set`)                    |
| ✅     | Key rotation with grace-window version retention and archived-version pruning                                                  |
| ✅     | Materialize-to-use key custody (X25519/ML-KEM unseal, value-store Ed25519 sign) with out-of-band public half                   |
| ✅     | Key-store materialize-to-use crypto for `db-keystore` and default-on 1Password                                                |
| ✅     | PQC provider metadata labels and fail-closed unsupported handling                                                              |
| ✅     | PQC ML-KEM-512/768/1024 `NewKey` provisioning and `GetPublicKey` read: software custody                                        |
| ☐      | PQC backend-native custody (Vault and OpenBao transit engines do not yet support native ML-DSA/ML-KEM) · ML-KEM key import |

## SPIFFE & SPIRE interoperability

| Status | Capability                                                                                                                                                                             |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ✅     | gRPC SPIFFE Workload API: `FetchX509SVID`, `FetchJWTSVID`, `FetchJWTBundles`, `FetchX509Bundles`, `ValidateJWTSVID` with `workload.spiffe.io` header and `SO_PEERCRED` policy gating    |
| ✅     | `rust-spiffe` client interop tests (X.509/JWT-SVID fetch, rustls peer auth, live X.509 rotation, wire-compat)                                                                          |
| ✅     | `go-spiffe` client interop tests (`FetchX509Context`/`FetchJWTSVID`/`ValidateJWTSVID` with the `workload.spiffe.io` header, `tlsconfig` mTLS, JWT-SVID over HTTP, live X.509 rotation) |
| ☐      | Cross-implementation interop matrix beyond `rust-spiffe` and `go-spiffe` (java/py/c SDKs)                                                                                              |
| ☐      | SPIFFE Federation bundle endpoint server / client with periodic foreign-bundle refresh                                                                                                 |
| ☐      | Federation bootstrap using `https_spiffe` or Web PKI                                                                                                                                   |
| ☐      | SPIRE registration-entry import/export                                                                                                                                                 |
| ☐      | SPIRE-style Upstream Authority integration                                                                                                                                             |
| ✅     | **Initial** Envoy SDS v3 integration for X.509-SVID delivery (`FetchSecrets` and initial `StreamSecrets`; rotation push and final hardening remain roadmap)                            |
| ☐      | Trust-bundle cache persistence and stale-bundle policy                                                                                                                                 |

## Attestation sources

| Status | Capability                                                                       |
| ------ | -------------------------------------------------------------------------------- |
| ✅     | `SO_PEERCRED` kernel attestation (caller uid / gid / pid over the local socket)  |
| ☐      | /proc exe path + Sha256                                                          |
| ☐      | systemd unit identity · cgroup identity · container runtime metadata attestation |
| ☐      | Kubernetes service account attestation · TPM-based node attestation              |
| ☐      | X.509 proof-of-possession attestation · pluggable attestor interface             |

## Identity protocols

| Status | Capability                                                                                                                                                      |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ✅     | OIDC discovery document for JWT-SVID issuers                                                                                                                    |
| ✅     | JWKS HTTP endpoint for non-SPIFFE JWT-SVID verifiers (`http` build feature plus `[jwks] enable = true`)                                                           |
| ✅     | COSE sealed invocation profile with `EdDSA` and `ES256` `COSE_Sign1`, preflight validation, protected Rust `Sign` responses, Rust helpers, and checked fixtures |
| ✅     | NATS request/reply bridge courier for raw COSE request and response bytes                                                                                       |
| ✅     | Go sealed-invocation build/open helper (`clients/go/sealedinvocation`: `BuildRequest` / `OpenResponse`, round-trip tested)                                        |
| ☐      | OAuth 2.0 Token Exchange using JWT-SVID as the subject token                                                                                                    |

## Operations & policy

| Status | Capability                                                               |
| ------ | ------------------------------------------------------------------------ |
| ✅     | Local audit log (per-operation decision records)                         |
| ✅     | Offline catalog + policy validation (`basil config check`)               |
| ✅     | Startup reconcile with capability enforcement and existence probes       |
| ✅     | Admin `Status` RPC (backend, version, protocol)                          |
| ✅     | Hot reload for catalog and policy with generation pinning                |
| ✅     | Policy dry-run / explain mode (`basil config explain`, offline)          |
| ✅     | Admin health/readiness probes                                            |
| ✅     | Audit/log sink: OTLP / OpenTelemetry (`otlp` cargo feature, default-off) |
| ✅     | Audit/log sink: journald                                                 |
| ☐      | Prometheus metrics                                                       |
| ☐      | Rate limits by uid/key/op                                                |
| ☐      | Emergency freeze by key, uid, or operation                               |
| ☐      | Enforced multi-party approval (dual-control) gate for config changes     |

## Admin API

| Status | Capability                                                               |
| ------ | ------------------------------------------------------------------------ |
| ✅     | `Status` returns broker version, backend, and protocol info              |
| ✅     | `Health`: liveness probe over the Unix socket                            |
| ✅     | `Readiness`: readiness probe with structured reason codes                |
| ✅     | `Watch` streams an event feed (`KeyRotated`, `BundleChanged`, `Revoked`) |
| ✅     | `Reload`: live catalog and policy reload without restart                 |
| ✅     | `Explain`: policy dry-run with matched-rule detail                       |
| ✅     | `Revoke`: JWT-SVID deny-list revocation                                  |

## Developer & client ergonomics

| Status | Capability                                                                                                 |
| ------ | ---------------------------------------------------------------------------------------------------------- |
| ✅     | `basil` CLI (keys, sign/verify, encrypt/decrypt, get/set, rotate, mint, NATS `.creds`, issue-cert, status) |
| ✅     | `basil get --format` materialization (`raw`, `hex`, standard padded `base64`, `base64-url-no-pad`)         |
| ✅     | `basil config check` validates a catalog + policy offline                                                  |
| ✅     | `basil config init` config/template scaffolding                                                            |
| ✅     | `basil doctor` environment check                                                                           |
| ✅     | `basil explain` explains a policy decision against the live broker                                         |
| ✅     | Rust client library (`basil` crate, async + sync)                                                          |
| ✅     | Go client library (`github.com/openbasil/basil-go`, package `basil`; `spiffe` + `stream` subpackages)      |
| ✅     | Cross-language streaming container interop (Rust reference CLI ↔ Go `stream`)                              |
| ✅     | Rust sealed-invocation helper API and checked COSE fixture                                                 |
| ✅     | Generated roff man pages (`just man-pages` / `cargo xtask`) and Linux `basil-deb` package                  |
| ☐      | Python client                                                                                              |
| ☐      | NATS resolver/operator bootstrap helpers                                                                   |
| ☐      | NATS auth callout helpers                                                                                  |

## Where to go next

- [What is Basil?](/introduction/what-is-basil/): the model in one page.
- [How it works](/introduction/how-it-works/): the request path end to end.
- [Backends & custody](/introduction/backends-and-custody/): the custody models behind this table.
