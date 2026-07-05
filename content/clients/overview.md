+++
title = "Client libraries overview"
weight = 10
+++

# Client libraries overview

Everything talks to Basil the same way: gRPC over a local Unix socket, with the kernel attesting
who's calling. There's no bearer token and no network endpoint by default. The socket *is* the
security boundary, and Basil resolves the peer's kernel-attested uid/gid evidence to a policy subject
before authorizing a call. A client **cannot impersonate**: run it under the identity you want Basil
to evaluate.

## The two APIs

| API | What it does |
| --- | --- |
| **Broker API** | Secrets and crypto: `sign`/`verify`/`encrypt`/`decrypt`/`get`/`set`/`rotate`/`list`/`mint`/`issue-cert`, plus admin (`status`/`health`/`ready`/`reload`/`explain`/`revoke`). |
| **SPIFFE Workload API** | Issues X.509-SVID and JWT-SVID identity documents over the same socket, on the standard SPIFFE contract. |

## How to talk to Basil today

| Client | Status | How |
| --- | --- | --- |
| **[Rust](/clients/rust/)** | <span class="pill impl">implemented</span> | The `basil` crate: async `Client` and sync `BlockingClient`. SPIFFE via the upstream `spiffe` (rust-spiffe) crate. |
| **[Go](/clients/go/)** | <span class="pill impl">implemented</span> | The `github.com/openbasil/basil-go` module: broker client, SPIFFE helpers, and streaming encryption. |
| **[Other languages](/clients/other-languages/)** | via gRPC | Any language with gRPC tooling can generate a client from the protobufs and call the broker over the socket. |
| **No source changes** | via sidecar | The [spiffe-helper sidecar](/clients/integration-patterns/) materializes an mTLS identity for a service you can't recompile. |
| **[Sealed invocations](/clients/sealed-invocations/)** | <span class="pill impl">implemented</span> | Opt-in COSE profile with protected Rust `Sign` responses and bridged-transport fixtures. |
| **[NATS bridge](/clients/nats-bridge/)** | <span class="pill impl">implemented</span> | Separate `basil-nats-bridge` courier binary for raw COSE request/reply over NATS. |

{% note(title="Verifying Basil-minted JWTs without SPIFFE") %}
A plain verifier (a gateway, an app framework, a `jsonwebtoken`-style library) can validate a
Basil-minted JWT-SVID off the opt-in [JWKS / OIDC-discovery surface](/configuration/jwks/). No SPIFFE
plumbing needed. Fetch the JWKS, pick the key by `kid`, verify the RS256/ES256/ES384 signature and
`aud`.
{% end %}

## Where to go next

- [Rust client](/clients/rust/): the first-class library.
- [Go client](/clients/go/): the Go module and subpackages.
- [Integration patterns](/clients/integration-patterns/): native client, sidecar, and last-resort pre-fetch.
- [CLI reference](/cli/command-reference/): the `basil` CLI is itself a client.
