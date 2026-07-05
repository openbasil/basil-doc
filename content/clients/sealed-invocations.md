+++
title = "Sealed invocations"
weight = 55
+++

# Sealed invocations

Sealed invocations are Basil's transport-neutral COSE contract for callers that cannot reach the
typed broker services over the local Unix socket. A courier can move the bytes, but it cannot decrypt
the request, assert the actor, pick the operation result, or learn key material.

Use this page as the wire contract for bridged transports and peer messages. Basil uses a strict
COSE profile: requests and responses are signed and encrypted COSE objects, NATS carries raw COSE
bytes, and the gRPC invocation service is only a small local carrier around those bytes.

{% caution(title="Not a second authentication system") %}
Sealed invocation does not restore bearer tokens, uid spoofing, or a metadata principal. The actor is
proved by a `signature-key` subject inside the signed COSE message, then Basil applies the same
default-deny policy and catalog grants as a local socket call.
{% end %}

## Enable the service

`InvocationService.Invoke` is registered on the broker gRPC server, but it rejects requests until an
operator enables it explicitly:

```toml
[broker-identity]
id = "basil://prod/us-east-1/agent-a"
response-signing-key-id = "broker.response_signing.2026q3"

[invocation]
enable = true
audience = ["basil://prod/us-east-1/agent-a"]
request-encryption-key-id = "broker.request_encryption.2026q3"
max-ttl-secs = 60
clock-skew-secs = 30
replay-cache-capacity = 4096
```

| Field | Meaning |
| --- | --- |
| `enable` | Accept sealed invocation requests. Defaults to `false`. |
| `audience` | Broker audience values this agent accepts. |
| `request-encryption-key-id` | Catalog key id for the broker request encryption key. |
| `max-ttl-secs` | Maximum explicit request TTL. Default `60`. |
| `clock-skew-secs` | Accepted issue-time and expiry skew. Default `30`. |
| `replay-cache-capacity` | In-memory replay-cache entry cap. Default `4096`. |

When `enable = true`, `[broker-identity] id` must be a `basil://` URI and
`response-signing-key-id` must name the broker signing key. The request encryption key must be a
`class: sealing` catalog key marked for request encryption. Response encryption keys supplied by
callers must also be `class: sealing` and marked for response encryption, so the broker can produce a
protected response without seeing the caller's private key.

## Message structure

Basil's invocation profile uses **signed sealed messages** for broker requests and responses:

```text
tagged COSE_Sign1
  protected: { alg: EdDSA or ES256, kid: sender signing key id }
  payload:   tagged COSE_Encrypt
    protected: { alg: content encryption, content type, CWT claims, Basil labels }
    payload:   encrypted deterministic CBOR operation body
    recipient: X25519 ECDH-ES + HKDF-256 recipient
  signature: Ed25519 or ECDSA P-256 signature over COSE Sig_structure
```

The outer `COSE_Sign1` authenticates the sender. The embedded tagged `COSE_Encrypt` hides the body
and binds the protected headers through COSE `Enc_structure` AAD. Basil must receive the exact tagged
bytes that were signed and encrypted. Parsing a message into another shape and re-encoding it changes
the bytes that COSE authenticates.

The same profile also supports **seal-only peer messages**: a bare tagged `COSE_Encrypt` without an
outer signature. Use that only when confidentiality to a peer key is enough and sender authenticity
is supplied elsewhere. For brokered in-place decrypt, call `AeadService.UnsealCose` with the complete
tagged `COSE_Encrypt` bytes and the matching encryption-layer `external_aad`.

## Protected claims and labels

Temporal, audience, and correlation claims live in the encrypted layer's protected header. Standard
CWT claims use header `15`; Basil adds private labels in the RFC 9052 private range:

