+++
title = "JWKS HTTP surface"
weight = 90
+++

# JWKS HTTP surface

Basil's primary protocol is gRPC over a peer-credential-attested Unix socket. The HTTP server is an
opt-in build feature, and the listener is disabled by default even when it is compiled in. The one
reason to enable it today is the read-only JWKS endpoint that publishes the public halves of JWT-SVID
issuer keys, so ordinary verifiers (gateways, app frameworks, the standard `jsonwebtoken` stacks) can
validate a Basil-minted JWT-SVID signature without gRPC/SPIFFE.

{% danger(title="Port closed by default") %}
With no `[jwks]` section (or `enable = false`) Basil doesn't start an HTTP listener. A binary built
without `--features http` rejects `jwks.enable = true` at startup.
{% end %}

```toml
[jwks]
enable = true # requires --features http. No HTTP port is opened unless enable is true.
listen = "127.0.0.1:8201" # only bound when enable = true
issuer = "https://basil.example.com" # optional; enables the OIDC discovery document

[jwks.tls]
enable = true # requires a binary built with --features http-tls
cert-file = "/etc/basil/jwks-cert.pem"
key-file = "/etc/basil/jwks-key.pem"
```

| Config key | What it does |
| --- | --- |
| `jwks.enable` | Open the JWKS HTTP listener. **Default `false`**: no port is bound. Requires a binary built with `--features http`; turning it on is the only way to expose any HTTP surface. |
| `jwks.listen` | Socket address to bind when enabled. Default `127.0.0.1:8201` (loopback). A malformed address fails the daemon closed before serving. |
| `jwks.issuer` | Public base URL the surface is reached at (no trailing slash). When set, Basil also serves the OIDC discovery document (see below). Must be an absolute `http(s)` URL. |
| `jwks.tls.enable` | Serve the same JWKS listener over native rustls TLS. Default `false`. Requires a binary built with `--features http-tls`; without it startup fails closed. |
| `jwks.tls.cert-file` | PEM certificate chain file for native TLS. Required when `jwks.tls.enable = true`. |
| `jwks.tls.key-file` | PEM private key file for native TLS. Required when `jwks.tls.enable = true`. |

## Endpoints & behavior

| Property | Value |
| --- | --- |
| JWKS path | `/jwks.json` and `/.well-known/jwks.json` (identical document). |
| Discovery path | `/.well-known/openid-configuration`, served *only* when `jwks.issuer` is set. |
| Method | `GET` only. |
| Auth | None. A JWKS / discovery doc is meant to be world-readable. Safe *because* both serve only public information. |
| Content-Type | JWKS: `application/jwk-set+json` (RFC 7517). Discovery: `application/json`. |
| Cache-Control | `public, max-age=300` on both, plus a content-addressed strong `ETag` for cheap conditional refetch. |

### JWKS body

The JWKS endpoints return an RFC 7517 JWK set: one JWK per issuer key version still inside the rotation
grace window. Each key carries:

- **RSA issuers**: `kty=RSA`, `n`/`e`, `alg=RS256`.
- **ECDSA P-256/P-384 issuers**: `kty=EC`, `crv=P-256`/`P-384`, `x`/`y`, `alg=ES256`/`ES384`. (ECDSA
  P-521 is generic-signing only, never a JWT-SVID issuer.)
