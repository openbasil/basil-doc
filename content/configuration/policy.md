+++
title = "The policy (authorization)"
weight = 30
+++

# The policy (authorization)

The policy is a **default-deny** allow-list. Nothing is permitted until a rule grants it. A rule maps
one or more **subjects** to an *action* (an op or a role) on a *target* (a key or key glob). Subjects
are named identities resolved from authenticated evidence, such as a Unix uid/gid from `SO_PEERCRED`.

```yaml
schemaVersion: 2
subjects:
  svc.web:
    allOf:
      - kind: unix
        uid: 9001

roles:
  signer:   [sign, verify, get_public_key]
  cryptor:  [encrypt, decrypt]
  reader:   [get, list, get_public_key]
  operator: [set, rotate, import, new_key]
  minter:   [mint]
  validator: [validate]
  nats_minter:    [mint, sign_nats_jwt]
  nats_validator: [validate_nats_jwt]
  nats_box:       [encrypt_nats_curve, decrypt_nats_curve]
  pqc_user:       [sign, verify, encrypt, decrypt, new_key, use_software_custody]

rules:
  - id: web-can-sign
    subjects: [svc.web]
    action:    [role:signer]
    target:    [web.tls.signing_key]
```

Basil reads the caller's real uid/gid from the kernel (`SO_PEERCRED`): there's no token to forge, and
a process can't claim a uid it isn't running as. Runtime authorization resolves that evidence to a
configured subject before the PDP evaluates any rule.

## Subjects

A policy declares its canonical subjects under `subjects`. Each subject defines exactly one matcher:
`allOf` means every listed proof must match; `anyOf` means at least one proof may match. Empty
`subjects`, empty `allOf`/`anyOf` lists, unsupported `kind` values, malformed uid/gid values, and
malformed `signature-key` public material are rejected while loading the policy.

| Principal kind    | Matches                                                    |
| ----------------- | ---------------------------------------------------------- |
| `unix` with `uid` | the caller's attested uid                                  |
| `unix` with `gid` | a gid in the caller's configured full group set            |
| `unauthenticated` | only when `unauthenticatedSubject` names this subject      |
| `signature-key`   | a configured signing key proof for sealed invocation flows |

Runtime authorization uses `unix` subjects (plus the explicit `unauthenticated` path).
`signature-key` subjects authenticate sealed invocations: `ed25519` and `nats-nkey` public material
authenticates a signed COSE message before the PDP evaluates the resulting subject.

```json
{
  "schemaVersion": 2,
  "subjects": {
    "svc.web": {
      "allOf": [{ "kind": "unix", "uid": 9001 }]
    },
    "ops.wheel": {
      "allOf": [{ "kind": "unix", "gid": 10 }]
    },
    "breakglass.root": {
      "breakGlass": true,
      "allOf": [{ "kind": "unix", "uid": 0 }]
    },
    "content.publisher": {
      "anyOf": [
        {
          "kind": "signature-key",
          "algorithm": "ed25519",
          "public": "BASE64URL_32_BYTE_ED25519_PUBLIC_KEY"
        },
        {
          "kind": "signature-key",
          "algorithm": "nats-nkey",
          "public": "UANATS_PUBLIC_NKEY"
        }
      ]
    }
  },
  "roles": {
    "signer": ["sign", "verify", "get_public_key"]
  },
  "rules": [
    {
      "id": "web-can-sign",
      "subjects": ["svc.web"],
      "action": ["role:signer"],
      "target": ["web.tls.signing_key"]
    }
  ],
  "config": {
    "names": {
      "users": { "9001": "svc-web", "0": "root" },
      "groups": { "10": "wheel" }
    },
    "memberships": {
      "9001": [9001]
    }
  }
}
```

A rule's action may name a role (`role:signer`) or an op directly (`op:sign`). A role must be defined
in the `roles` table before a rule references it: the loader rejects a rule pointing at an undefined
role, so the example above declares `signer` in `roles` for its `role:signer` rule to resolve.

{% note(title="Why subjects are named") %}
Rules grant to stable names like `svc.web`, not directly to uid/gid predicates. The audit log can then
say the actor was `svc.web` while still recording the presenter as `svc-web(9001)` and the proof as
`unix_peercred:svc.web`.
{% end %}

## Source vs. exported policy

You write policy in a friendlier source form (typically Nix), where subject definitions can refer
to local user/group names for convenience. The exporter resolves those names to numeric uid/gid values
and emits the JSON Basil actually reads:

- every Unix subject matcher becomes numeric (`uid: 9001`, `gid: 10`);
- every rule names subjects with `subjects: ["name"]`;
- a `config.names` table records the numeric→name mapping;
- `config.memberships` records the full uid→gid group set Basil uses for group subjects.