| Label | Name | Role | Meaning |
| --- | --- | --- | --- |
| `-70001` | `in_reply_to` | Response | Request message id answered by this response. |
| `-70002` | `request_hash` | Response | `SHA3-256` of the complete tagged request bytes. |
| `-70003` | `sender_key_id` | Request, response, peer | Sender key id. Must equal the outer `kid` on signed sealed messages. |
| `-70004` | `response_key_id` | Request | Caller-selected key that the broker response must be sealed to. |
| `-70005` | `response_subject` | Request | Optional courier route for the response. |

The role determines which labels are legal:

| Role | Required | Forbidden |
| --- | --- | --- |
| Request | `sender_key_id`, `response_key_id`, CWT `iat`, CWT `cti` | `in_reply_to`, `request_hash` |
| Response | `in_reply_to`, `request_hash`, CWT `iat`, CWT `cti` | `response_key_id`, `response_subject` |
| Peer | `sender_key_id`, CWT `iat`, CWT `cti` | `in_reply_to`, `request_hash`, `response_key_id`, `response_subject` |

`cti` is the message id. It is replay state, not a bearer secret. It must be unique for the sender
inside the replay window. `iss` is the sender subject when present, `aud` is the broker audience when
present, `iat` is required, and `exp` is optional. When `exp` is absent, Basil applies the configured
default TTL.

## Signer certificate headers (`-70006`)

The base profile trusts a signer only by a pinned `kid`: a verifier holds broker or peer signing
public keys out of band and rejects anything else. Some deployments instead want a message to *carry*
the trust chain for its own signer, so a header-aware verifier can resolve an unfamiliar `kid` from
the message itself. Basil supports that with one optional protected header on the **outer**
`COSE_Sign1`:

| Label | Name | Meaning |
| --- | --- | --- |
| `-70006` | `signer_certificates_jwt` | Array of compact trusted-signer certificate JWTs for the outer signing `kid`. |

The label is `crit`, so a verifier that does not understand it fails closed rather than silently
ignoring the chain. The strict codec round-trips the array byte-for-byte like every other protected
value, and the decoded value is exposed through the `ProtectedHeaders` type alongside the CWT claims.

`Verifier::verify` receives the decoded `ProtectedHeaders` on its single verify call. A header-aware
verifier can use `signer_certificates_jwt` to resolve and trust the signer `kid` from the message; a
verifier that pins keys out of band ignores the header and pins as before. Either way, a successful
check still proves only that the pinned or resolved key signed the exact `Sig_structure` bytes.

{% note() %}
Signer certificate headers are an extension beyond the base sealed-invocation profile, added for
downstream COSE interoperability. The base broker request and response flow pins broker signing keys
out of band and does not populate `-70006`.
{% end %}

## Content types and bodies

The COSE content type header is a media-type string. Basil reserves the `application/basil.*`
registry for invocation body schemas:

| Content type | Body schema |
| --- | --- |
| `application/basil.sign-request` | `SignInvocationRequest` |
| `application/basil.sign-response` | `SignInvocationResponse` |
| `application/basil.mint-jwt-request` | `MintJwtInvocationRequest` |
| `application/basil.mint-jwt-response` | `MintJwtInvocationResponse` |
| `application/basil.mint-nats-user-request` | `MintNatsUserInvocationRequest` |
| `application/basil.mint-nats-user-response` | `MintNatsUserInvocationResponse` |

Bodies are deterministic CBOR maps selected only by the protected content type. The current broker
execution path returns protected `application/basil.sign-response` bodies for sealed `Sign`
requests, including denied and invalid-request outcomes. The registry also defines the minting body
contracts used by fixtures and client helpers.

`SignInvocationResponse` carries `status`, `policy_generation`, and an optional `signature`.
`status` is one of `OK`, `DENIED`, `INVALID_REQUEST`, or `INTERNAL_ERROR`. A denied or failed
operation carries no signature bytes, but it is still a trusted result when the response verifies and
opens.

`MintNatsUserInvocationRequest` is a five-entry deterministic CBOR map:

