+++
title = "NATS bridge"
weight = 58
+++

# NATS bridge

The `basil-nats-bridge` binary lets NATS request/reply callers reach Basil's sealed invocation
service without making the bridge a trusted actor. It is a **courier**: it moves raw tagged COSE
bytes between NATS and `InvocationService.Invoke`, and Basil does the identity, policy, decryption,
operation execution, response signing, and response encryption.

Use this path when a workload can publish to NATS but should still authorize through a verified
signing key. The bridge process is the local Unix-socket presenter. Basil binds its independently
attested local evidence and the remote signing key in one schema-3 subject. The bridge must not
decrypt request or response bodies, rewrite subjects, delegate, impersonate, or fabricate results.

## Binary and config

`basil-nats-bridge` is a separate Rust binary from the `basil` agent. Run it as its own service user
and point it at both NATS and the local Basil Unix socket:

```toml
[nats]
url = "nats://127.0.0.1:4222"
creds = "/run/credentials/basil-nats-bridge/nats.creds"

[basil]
socket = "/run/basil/basil.sock"

[bridge]
request-subject = "basil.invocation.v1"
queue-group = "basil-nats-bridge"
max-message-bytes = 1048576
```

| Field | Meaning |
| --- | --- |
| `nats.url` | NATS server URL. |
| `nats.creds` | Optional NATS credentials file. Omit it for unauthenticated local NATS deployments. |
| `basil.socket` | Basil agent Unix socket used for `InvocationService.Invoke`. |
| `bridge.request-subject` | NATS subject that accepts sealed invocation request bytes. |
| `bridge.queue-group` | Optional NATS queue group for multiple bridge workers. |
| `bridge.max-message-bytes` | Required maximum accepted NATS payload size, in bytes. Oversized requests get a bridge error. |

The NATS request payload is the complete tagged request `COSE_Sign1`. The NATS reply payload is the
complete tagged response `COSE_Sign1` when Basil returns a protected response. NATS inboxes provide
transport correlation, but callers must still verify the signed response, check the response claims,
and decrypt the body before trusting any status or result.

## Message flow

1. A caller builds a sealed invocation request with the [sealed invocation](/clients/sealed-invocations/)
   helper or the fixture-compatible COSE wire rules.
2. The caller publishes raw tagged request `COSE_Sign1` bytes to `bridge.request-subject` using NATS
   request/reply.
3. The bridge checks only transport shape: reply subject and payload size.
4. The bridge wraps the bytes as `SealedRequest { message }` and forwards them to Basil over
   `InvocationService.Invoke` on the configured Unix socket.
5. Basil verifies the COSE signature, resolves one domain-scoped subject from bridge and signature
   evidence, authorizes its operation-specific grants, executes the operation, and returns
   `SealedResponse { message, response_subject }`.
6. The bridge publishes `SealedResponse.message` bytes unchanged to `SealedResponse.response_subject`
   when present, or otherwise to the NATS reply subject.
7. The caller verifies the broker response signature, checks request binding, decrypts with its
   selected response key, and reads the protected response body.

## Opaque payloads

The bridge never sees `Sign`, minting, or response plaintext. The operation body is inside the
embedded `COSE_Encrypt` payload and remains encrypted.

```text
NATS request payload: <tagged COSE_Sign1 request bytes>
NATS reply payload:   <tagged COSE_Sign1 response bytes>
```

The bridge does not inspect COSE protected headers, claims, content types, signatures, ciphertexts,
or request/response correlation claims. It is a byte courier between NATS and Basil's local
invocation gRPC service.

## Policy grant

The bridge needs no separate `op:invoke` grant. There is no transport-level `op:invoke` action in the
policy language. Its local identity still participates in subject resolution: the matching subject
must bind the bridge evidence and a verified `invocation.signature-key` leaf. The resolved compound
subject needs `op:decrypt` on the request-encryption key and the operation-specific grant for the
inner request.

