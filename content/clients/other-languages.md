+++
title = "Other languages"
weight = 35
+++

# Other languages

Basil speaks **gRPC**, so any language with gRPC tooling can drive it, and any stack with a JWT
library can verify Basil-minted tokens. A dedicated Python client is
<span class="pill gap">roadmap</span>; in the meantime the two patterns below cover every language.

## Call the broker over gRPC

Generate a client from the protobufs and dial the broker's Unix socket:

- the [SPIFFE Workload API protobufs](https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE_Workload_API.md)
  for identity (X.509/JWT SVIDs), or
- Basil's own **broker protos** for secrets and crypto (`sign` / `encrypt` / `mint` / …).

The connection is a plain Unix-socket gRPC channel. The socket plus `SO_PEERCRED` is the security
boundary, so no client TLS certificate is involved. Run the client process under the identity you
want Basil to evaluate, because authorization resolves kernel-attested uid/gid evidence to a policy
subject and a client cannot impersonate.

For bridged transports, do not invent a parallel auth scheme. Use the
[sealed invocation](/clients/sealed-invocations/) COSE fixture and canonical bytes. Rust helpers are
implemented, including protected `Sign` response verification/decryption and broker-backed
`UnsealCose` opening. The Go `sealedinvocation` package
(`github.com/openbasil/basil-go/sealedinvocation`) is also implemented: its `BuildRequest` and
`OpenResponse` build and open sealed COSE invocation messages broker-free, matching the checked
fixtures. The [NATS bridge](/clients/nats-bridge/) itself only couriers raw tagged COSE bytes
unchanged; it does not build or open them.

{% note(title="The one required header") %}
Every SPIFFE Workload API RPC must carry the metadata header `workload.spiffe.io: true`, or it fails
closed with `InvalidArgument`. The [Go client page](/clients/go/) shows the metadata pattern; the
equivalent exists in every gRPC binding.
{% end %}

## Verify Basil JWT-SVIDs anywhere

If you only need to *verify* tokens (a gateway, an application framework, a `jsonwebtoken`-style
library), you don't need gRPC or SPIFFE at all. Point your verifier at Basil's opt-in
[JWKS / OIDC-discovery surface](/configuration/jwks/):

1. (Optional) discover the issuer at `/.well-known/openid-configuration` to learn `jwks_uri`.
2. Fetch the JWKS at `/jwks.json`.
3. Select the key by the token's `kid`.
4. Verify the **RS256, ES256, or ES384** signature and the `aud` you minted for.
5. Do not assert `iss` against the discovery issuer: a Basil JWT-SVID's `iss` is its SPIFFE id.

This works with the standard JWKS-aware verifier in essentially any ecosystem (Node, Python, Java,
Go, .NET, …).

## No source changes at all

For a service you can't modify, the [spiffe-helper sidecar](/clients/integration-patterns/)
materializes the X.509-SVID, its private key, and the trust bundle as PEM files and keeps them fresh:
a standard, maintained tool that solves rotation for you.

## Where to go next

- [JWKS HTTP surface](/configuration/jwks/): endpoints, rotation, and a worked verification example.
- [Sealed invocations](/clients/sealed-invocations/): transport-neutral COSE profile and fixture contract.
- [Go client](/clients/go/): a concrete instance of the gRPC and OIDC patterns above.
- [Integration patterns](/clients/integration-patterns/): choosing native, sidecar, or pre-fetch.