At runtime, the kernel-attested uid/gid are authentication evidence. Basil resolves that evidence to a
single subject, then rules grant to the subject. The loaded policy is rejected if a rule references an
undefined subject, if a subject matcher is empty, or if the unauthenticated path is configured
inconsistently.

Export policy as `schemaVersion: 2`, declare subjects once
under `subjects`, and list those names from every rule with `subjects: [...]`.

In Nix, declare canonical subjects directly with `services.basil.policy.subjects` and refer to those
names from `services.basil.policy.rules[*].subjects`. Use `policy.unixSubjects` only as a source-level
shortcut for generated Unix uid/gid subjects; the JSON export still contains `schemaVersion: 2`,
numeric `unix` principals, `subjects`, `rules[*].subjects`, `config.names`, and
`config.memberships`.

{% note() %}
This means a host's name→uid mapping is fixed at export time. If you rename a service or its uid
changes, re-export the policy so the numeric subject matchers (and the presenter names in your logs)
stay in sync with the system.
{% end %}

## Unauthenticated subjects

Anonymous access is disabled unless policy opts in with `unauthenticatedSubject`. The configured name
must refer to a subject whose matcher contains `kind: "unauthenticated"`; the loader rejects an
unauthenticated principal anywhere else.

```json
{
  "schemaVersion": 2,
  "unauthenticatedSubject": "guest",
  "subjects": {
    "guest": {
      "anyOf": [{ "kind": "unauthenticated" }]
    }
  },
  "rules": [
    {
      "id": "guest-can-read-public-identities",
      "subjects": ["guest"],
      "action": ["op:get_public_key"],
      "target": ["identity.public.**"]
    }
  ]
}
```

{% best(title="One uid per workload") %}
A workload's subject is usually resolved from its uid. Give each service its own uid (and/or gid) via
systemd `User=`/`Group=` (or `DynamicUser=`). Two services that share the same subject proof share
every grant; use distinct subject definitions so the audit trail can distinguish them.
{% end %}

{% caution(title="The * (any-key) target") %}
A rule whose target is `*` must grant only to subjects marked `breakGlass: true`. Basil rejects an
any-key grant when any referenced subject lacks that marker. Keep break-glass subjects to genuine
operator recovery, and prefer naming the exact keys.
{% end %}

## Operation-specific grants

NATS has dedicated op tokens because minting a user JWT, validating a presented JWT, and decrypting a
NATS curve box are different authorities. Grant `sign_nats_jwt` on issuer keys, `validate_nats_jwt`
on catalog signers used as trust roots, and `encrypt_nats_curve` / `decrypt_nats_curve` on
`class=sealing`, `keyType=x25519` xkeys.

The NATS bridge presenter is not policy-gated. There is no `invoke` op (a policy naming one fails to
load), and `InvocationService.Invoke` authorizes the **actor** inside the sealed message, not the Unix
process that couriered it. The actor is the `signature-key` subject that signed the COSE request; it
needs `op:decrypt` on the broker's request-encryption key to open the sealed request, plus whatever op
the inner operation requires on its own target key (for example `op:sign` on a signing key). "invoke"
survives only as an audit label on the resulting decision.

Software-custodied PQC keys require `op:use_software_custody` in addition to the underlying
operation. The op is intentionally excluded from wildcard expansion, so a root `*/*` rule does not
silently grant authority to materialize PQC private seeds in the broker process. Add it only on the
specific ML-DSA/ML-KEM keys whose software custody you intend to use.

## Signature-key subjects

`signature-key` subjects authenticate bridged sealed invocation COSE messages. The public key
material lives in policy, not in the catalog, because the proof identifies the actor; catalog keys
still own the operation target and custody.

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
      "id": "publisher-can-use-sealed-signing",
      "subjects": ["content.publisher"],
      "action": ["op:decrypt", "op:sign"],
      "target": ["broker.request_encryption.2026q3", "publisher.signing.2026q3"]
    }
  ]
}
```

Use `algorithm: "ed25519"` with a base64url raw Ed25519 public key, or
`algorithm: "nats-nkey"` with a public NATS NKey. Basil rejects malformed public material at load
time. See [Sealed invocations](/clients/sealed-invocations/) for the COSE profile, replay, expiry, and
audience checks that happen before policy evaluation.

## Where to go next

- [Policy explain / dry-run](/operations/policy-explain/): preview "would this be allowed, and why?".
- [Sealed invocations](/clients/sealed-invocations/): the signature-key actor and its COSE preflight.
- [NATS integration](/clients/nats/): the NATS-specific op tokens and client calls.
- [Approvals & change control](/configuration/approvals/): the `writable` hard cap above the allow-list.
