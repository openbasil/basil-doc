+++
title = "Rust client"
weight = 20
+++

# Rust client

The Rust client library is published as the **`basil`** crate. It's the first-class way to talk to
the broker, and it's deliberately lightweight: it avoids the heavy broker and server dependencies, so
adding it to an application doesn't transitively pull in OpenBao, the tonic server, `age`, or
`argon2`. A client app links the gRPC protocol and the client-side crypto, not the storage backend.

It offers two front ends:

- **`Client`**: the async client (Tokio).
- **`BlockingClient`**: a synchronous wrapper for non-async callers.

## Async example

```rust
use basil::{Client, KeyType, AeadAlgorithm};

# async fn run() -> basil::Result<()> {
// Connect over the broker's Unix socket. The kernel attests this process's
// uid/gid, so there is no token to present.
let mut client = Client::connect("/run/basil/basil.sock").await?;

// Sign a raw message. The private key never leaves the backend.
let signature = client.sign("web.tls.signing_key", b"hello basil").await?;

// AEAD-encrypt. Basil owns the nonce, so you can't reuse one by accident.
let envelope = client.encrypt("app.aead", b"backup-bytes").await?;
let plaintext = client.decrypt("app.aead", &envelope).await?;

// Mint a short-lived generic JWT using the issuer key's JWS algorithm.
let jwt = client.mint_jwt("svc.jwt_issuer", "spiffe://example.org/web", 300).await?;

// Ask the agent what it's fronting.
let status = client.status().await?;
println!("backend: {}, version: {}", status.backend, status.version);
# Ok(())
# }
```

{% note(title="Method shapes vary") %}
The snippets above are simplified to the common shape; several methods take richer arguments than
shown (for example AEAD algorithm selection, AAD, NATS permissions, or certificate SANs). Use your
editor's type information against the `basil` crate for the exact signatures. The groups below list
the full surface.
{% end %}

## Blocking example

```rust
use basil::BlockingClient;

# fn run() -> basil::Result<()> {
let mut client = BlockingClient::connect("/run/basil/basil.sock")?;
let sig = client.sign("web.tls.signing_key", b"hello basil")?;
let status = client.status()?;
# Ok(())
# }
```

## The method surface

| Area | Methods |
| --- | --- |
| **Connect** | `connect(path)`, `connect_with_timeout(path, default_timeout)` |
| **Keys** | `new_key(key_id, key_type)`, `import(...)`, `import_set(entries)`, `list_catalog(prefix)` |
| **Sign / verify** | `sign(key_id, message)`, `sign_with_algorithm(...)`, `verify(key_id, message, signature)`, `verify_with_algorithm(...)`, `get_public_key(...)` |
| **Encrypt / decrypt** | `encrypt(...)`, `decrypt(...)`, `wrap_envelope(...)`, `unwrap_envelope(...)` |
| **Secrets / values** | `get_secret(...)`, `set_secret(secret_id, value)`, `rotate_secret(secret_id)` |
| **Minting & certificates** | `mint_jwt`, `sign_nats_jwt`, `validate_nats_jwt`, `issue_certificate` |
| **NATS keys & curve boxes** | `mint_nats_user`/`account`/`operator`/`signer`/`server`/`curve`, `encrypt_nats_curve`, `decrypt_nats_curve` |
| **Admin** | `status()`, `health()`, `readiness()`, `reload(check)`, `explain(subject, op, key)`, `revoke(...)` |

Public result/argument types include `KeyHandle`, `SecretValue`, `MintedJwt`, `IssuedCertificate`,
`AgentStatus`, `AgentHealth`, `AgentReadiness`, `AgentReload`, `AgentExplanation`, `AgentRevocation`,
`ImportEntry`, `NatsUserPermissions`, and `SignNatsJwtOptions`. Errors surface through `basil::Error`
(with the `basil::Result` alias). Protocol enums such as `KeyType`, `AeadAlgorithm`, and
`CatalogEntry` are re-exported from `basil-proto`.

`sign_nats_jwt` accepts any `serde::Serialize` claim object. Use `sign_nats_jwt_json` when you
already have UTF-8 JSON claim bytes and need to preserve integer-valued NATS claims without an
intermediate structured conversion. See the [NATS JWT reference](/reference/nats-jwt-reference/) for
every account and user claim these calls accept and the semantic defaults Basil applies.

{% tip(title="Sign takes the message, not a digest") %}
Basil's signing contract is over the **raw message**: you pass `b"hello basil"`, not a pre-computed
hash. The broker (and its backend) does the hashing, closing a class of caller-side mistakes.
{% end %}

## Sealed invocation helpers

The crate also exports `basil::sealed_invocation` for sealed-invocation handoff. Use
`SealedInvocationBody`, `SealedInvocationOptions`, and `prepare_sealed_invocation` to build a v1
tagged `COSE_Sign1` for `Sign`, `MintJwt`, or `MintNatsUser` bridged calls. The helper selects the
protected `application/basil.*` content type, emits deterministic CBOR, seals the body to the broker
request-encryption public key, and signs the COSE `Sig_structure` with your signer. For protected
`Sign` responses, `verify_and_decrypt_sign_response` verifies the pinned broker response-signing key,
checks request binding, decrypts the body to the request-selected response key, and decodes the
trusted status and signature fields. The clear gRPC status from `InvocationService.Invoke` reflects
transport and protocol failures only. Trust an operation result (`OK`, `DENIED`, `INVALID_REQUEST`,
or `INTERNAL_ERROR`) only after verifying and decrypting the response body.

See [Sealed invocations](/clients/sealed-invocations/) for the COSE profile, fixture path, replay
and audience rules, `UnsealCose`, and the protected response contract.

## Streaming encryption

The crate also exports `basil::stream` for bounded-memory file and large-payload encryption:
`encrypt_aead` / `decrypt_aead` for symmetric CEKs, and `encrypt_ml_kem` / `decrypt_ml_kem` for
ML-KEM-wrapped CEKs. The format is wire-identical to the Go `stream` subpackage.
See [Streaming encryption](/clients/stream/).

## SPIFFE in Rust

For workload identity, you don't need a bespoke integration:

- Use the upstream [`spiffe`](https://crates.io/crates/spiffe) (rust-spiffe) crate. Its auto-rotating
  `X509Source` connects to the Basil socket and keeps the X.509-SVID fresh on Basil's configured
  `svid-ttl-secs` cadence, with no Basil-specific TLS adapter required.
- Or use the in-tree generated Workload API client
  `basil_proto::spiffe::spiffe_workload_api_client::SpiffeWorkloadApiClient` (already `pub`, exercised
  by the SPIFFE e2e tests).

The high-level `spiffe` client attaches the required `workload.spiffe.io: true` metadata header for
you; a raw generated client must set it itself or every call fails closed with `InvalidArgument`.

{% tip(title="Rust services don't need a sidecar") %}
A Rust service gets an auto-rotating SVID natively via the `spiffe` crate. Save the
[spiffe-helper sidecar](/clients/integration-patterns/) for services you can't recompile.
{% end %}

## Where to go next

- [Integration patterns](/clients/integration-patterns/): native, sidecar, or pre-fetch after designing the secret out.
- [Sealed invocations](/clients/sealed-invocations/): the bridged-transport COSE helpers.
- [Streaming encryption](/clients/stream/): files and large payloads without full buffering.
- [NATS integration](/clients/nats/): NATS JWT validation and curve xkey boxes.
