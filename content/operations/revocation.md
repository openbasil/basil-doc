+++
title = "Revocation"
weight = 30
+++

# Revocation

Basil keeps a **JWT-SVID deny-list**: a persisted set of revoked credentials, keyed by
`(trust_domain, jti)` with an expiry. On `ValidateJWTSVID` a revoked `jti` is rejected, and a
`REVOKED` watch event is pushed to connected Workload API clients so they drop the credential
promptly rather than waiting for it to expire.

## How the deny-list is wired

- The store is a catalog `value` key carrying the reserved label `revocation_store=jwt-svid`.
- It's loaded into memory at startup, refreshed after successful hot reloads, and consulted on every
  validation.
- Reload refreshes use union semantics: out-of-band/peer revocations are added, and an in-memory
  revocation is not shortened or removed by a reload.
- Entries auto-expire: once a revoked credential's own expiry passes, the entry is moot (a
  short-lived SVID is already gone).

{% note(title="Live revocation is explicit and persisted") %}
`basil revoke` writes through the configured `revocation_store=jwt-svid` value key, updates the live
in-memory deny-list, and publishes a `REVOKED` watch event. If no persistent store is configured, the
command fails closed instead of creating a restart-lost in-memory revocation.
{% end %}

## Permission grant and CLI

Revocation is gated by a dedicated broker-admin op. It is not implied by data-plane grants,
`op:reload`, `op:explain`, or wildcard `*`. Grant `op:revoke` explicitly over the reserved target
`broker.revoke`:

```json
{
	"schemaVersion": 2,
	"subjects": {
		"svc.revoke": { "allOf": [{ "kind": "unix", "uid": 4244 }] }
	},
	"rules": [
		{
			"id": "broker-admin-revoke",
			"subjects": ["svc.revoke"],
			"action": ["op:revoke"],
			"target": ["broker.revoke"]
		}
	]
}
```

```sh
basil revoke --trust-domain example.org \
  --jti 01J2REVOCATION \
  --expires-at-unix 1767225600

basil revoke --trust-domain example.org --jti 01J2REVOCATION \
  --expires-at-unix 1767225600 --json
# {"trust_domain":"example.org","jti":"01J2REVOCATION","expires_at_unix":1767225600,"persisted":true}
```

Use the trust-domain label form (for example `example.org`), not `spiffe://example.org`.
`expires-at-unix` should be the token's `exp`; the deny-list entry is pruned after that time. Because
SVIDs are short-lived by design, revocation is the exception, not the routine. For many incidents,
rotating the issuer key plus waiting out outstanding TTLs is the faster lever.

{% tip(title="X.509 revocation") %}
X.509-SVIDs carry a serial and are governed by the backend PKI engine's CRL, not this deny-list.
Short TTLs remain your first line of defense: Basil issues SVIDs that expire in minutes, so the
window an un-revoked credential stays valid is small by construction.
{% end %}

## Where to go next

- [The catalog](/configuration/catalog/): declaring the `revocation_store` value key.
- [Command reference](/cli/command-reference/): the full `basil revoke` signature.
