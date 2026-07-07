+++
title = "RFC compatibility"
weight = 30
+++

# RFC compatibility

Basil builds on open, published standards, so its issued tokens, sealed envelopes, and wire
structures interoperate with tooling you already trust. This page lists the RFCs Basil implements or
interoperates with, grouped by area. Where a standard leaves flexibility or ambiguity, the notes
below record where Basil takes the stricter, more secure interpretation.

Every entry below is <span class="pill impl">implemented</span> in the current tree unless it is
marked <span class="pill gap">roadmap</span>. Basil is under active development, so treat this list
as the standards Basil targets today, not a frozen contract.

[COSE & CBOR](#cose-and-cbor) · [JSON tokens](#json-tokens-jose) · [Signatures & keys](#signature-algorithms-and-keys) · [Key derivation & encryption](#key-derivation-and-encryption) · [Encodings & formats](#encodings-and-formats)

## COSE and CBOR

Basil's sealed invocation protocol is a strict, deterministic profile of COSE: a `COSE_Sign1` over
an embedded tagged `COSE_Encrypt`, so a courier can route a message it cannot read while a recipient
verifies the signature before decrypting.

- **[RFC 9052](https://www.rfc-editor.org/rfc/rfc9052)** CBOR Object Signing and Encryption (COSE):
  Structures and Process. `COSE_Sign1` over an embedded tagged `COSE_Encrypt` carries every sealed
  request and response.
- **[RFC 9053](https://www.rfc-editor.org/rfc/rfc9053)** COSE: Initial Algorithms. Fixes the v1
  suite: `EdDSA` or `ES256` signatures, `ECDH-ES + HKDF-256` (X25519) key agreement, `A256GCM`
  content (`ChaCha20-Poly1305` is also supported).
- **[RFC 8949](https://www.rfc-editor.org/rfc/rfc8949)** Concise Binary Object Representation
  (CBOR). The codec re-encodes every message on decode and requires byte-for-byte equality,
  enforcing the §4.2 deterministic form on release builds.

{% note(title="Basil is a strict COSE profile, not a general COSE verifier") %}
Basil's interop suite checks its codec against the COSE Working Group's published example vectors,
the corpus RFC 9052 and RFC 9053 reference. Basil deliberately **rejects** generic, RFC-valid COSE
that falls outside its profile. It requires `EdDSA` or `ES256`, the signing `alg` and `kid` in the
*protected* header with an empty unprotected header, a tagged `COSE_Encrypt` as the `COSE_Sign1`
payload (the sign-over-encrypt nesting), and the Basil `crit` labels plus CWT claims. The private
request-hash claim uses `SHA3-256` where the RFCs leave the primitive open. Unknown or duplicate
labels, indefinite lengths, non-deterministic encodings, and claims in unprotected headers are all
rejected. This is secure-by-default: anything the profile does not explicitly allow fails closed.
{% end %}

## JSON tokens (JOSE)

Basil issues workload and messaging credentials as JSON Web Tokens, signed and described with the
JOSE family. The keys stay in the vault; Basil brokers the signature, so the private issuer key is
never handed out.

- **[RFC 7519](https://www.rfc-editor.org/rfc/rfc7519)** JSON Web Token (JWT). JWT-SVIDs and NATS
  user, account, operator, server, and signer JWTs are RFC 7519 tokens.
- **[RFC 7515](https://www.rfc-editor.org/rfc/rfc7515)** JSON Web Signature (JWS). Every issued JWT
  is signed as a compact JWS.
- **[RFC 7518](https://www.rfc-editor.org/rfc/rfc7518)** JSON Web Algorithms (JWA). Issuer signing
  algorithms `RS256`, `ES256`, and `ES384` for the generic `mint-jwt` and JWT-SVID issuer paths
  (`ES512`/P-521 is generic-signing only, not a JWT issuer).
- **[RFC 8037](https://www.rfc-editor.org/rfc/rfc8037)** CFRG ECDH and Signatures in JOSE. The
  `EdDSA` (raw Ed25519) JOSE algorithm for Ed25519 JWT-SVID issuers and NATS NKey JWTs.
- **[RFC 7517](https://www.rfc-editor.org/rfc/rfc7517)** JSON Web Key (JWK). The JWKS HTTP endpoint
  publishes issuer public keys as an unauthenticated, world-readable JWK Set.
- **[RFC 8414](https://www.rfc-editor.org/rfc/rfc8414)** OAuth 2.0 Authorization Server Metadata.
  The OIDC discovery document (`/.well-known/openid-configuration`) advertises the issuer and
  `jwks_uri` for non-SPIFFE verifiers.

## Signature algorithms and keys

- **[RFC 8032](https://www.rfc-editor.org/rfc/rfc8032)** Edwards-Curve Digital Signature Algorithm
  (EdDSA). Ed25519 signing for COSE envelopes, NATS NKeys, and Ed25519 SVIDs; a known-answer test in
  the test suite pins the RFC 8032 §7.1 vector.
- **[RFC 6979](https://www.rfc-editor.org/rfc/rfc6979)** Deterministic Usage of DSA and ECDSA. Local
  `ES256` COSE signing uses deterministic ECDSA over P-256 and normalizes low `S`, so the signed
  `COSE_Sign1` fixture is byte-stable. The verifier also rejects high-`S` `ES256` signatures, so
  Basil accepts the same canonical form it emits.
- **[RFC 8410](https://www.rfc-editor.org/rfc/rfc8410)** Algorithm Identifiers for Ed25519, Ed448,
  X25519, X448 in X.509. The fixed PKCS#8 DER prefix that wraps an Ed25519 seed on transit BYOK
  import.
- **[RFC 5958](https://www.rfc-editor.org/rfc/rfc5958)** Asymmetric Key Packages (PKCS#8). The
  `OneAsymmetricKey` version field for PKCS#8-wrapped private keys.
- **[RFC 7468](https://www.rfc-editor.org/rfc/rfc7468)** Textual Encodings of PKIX, PKCS, and CMS
  Structures (PEM). PEM output wraps the Base64 body at 64 columns.

## Key derivation and encryption

- **[RFC 5869](https://www.rfc-editor.org/rfc/rfc5869)** HMAC-based Extract-and-Expand Key
  Derivation Function (HKDF). HKDF-SHA256 derives content keys in COSE and sealed-box envelopes and
  in the streaming encryption format.
- **[RFC 3218](https://www.rfc-editor.org/rfc/rfc3218)** Preventing the Million Message Attack on
  CMS (RSA-OAEP). RSA-OAEP(SHA-256) wraps the ephemeral AES key when importing an RSA BYOK key into
  transit.
- **[RFC 9180](https://www.rfc-editor.org/rfc/rfc9180)** Hybrid Public Key Encryption (HPKE)
  <span class="pill gap">roadmap</span>. A planned envelope-encryption alternative; not yet
  implemented.

## Encodings and formats

- **[RFC 3339](https://www.rfc-editor.org/rfc/rfc3339)** Date and Time on the Internet: Timestamps.
  Audit-log timestamps render as RFC 3339 UTC, `YYYY-MM-DDThh:mm:ssZ` at seconds precision.

## Where to go next

- [Feature matrix](/reference/feature-matrix/): what is implemented versus roadmap, per feature.
- [Sealed invocations](/clients/sealed-invocations/): the COSE request and response protocol in detail.
- [Glossary](/reference/glossary/): the terms these standards share.