| CBOR key | Field | Meaning |
| --- | --- | --- |
| `1` | `account_key_id` | Account identity key or account signing key that signs the user JWT. |
| `2` | `user_nkey` | User public NKey. |
| `3` | `name` | User display name. |
| `4` | `ttl_secs` | Optional whole-second token lifetime. |
| `5` | `issuer_account` | Optional owning account identity. Set it when `account_key_id` is an account signing key, so the minted JWT carries `nats.issuer_account`. |

## Algorithms and strict validation

The profile is intentionally closed:

| Purpose | Allowed algorithms |
| --- | --- |
| Signature | `EdDSA` COSE codepoint `-8` with Ed25519 keys, or `ES256` COSE codepoint `-7` with ECDSA P-256 keys. |
| Key agreement | `ECDH-ES + HKDF-256` COSE codepoint `-25`, X25519 keys. |
| Content encryption | `A256GCM` COSE codepoint `3`; `ChaCha20-Poly1305` COSE codepoint `24` for peer use. |
| Request binding | `SHA3-256` of the complete tagged request bytes. |

The decoder rejects untagged or wrong-tag messages, indefinite lengths, non-minimal integers,
non-deterministic encodings, duplicate or unknown labels, text labels, unknown algorithm codepoints,
`crit` violations, claims in unprotected headers, missing payloads, and recipient arrays that are not
exactly one recipient. After decoding, Basil re-encodes the parsed semantics and requires byte
equality with the input. This check runs in release builds too.

Nonces and X25519 ephemeral keys are generated by the COSE implementation. Production callers do not
supply them. Secret intermediates are zeroized, low-order X25519 inputs are rejected, Ed25519
verification uses strict verification, and `ES256` signatures are deterministic and low-`S`
normalized.

The checked fixtures include the sealed invocation body set, including the
`mint-nats-user-request` vector with `issuer_account`, and an `ES256` signed `COSE_Sign1` fixture.
The interop suite verifies `ES256` `COSE_Sign1` messages with `veraison/go-cose` in both
directions.

## gRPC carrier

The local broker carrier is deliberately thin:

| Service | Method | Request | Response |
| --- | --- | --- | --- |
| `InvocationService` | `Invoke` | `SealedRequest` | `SealedResponse` |

`SealedRequest` contains one field:

| Field | Meaning |
| --- | --- |
| `message` | Complete tagged request `COSE_Sign1` bytes, exactly as received. |

`SealedResponse` contains:

| Field | Meaning |
| --- | --- |
| `message` | Complete tagged response `COSE_Sign1` bytes. |
| `response_subject` | Optional clear courier route copied from request claim `-70005`. |

`response_subject` is not trusted response metadata. It exists so a courier can publish the protected
response to a caller-selected subject. The caller must verify and decrypt `SealedResponse.message`
before trusting any operation status or output.

Clear gRPC status is transport and protocol status only. Once the broker accepts and opens a request,
allow, deny, invalid body, and sanitized operation failures belong inside the signed and encrypted
response body. If Basil cannot produce that protected response, it fails closed with a clear error and
no trusted operation result.

## Brokered peer-message decrypt (`UnsealCose`)

A **seal-only peer message** is a bare tagged `COSE_Encrypt` with no outer signature. When its
recipient is a backend-custodied X25519 sealing key, the holder cannot open it locally: the private
half stays in the vault and is used *in place*. `AeadService.UnsealCose` opens such a message through
the broker without ever exposing the key.

| Field | Meaning |
| --- | --- |
| `key_id` | Catalog X25519 `class: sealing` key the message is sealed to. |
| `cose_encrypt` | Complete tagged `COSE_Encrypt` bytes, exactly as received. |
| `external_aad` | The encryption-layer external AAD the sender bound (omit for none). |

The response carries only the recovered `plaintext`. The RPC is gated by `op:decrypt` on `key_id`: it
reuses the AEAD decrypt permission rather than adding a new op, so granting an unseal is the same
grant as granting decrypt on that key.