- **Every key**: `kid` (the same id Basil stamps in each token's JWS header) and `use=sig`.

The set is byte-identical to what the SPIFFE Workload API JWT bundle publishes for the same issuer.

{% note(title="Public keys only, by construction") %}
The handler reads each issuer's public key(s) (never any private or secret material) and serializes only
the public key coordinates. The JWK set is rebuilt fresh on every request off the live key set, so a
rotated issuer's new `kid` appears as soon as the rotation lands, with no stale cache in between. A
standard verifier fetches the set, picks the key by the token's `kid`, and validates the RS256, ES256,
or ES384 signature.
{% end %}

## Rotation & the grace window

A JWT-SVID is stamped with a `kid` derived from the *exact* issuer key version that signed it. When you
rotate an issuer ([rotating keys](/operations/rotating-keys/)), new tokens are signed by the new version
and carry the new `kid`; tokens minted just before the rotation still carry the old one and remain valid
until they expire on their short TTL. So the JWKS publishes every version still inside the grace
window, the range `[latest − grace-versions … latest]` (clamped to ≥ 1). Once a version falls *below*
the grace floor, its JWK is **dropped** from the set and a token still keyed to that version no longer
resolves. `grace-versions` (default `1`) controls the window width; `grace-versions = 0` publishes the
newest version only. The gRPC SPIFFE Workload-API JWT bundle reflects the same window from the same
source, so the two surfaces never disagree.

## OIDC discovery document

With `jwks.issuer` set, `GET /.well-known/openid-configuration` returns a minimal, spec-valid document:

```json
{
	"issuer": "https://basil.example.com",
	"jwks_uri": "https://basil.example.com/jwks.json",
	"id_token_signing_alg_values_supported": ["RS256", "ES256", "ES384"],
	"response_types_supported": ["id_token"],
	"subject_types_supported": ["public"]
}
```

`issuer` and `jwks_uri` are **consistent** by construction (same scheme/host/base; `jwks_uri` is
`issuer` + the real JWKS path) so a verifier that discovers the issuer fetches the JWKS this same surface
serves.

{% note(title="The iss decision: Basil JWT-SVIDs carry a SPIFFE issuer") %}
A Basil-minted JWT-SVID's `iss` claim is its **SPIFFE trust-domain id** (`spiffe://<trust domain>`),
*not* the discovery `issuer` URL. This is a SPIFFE-compatibility requirement: the SPIFFE JWT-SVID profile
expects a `spiffe://` `iss`, and rewriting it to an HTTPS URL would break SPIFFE clients. A verifier
keyed off the discovery document therefore validates the signature + `kid` + `aud` and **does not
assert `iss`** against the discovery `issuer`. The discovery `issuer` exists only to make the document
self-consistent and to advertise `jwks_uri`.
{% end %}

## Worked example: verify a Basil JWT across a rotation

A standard OIDC/JWKS verifier needs only the published documents. Discover the issuer, fetch the JWKS,
select the key by the token's `kid`, and validate the RS256, ES256, or ES384 signature and `aud`:

```sh
# 1. Discover the issuer (only if jwks.issuer is configured).
curl -s https://basil.example.com/.well-known/openid-configuration
#   -> { "issuer": "...", "jwks_uri": "https://basil.example.com/jwks.json", ... }

# 2. Fetch the JWKS named by jwks_uri.
curl -s https://basil.example.com/jwks.json
#   -> { "keys": [ {kid:"...v2..."}, {kid:"...v1..."} ] }   # both in grace
```

```rust
// Pseudocode for a jsonwebtoken-style verifier (any language):
let header = decode_jws_header(token);          // -> { alg: "RS256"|"ES256"|"ES384", kid: "..." }
let jwk    = jwks.keys.find(|k| k.kid == header.kid);  // pick by kid
if jwk.is_none() { reject("kid not published - outside grace, or unknown issuer"); }
let key = rsa_public_key_from(jwk.n, jwk.e);
verify_rs256(token, key);                        // signature
require(token.aud == "my-audience");             // audience you minted for
// Do NOT assert iss == discovery issuer: Basil's iss is the SPIFFE id (see above).
```

**Across a rotation.** Suppose the issuer is at version 1 and you mint token A, then rotate to version 2
and mint token B. With `grace-versions = 1` the JWKS now lists *both* v1's and v2's `kid`, so the
verifier validates both A and B by selecting each token's `kid`. Rotate once more to version 3
(grace floor advances to 2): v1's JWK is dropped, so token A no longer resolves and is rejected,
while B (v2) and any v3 token still validate. No verifier reconfiguration is needed: it always re-reads
the published JWKS.

{% caution(title="Use TLS for non-loopback exposure") %}
The default surface is plain HTTP. Bind it to loopback and front it with your ingress/TLS terminator,
or build Basil with `--features http-tls` and set `[jwks.tls]` certificate/key paths to serve HTTPS
directly. Set `jwks.issuer` to the public *https* URL verifiers use so the discovery document and
`jwks_uri` point at where verifiers actually reach you.
{% end %}

## Where to go next

- [Rotating keys](/operations/rotating-keys/): how issuer rotation drives the grace window.
- [Go client](/clients/go/): a real `go-oidc` verifier that validates Basil JWT-SVIDs off this surface.
- [Other languages](/clients/other-languages/): verifying JWT-SVIDs from any stack.
