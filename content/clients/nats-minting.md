+++
title = "Mint NATS credentials without nsc"
weight = 45
+++

# Mint NATS credentials without nsc

`nsc` manages NATS operator and account NKeys as seed files in a directory. That works, but the
directory *is* the trust root: whoever copies `~/.nkeys` can mint users for every account forever,
and nothing records which seeds minted what. This tutorial replaces that workflow with Basil:
operator and account seeds live in the backend and sign **in place**, minting is a policy-gated
operation granted per uid, every mint has a TTL, and every decision lands in the audit log.

The shape of the flow matches `nsc` deliberately: import (or generate) issuer keys once, mint user
JWTs on demand, and assemble `.creds` files for the connecting clients.

## 1. Declare the issuer keys

NATS issuer keys are catalog signing keys: `keyType: ed25519-nkey` on the `transit` engine with a
`nats_type` label naming the NKey role (`O` operator, `A` account, `U` user). There is no
`engine: nats`; the NATS role is metadata on a signing key (see
[NATS integration](/clients/nats/)).

```json
"nats.operator": {
  "class": "asymmetric",
  "keyType": "ed25519-nkey",
  "backend": "bao",
  "engine": "transit",
  "path": "nats-operator",
  "writable": true,
  "missing": "error",
  "labels": { "nats_type": "O" }
},
"nats.account": {
  "class": "asymmetric",
  "keyType": "ed25519-nkey",
  "backend": "bao",
  "engine": "transit",
  "path": "nats-account",
  "writable": true,
  "missing": "error",
  "labels": { "nats_type": "A" }
}
```

For a brand-new deployment you can set `missing: generate` and let reconcile create fresh NKeys in
place; then nothing below about importing applies. `missing: error` is the migration posture: the
keys must be the ones your `nats-server` already trusts, so they arrive by import, never by
accidental generation.

## 2. Import your existing NKeys

Migrating a live NATS deployment means bringing the operator and account seeds `nsc` holds into
the backend. `import-set` moves them in one all-or-nothing batch: the broker authorizes `import`
on every entry before importing any, so a partial trust migration cannot happen.

The manifest takes each key's raw 32-byte Ed25519 seed as 64 hex characters. An NKey seed string
(`SO...`, `SA...`) is an encoding of that seed, so decode it to raw hex first; the encrypted-at-rest
copy in the backend is what signs from then on.

```json
[
  { "key_id": "nats.operator", "key_type": "ed25519-nkey", "seed_hex": "<64 hex chars>" },
  { "key_id": "nats.account",  "key_type": "ed25519-nkey", "seed_hex": "<64 hex chars>" }
]
```

```sh
basil --socket /run/basil/basil.sock import-set --file ./nats-issuers.json
```

Import is wrapped end to end: the broker fetches the backend's `wrapping_key` and the material
reaches the backend only RSA-OAEP + AES-KWP wrapped. See
[Importing (BYOK) keys & sets](/operations/importing-byok/). Once the import verifies (the printed
public keys must match your existing operator and account ids), retire the seed files. That
retirement is the point of the exercise.

## 3. Grant minting narrowly

Minting is the `mint` op over the issuer key. The uid that provisions users (a CI job, a device
enrollment service) gets `mint` on the account key and nothing else; importing needed a separate
`import` grant you can now remove.

```json
{
  "id": "enroll-can-mint-users",
  "subjects": ["svc.enroll"],
  "action": ["op:mint"],
  "target": ["nats.account"],
  "comment": "The enrollment service may mint user JWTs from the account key. It cannot read, rotate, or import."
}
```

## 4. Mint a user JWT, with a TTL

The connecting client generates (and keeps) its own user NKey; Basil deliberately does not mint
user seeds. Mint the user JWT from the account key, bounded in time and in subject space:

```sh
basil --socket /run/basil/basil.sock mint-nats-user \
  --key-id nats.account \
  --user-nkey "$USER_PUBLIC_NKEY" \
  --name device-42 \
  --ttl-secs 3600 \
  --pub-allow "telemetry.device-42.>" \
  --sub-allow "commands.device-42.>" > device-42.jwt
```

`--pub-allow`/`--pub-deny`/`--sub-allow`/`--sub-deny` repeat, and they bake NATS subject
permissions into the JWT itself, so the credential carries its own least privilege. If `--key-id`
is an account *signing* key rather than the account identity key, add `--issuer-account` with the
owning account's public NKey; [NATS integration](/clients/nats/) explains why nats-server requires
it.

## 5. Assemble the `.creds` file

`issue-nats-creds` is local file plumbing (no socket, no broker): it combines the minted JWT with
the user's locally held seed into the canonical `nsc`-style credentials document, written
atomically at mode `0600`:

```sh
basil issue-nats-creds \
  --jwt-file device-42.jwt \
  --seed-file device-42.seed \
  --out-file device-42.creds
```

The two authorities stay separate on purpose: the account issuer seed never left the backend, and
the user seed never touched Basil.

## Every mint is on the record

Each mint writes one structured audit event: the kernel-attested presenter, the resolved subject,
`op: mint`, the issuer key, and the decision, for denials as well as allows. `nsc` has no
equivalent; here, "who minted credentials for what, and when" is a `grep` over `audit.jsonl`. See
[Audit logs](/operations/audit-logs/).

## Revocation: be honest about it

`basil revoke` does **not** apply to NATS JWTs. It maintains the SPIFFE JWT-SVID deny-list, keyed
by `(trust_domain, jti)`, and nats-server never consults that list (see
[Revocation](/operations/revocation/)).

For NATS users your controls are:

- **Short TTLs plus re-minting.** This is the primary control. A leaked one-hour user JWT is a
  one-hour problem; the enrollment service simply stops re-minting for that user. Prefer the
  shortest TTL your reconnect behavior tolerates.
- **Account-claim revocations.** The NATS-native mechanism is the account JWT's
  `nats.revocations` map (user public key, or `*`, to a Unix timestamp; see the
  [NATS JWT reference](/reference/nats-jwt-reference/)). You can publish an updated account JWT
  carrying that map by building the full account claim document and signing it with
  `sign-nats-jwt` against the custodied operator key; distributing the updated account JWT to your
  nats-server (its account resolver) is a NATS-side step outside Basil.

If you need push-style revocation with sub-TTL latency, that is the trade-off to weigh against
`nsc`, which has the same property: NATS revocation is claim-distribution, not a broker RPC.

{% note(title="If anything failed") %}
Run `basil doctor --keys -c <config>` to validate the catalog, policy, and the authenticated
per-key probe, and see [Troubleshooting](/troubleshooting/) for the error reference. For a denied
mint, `basil explain --subject svc.enroll --op mint --key nats.account` shows the matcher's view.
{% end %}

## Where to go next

- [NATS integration](/clients/nats/): the full NATS surface, validation, signing keys, and xkey boxes.
- [NATS JWT reference](/reference/nats-jwt-reference/): every claim the account and user documents carry.
- [NATS bridge](/clients/nats-bridge/): couriering sealed invocations over NATS itself.
- [Importing (BYOK) keys & sets](/operations/importing-byok/): the wrapped import path in detail.