```json
{
  "schema": "policy",
  "subjects": {
    "content.publisher": {
      "domain": "host-process",
      "match": { "all": [
        { "process.uid": 9100 },
        {
          "invocation.signature-key": {
            "algorithm": "nats-nkey",
            "public": "UANATS_PUBLIC_NKEY"
          }
        }
      ] }
    }
  },
  "rules": [
    {
      "id": "publisher-can-use-invocation-signing",
      "subjects": ["content.publisher"],
      "action": ["op:decrypt", "op:sign"],
      "target": ["broker.request_encryption.2026q3", "publisher.signing.2026q3"]
    }
  ]
}
```

The rule grants the compound subject its real authority. A bridge UID match cannot make an unsigned
or invalid message authorize, and a valid signature cannot bypass the bridge's local domain and
process evidence. If two subjects match, Basil denies before evaluating this rule.

## Audit semantics

Bridged audit records deliberately separate actor and presenter:

| Field | Bridged meaning |
| --- | --- |
| `actor_kind` / `actor_id` | The sealed invocation subject proved by the message, such as `content.publisher`. |
| `authenticated_by` | The evidence summary, including process credentials and a signature-key fingerprint. |
| `presenter_kind` / `presenter_id` | The bridge process attested by `SO_PEERCRED`, such as `svc-nats-bridge(9100)`. |
| `generation`, `op`, `target_id`, `decision`, `reason` | The policy generation, operation target, and PDP outcome for the actor. |

This makes incident review explicit: the bridge delivered the request, but Basil authorized the
sealed actor. If actor proof fails, Basil emits a denied audit record without treating the bridge as
the actor.

## Bridge error headers

When Basil returns sealed response bytes, the bridge forwards them unchanged and does not add bridge
error headers. When the bridge cannot obtain a sealed Basil response, it replies with an empty payload
and these NATS headers:

| Header | Meaning |
| --- | --- |
| `Basil-Bridge-Error` | Stable bridge-level token. |
| `Basil-Bridge-Message` | Operator-facing detail suitable for logs. |
| `Basil-Bridge-Retryable` | `true` only when retrying the same request may succeed. |

Stable error tokens are `MALFORMED_REQUEST`, `MESSAGE_TOO_LARGE`, `BASIL_UNAVAILABLE`,
`BASIL_REJECTED`, `TIMEOUT`, and `INTERNAL`.

| Token | Typical cause |
| --- | --- |
| `MALFORMED_REQUEST` | Missing NATS reply subject. |
| `MESSAGE_TOO_LARGE` | Payload exceeds `bridge.max-message-bytes`. |
| `BASIL_UNAVAILABLE` | The Unix socket cannot be reached or Basil is not serving. |
| `BASIL_REJECTED` | Basil rejected the request before producing a sealed response. |
| `TIMEOUT` | Basil did not respond before the bridge deadline. |
| `INTERNAL` | Unexpected bridge-side failure. |

Do not treat a bridge error as a denied operation result. It means there is no trusted sealed Basil
response. Retry only when `Basil-Bridge-Retryable: true` and your message id and expiry strategy
still satisfy replay and TTL rules.

## Current boundaries

The bridge has no delegation, no impersonation, no metadata auth shortcut, and no migration mode for
legacy unsigned requests. All successful operation results stay inside signed and encrypted COSE
responses.

The Go `sealedinvocation` package (`github.com/openbasil/basil-go/sealedinvocation`) ships a
fixture-compatible `BuildRequest`/`OpenResponse` helper, so Go callers can build and open sealed COSE
invocations broker-free rather than hand-assembling bytes. The bridge itself stays a byte courier: it
never builds or opens the COSE messages it carries.

## Where to go next

- [Sealed invocations](/clients/sealed-invocations/): the COSE profile and response verification contract.
- [The policy](/configuration/policy/): domain-scoped subjects and signature-key evidence.
- [Audit logs](/operations/audit-logs/): actor-vs-presenter fields for bridged requests.
- [NATS integration](/clients/nats/): NATS identity minting, JWT signing, validation, and xkey boxes.
