+++
title = "Error & status code reference"
weight = 10
+++

# Error & status code reference

Basil **fails closed** and never panics on the request path: a bad input, a denied caller, or a
flaky backend turns into a clean status code, not a crashed broker. What each code means and what to
do about it:

## Wire status codes

| Code | gRPC | Meaning / your move |
| --- | --- | --- |
| `UNAUTHORIZED` | `PermissionDenied` | Policy said no, or the key doesn't exist. Deliberately indistinguishable and detail-free (no key enumeration). Check the audit `reason` for the real cause. |
| `UNAUTHENTICATED` | `Unauthenticated` | Missing peer credentials (`SO_PEERCRED`): the broker can't attest the caller, so it fails closed before policy runs. |
| `INVALID_REQUEST` | `InvalidArgument` | Malformed input, wrong op for the key's class, or an algorithm mismatch. A client/config bug; fix the call. |
| `PAYLOAD_TOO_LARGE` | `ResourceExhausted` | Over an encrypt/payload cap. Raise the limit ([Limits](/configuration/limits/)) or chunk the data. |
| `UNSUPPORTED` / `UNSUPPORTED_ALGORITHM` | `Unimplemented` | The op or algorithm isn't backed here (usually a catalog/backend mismatch). Re-run `basil doctor`. |
| `DECRYPT_FAILED` | `InvalidArgument` | AEAD/unseal authentication failed: wrong key, tampered ciphertext, or mismatched AAD. Opaque on purpose: no oracle distinguishing the cause. |
| `BACKEND_UNAVAILABLE` | `Unavailable` | The backend is unreachable. Likely transient infra, so retry and check Vault/OpenBao health. |
| `BACKEND_ERROR` / `INTERNAL` | `Internal` | The backend rejected the op, or an internal invariant (e.g. a misconfigured `publicPath`) tripped. Check logs; usually a config issue. |

Admin ops (`explain`, `revoke`) return the same `InvalidArgument` gRPC code with the token
`INVALID_ARGUMENT` rather than `INVALID_REQUEST`; the meaning is identical. Two narrower reasons round
out the set: `revoke` without a configured store returns `NO_REVOCATION_STORE` (`FailedPrecondition`),
and a sealed-invocation response-protection failure returns `INVOCATION_RESPONSE_PROTECTION_FAILED`
(`Internal`).

{% note(title="Failures are isolated per key") %}
Each key resolves independently, so a backend that's down fails only the ops routed to it. Keys on a
healthy backend keep serving. One bad backend doesn't take down the broker.
{% end %}

{% tip(title="Why some errors tell you so little") %}
`UNAUTHORIZED` and `DECRYPT_FAILED` are intentionally terse, hiding whether a key exists
or why a decrypt failed. When you need the *why*, it's in your [audit log](/operations/audit-logs/)
(for authorization) or the broker's `tracing` output (for backend/crypto), not in the caller-facing
status.
{% end %}

## Where to go next

- [Audit logs](/operations/audit-logs/): the `reason` token behind an `UNAUTHORIZED`.
- [Incident runbook](/troubleshooting/incident-runbook/): scenario-by-scenario response.