Basil forwards `cose_encrypt` to the key verbatim and never re-encodes it. The COSE `Enc_structure`
AAD embeds the exact serialized protected-header bytes, so any parse-and-re-encode round trip would
change the authenticated bytes and break the AEAD tag. That is why `UnsealCose` is a bytes-in RPC and
not a field on the typed `Decrypt` or `UnwrapEnvelope` calls.

{% caution(title="Fail-closed, and confidentiality only") %}
A wrong `key_id`, a mismatched `external_aad`, or any tampering with the ciphertext, protected
headers, or KDF party identities fails closed with a decrypt error and no plaintext. A successful open
proves only confidentiality to the recipient key; it never proves who sent the message. Sender
identity comes only from an outer `COSE_Sign1`.
{% end %}

### Narrowing the unseal oracle with a catalog pin

By default, an `op:decrypt` grant on the sealing `key_id` opens *any* `COSE_Encrypt` addressed to that
key. When that authority is too broad, pin the key in the catalog. A `sealingPin` on the `class:
sealing` entry restricts `UnsealCose` to envelopes whose KDF `partyU`/`partyV` identities and/or
encryption-layer `external_aad` match the pinned context; a non-matching envelope is refused
`PermissionDenied` before the private key is materialized. If no pin is set, behavior is unchanged.
This is least privilege on the unseal oracle: the same `op:decrypt` grant authorizes only the
contexts you pin. See [the catalog](/configuration/catalog/) for the `sealingPin` schema.

The request is bounded by the broker's configured maximum encrypt size. In Rust, the `BrokerRecipient`
in `basil::sealed_invocation` forwards `OpenRequest::cose_encrypt` verbatim to this RPC; in Go, call
`Client.UnsealCose(ctx, keyID, coseEncrypt, externalAAD)`.

## NATS bridge courier model

`basil-nats-bridge` carries raw COSE bytes:

```text
NATS request payload: <tagged COSE_Sign1 request bytes>
NATS reply payload:   <tagged COSE_Sign1 response bytes>
```

The bridge checks only courier shape: reply subject, payload size, Basil availability, timeout, and
whether a returned `response_subject` is a valid publish subject. It wraps request bytes as
`SealedRequest { message }`, sends them to `InvocationService.Invoke`, and publishes
`SealedResponse.message` unchanged to `SealedResponse.response_subject` when present or to the NATS
reply subject otherwise.

The bridge does not inspect protected headers, decrypt bodies, verify signatures, rewrite subjects,
or fabricate operation results. It also needs no policy grant of its own: Basil authorizes the actor
inside the sealed request (its `signature-key` proof, its `op:decrypt` on the request-encryption
key, and the operation-specific grants on the requested key), never the process that presented it.

## Trust distribution

Requesters must learn broker response-signing public keys out of band, for example through operator
configuration or another controlled trust bundle. Do not fetch trust anchors from the courier and do
not trust a key id merely because it appears in a response.

The Rust helper accepts a pinned map of broker signing key ids to Ed25519 public keys. A response is
accepted only when the signature verifies under a pinned key, the response answers the original
message id, the `request_hash` equals `SHA3-256` of the exact request bytes, and the encrypted body
opens with the caller-selected response key.

Broker request encryption public keys are also distributed out of band. A caller seals the request
to the configured broker request-encryption key id; Basil rejects requests addressed to any other
recipient key.

## Replay and expiry

Before policy evaluation, Basil validates:

| Check | Failure meaning |
| --- | --- |
| Audience | A present `aud` must match one configured broker audience. |
| Issue time | `iat` cannot be beyond allowed clock skew. |
| Expiry | `exp`, or `iat + default TTL`, cannot be older than allowed skew. |
| TTL cap | Explicit `exp - iat` cannot exceed `max-ttl-secs`. |
| Replay | The `(sender_key_id, cti)` pair must not already be in the replay cache. |
| Role shape | Request-only and response-only labels must appear only in their legal roles. |

The replay cache is local broker memory. Size it for the expected request rate over the maximum
accepted TTL and clock skew. A repeated message id for the same sender inside the window is rejected
even if the COSE bytes differ.

## Response protection

Basil signs every protected response with the configured broker response-signing key and seals it to
the request's `response_key_id`. The response claims bind it to the request with `in_reply_to` and
`request_hash`.

Denied operations, invalid request bodies, unsupported content types, and sanitized internal
operation errors are response bodies, not unsigned courier errors, whenever Basil can protect the
response. Treat a verified `DENIED`, `INVALID_REQUEST`, or `INTERNAL_ERROR` exactly as a trusted
operation result. Treat a clear bridge or gRPC error as "no trusted result".

## Rust helper usage

The Rust `basil` crate exports `basil::sealed_invocation`:

```rust
use basil::{
    LocalSealedInvocationSigner, SealedInvocationBody, SealedInvocationOptions,
    SigningAlgorithm, prepare_sealed_invocation,
};
use basil_cose::KeyId;
use basil_proto::invocation::SignInvocationRequest;
use zeroize::Zeroizing;

let signer = LocalSealedInvocationSigner::from_secret_bytes(
    KeyId::from_text("publisher.signing.2026q3")?,
    &Zeroizing::new(sender_private_seed),
);

let body = SealedInvocationBody::Sign(SignInvocationRequest {
    key_id: "publisher.signing.2026q3".to_string(),
    message: b"payload".to_vec(),
    algorithm: i32::from(SigningAlgorithm::Ed25519),
});

let prepared = prepare_sealed_invocation(
    SealedInvocationOptions {
        message_id: "018f0a5d-7f2d-7330-b6d1-102030405060".to_string(),
        issued_at_unix: 1_782_740_000,
        expires_at_unix: Some(1_782_740_030),
        sender_sign_id: "publisher.signing.2026q3".to_string(),
        sender_subject: Some("content.publisher".to_string()),
        recipient_key_id: "broker.request_encryption.2026q3".to_string(),
        recipient_subject: Some("basil://prod/us-east-1/agent-a".to_string()),
        response_encryption_key_id: "publisher.response.2026q3".to_string(),
    },
    &broker_request_encryption_public_key,
    &body,
    &signer,
).await?;

let request = prepared.to_sealed_request();
```

For protected `Sign` responses, use `verify_and_decrypt_sign_response` with the prepared request,
the `SealedResponse`, the private half of the caller's response key, pinned broker signing keys, and
response validation bounds. For broker-backed peer-message opening, `BrokerRecipient` forwards the
embedded tagged `COSE_Encrypt` bytes to `AeadService.UnsealCose` without re-encoding them.

## Policy shape

A sealed invocation actor is a normal policy subject whose matcher contains a `signature-key` proof:

```json
{
  "schemaVersion": 2,
  "subjects": {
    "content.publisher": {
      "allOf": [
        {
          "kind": "signature-key",
          "algorithm": "ed25519",
          "public": "BASE64URL_32_BYTE_ED25519_PUBLIC_KEY"
        }
      ]
    }
  },
  "rules": [
    {
      "id": "publisher-can-submit-and-sign",
      "subjects": ["content.publisher"],
      "action": ["op:decrypt", "op:sign"],
      "target": ["broker.request_encryption.2026q3", "publisher.signing.2026q3"]
    }
  ]
}
```

`algorithm` is `ed25519` for base64url raw Ed25519 public keys or `nats-nkey` for public NATS NKeys.
Malformed public material is rejected at policy load time. Grant only the broker request-encryption
key and the specific operation keys the actor needs.

## Where to go next

- [The policy](/configuration/policy/): `signature-key` subjects and the actor grants behind sealed invocations.
- [Configuration overview](/configuration/overview/): startup TOML, including `[invocation]`.
- [NATS bridge](/clients/nats-bridge/): raw COSE request/reply courier behavior.
- [Rust client](/clients/rust/): the `basil::sealed_invocation` helper exports.
