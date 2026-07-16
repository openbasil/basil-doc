+++
title = "The policy (authorization)"
weight = 30
+++

# The policy (authorization)

The policy is a **default-deny** allow-list. Basil first proves which local workload presented the
request, resolves exactly one named subject, and only then checks that subject's grants. A rule maps
subjects to an *action* (an operation or role) on a *target* (a key or key glob).

Schema 3 separates workload classification from evidence matching. This prevents an alternative
match branch, signed claim, or caller-controlled field from selecting a more privileged workload
domain.

![Schema 3 authorization narrows a request through domain resolution, same-domain subject matching,
unique-subject resolution, and grant evaluation. Zero matches, overlapping matches, and unavailable
evidence all fail closed.](/images/schema-3-authorization-flow.png)

## Policy document shape

The top-level agent configuration selects configuration corpus schema 3. The referenced policy file
contains `"schema": "policy"`; it has no independent version field.

```json
{
  "schema": "policy",
  "subjects": {
    "svc.web": {
      "domain": "host-process",
      "match": {
        "all": [
          { "process.uid": 9001 },
          { "process.gid.supplementary": 110 }
        ]
      }
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
      "users": { "9001": "svc-web" },
      "groups": { "110": "web-signers" }
    },
    "memberships": { "9001": [9001, 110] }
  }
}
```

The bootstrap selects the complete corpus version and names the policy file:

```toml
schema = "agent"
schemaVersion = 3

[import]
catalog = "/etc/basil/catalog.json"
policy = "/etc/basil/policy.json"
bundle = "/var/lib/basil/credentials.age"
```

Unknown fields, mixed schema shapes, missing domains, empty expressions, malformed predicate values,
and references to undefined subjects or roles reject the complete candidate policy. A failed reload
leaves the active generation serving.

## Authorization domains

Every subject declares exactly one `domain` outside its `match` expression. Basil independently
classifies the presenter and considers only subjects with the same domain.

| Domain | Workload established by | Matching policy evidence |
| --- | --- | --- |
| `host-process` | A local process that is affirmatively outside a more-specific supported manager | Process credentials, executable content, invocation signature key |
| `systemd-unit` | A correlated systemd `.service` unit | Systemd unit or template, numeric process credentials, executable content, invocation signature key |
| `container` | A correlated supported container runtime | Compose, runtime, OCI signer, process, systemd, executable, and invocation-key evidence |

Domain resolution uses most-specific precedence: verified container evidence, then verified systemd
service evidence, then affirmative host-process evidence. A runtime, namespace, cgroup, or systemd
lookup failure cannot downgrade a request to `host-process`. Unsupported or ambiguous isolation
fails closed.

{% note(title="Evidence-provider status") %}
Schema 3 parsing, the host-process `SO_PEERCRED` compatibility path, recursive evaluation,
unique-subject resolution, and invocation signature-key binding are implemented. Pinned credential
slot revalidation and live systemd, executable-object, Compose, container-runtime, and OCI-signer
providers remain roadmap items in the feature matrix. Predicates that require unavailable evidence
evaluate to `unavailable` and cannot grant authority.
{% end %}

## Recursive `all` and `any`

Each `match` node contains exactly one key. That key is `all`, `any`, or one typed leaf predicate.
Groups may nest, which supports policies such as "approved container and (approved signer or exact
service plus uid)." Negation, exclusive-or, threshold operators, and empty groups are invalid.

```json
"match": {
  "all": [
    { "runtime.kind": "podman" },
    {
      "any": [
        { "oci.signer": "release-images" },
        {
          "all": [
            {
              "compose.service": {
                "realm": "ci-podman",
                "project": "build",
                "name": "worker"
              }
            },
            { "process.uid": 10001 }
          ]
        }
      ]
    }
  ]
}
```

Leaves and groups evaluate to `match`, `no-match`, or `unavailable`:

| Expression | `match` | `no-match` | `unavailable` |
| --- | --- | --- | --- |
| Leaf | Trusted evidence equals the predicate | Trusted evidence differs | Evidence could not be established safely |
| `all` | Every child matches | At least one child is `no-match` | No child is `no-match`, and at least one is unavailable |
| `any` | At least one child matches | Every child is `no-match` | No child matches, and at least one is unavailable |

Only `match` can establish a subject. An unavailable branch may be masked by a conclusive result:
`all(no-match, unavailable)` is `no-match`, while `any(match, unavailable)` is `match`. Missing
evidence never becomes proof of a negative claim.

A subject expression may contain at most 8 nested groups and 64 leaves. `basil doctor` warns above
depth 4 or 16 leaves because a valid expression can still be difficult to audit. Single-child groups
are accepted for generated policy.

## Evidence predicates

Predicate names are typed and namespaced. Compound values accept only the fields shown.

| Predicate | Value | Valid domains |
| --- | --- | --- |
| `process.uid` | UID all caller-visible credential slots must equal | All |
| `process.uid.real`, `.effective`, `.saved`, `.filesystem` | UID for one credential slot | All |
| `process.gid` | GID all primary-group credential slots must equal | All |
| `process.gid.real`, `.effective`, `.saved`, `.filesystem` | GID for one credential slot | All |
| `process.gid.supplementary` | Required supplementary GID membership | All |
| `process.executable.digest` | `sha256:` plus 64 lowercase hexadecimal digits | All |
| `systemd.unit` | `{ "name": "worker@one.service", "managerUser": 1000 }` | `systemd-unit`, `container` |
| `systemd.template` | `{ "name": "worker@.service", "managerUser": 1000 }` | `systemd-unit`, `container` |
| `compose.service` | Exact `{ "realm", "project", "name" }` strings | `container` |
| `compose.project` | Exact `{ "realm", "project" }` strings | `container` |
| `runtime.kind` | `docker` or `podman` | `container` |
| `oci.signer` | Name of the OCI signer policy that verified the immutable image digest | `container` |
| `invocation.signature-key` | Exact `{ "algorithm", "public" }` signing key | All |

`systemd.unit` names one concrete canonical `.service` unit. `systemd.template` names a canonical
template such as `worker@.service`. Omitting `managerUser` means the system manager. Adding it binds
a per-user manager owner. Unit configuration such as `User=` does not establish process credentials;
combine the systemd predicate with `process.uid` or `process.gid` when those credentials matter.

`compose.service` matches realm, effective project, and service together. `compose.project` matches
realm and project. No partial object, glob, or label-only identity is accepted. `oci.signer` names a
configured policy result after image-digest verification; a tag or repository string alone is not
signer evidence.

### Numeric and symbolic local accounts

Process UID/GID values accept an integer. In the `host-process` domain they may also use a
nonnumeric local username or group name. Basil reads `/etc/passwd` and `/etc/group` atomically while
loading policy, compiles the name to its numeric ID, and resolves it again only on reload.

Symbolic process credentials are rejected in `systemd-unit` and `container` subjects because the
agent host's account database cannot define another namespace. Use observed numeric IDs there. The
one retained symbolic exception is `systemd.unit.managerUser` or
`systemd.template.managerUser`, which identifies the host owner of a user systemd manager.

Missing, duplicate, malformed, numeric-looking string, or out-of-range account entries reject the
candidate policy. Resolution reads the local files directly and does not invoke network-dependent
NSS services.

## Exactly one subject

Basil evaluates every eligible subject against one immutable evidence snapshot before it checks key
existence, rule order, public-class access, or admin targets.

| Eligible subject results | Resolution | Authorization outcome |
| --- | --- | --- |
| Exactly one `match`; all others `no-match` | Named subject resolved | Continue to grants |
| No matches; all `no-match` | No subject | Deny |
| Any `unavailable` candidate that is not conclusively `no-match` | Indeterminate | Fail closed |
| Two or more matches | Ambiguous | Deny |

Matching subjects never merge their grants. If several evidence alternatives should share one
authority, put them inside one subject's `any` expression. A signed issuer or subject claim may be
checked for equality after independent resolution; it cannot select one of two overlapping subjects.

{% caution(title="Overlaps deny even when grants are identical") %}
Two subjects that match the same request are ambiguous. Basil denies before comparing their rules.
Use `any` inside one named subject for intentional alternatives.
{% end %}

## Public-class access still resolves a subject

`class: public` implicitly permits `get` and `get_public_key` after one subject resolves, subject to
catalog hard caps. It does not provide anonymous access. Schema 3 removes `unauthenticatedSubject`
and the `kind: unauthenticated` principal.

A caller with no resolvable local workload domain, no matching subject, unavailable evidence, an
overlap, or a signed-claim mismatch cannot read public-class material. Define a narrow subject from
observed local evidence for a client that only needs public keys.

## Sealed invocations bind presenter and signer

A signature verifies invocation evidence. It cannot establish the local workload domain. Basil also
classifies the process that presents the sealed request, such as a NATS bridge, and resolves one
subject from the combined local and signature evidence.

```json
"sealed.publisher": {
  "domain": "host-process",
  "match": {
    "all": [
      { "process.uid": 9100 },
      {
        "invocation.signature-key": {
          "algorithm": "nats-nkey",
          "public": "UANATS_PUBLIC_NKEY"
        }
      }
    ]
  }
}
```

Every successful sealed-invocation expression path must include a matching
`invocation.signature-key` leaf. The supported algorithms are `ed25519`, with a base64url raw
Ed25519 public key, and `nats-nkey`, with a public NATS NKey. Malformed public material rejects the
policy without logging the key; audit output uses a non-reversible fingerprint.

The resolved compound subject needs `op:decrypt` on the broker request-encryption key and the
operation-specific grant on the inner target. See [Sealed invocations](/clients/sealed-invocations/)
for the COSE checks that run around policy evaluation.

## Rules, roles, and hard caps

A rule's action may name a role (`role:signer`) or an operation directly (`op:sign`). Roles must be
defined before use. Rules list already resolved subject names; they do not combine subject evidence
or authority.

A target of `*` or bare `**` is accepted only when every referenced subject sets
`breakGlass: true`. Key `writable` settings and operation-specific restrictions remain hard ceilings
above the allow-list. Software-custodied post-quantum keys also require
`op:use_software_custody`; wildcard expansion deliberately excludes it.

NATS operations use separate tokens because minting, validation, JWT signing, and curve-box access
are distinct authorities. Grant only the operation and key each workload needs.

## NixOS source policy

The NixOS module adds `schema: policy` during export. Declare the schema-3 subject shape directly:

```nix
services.basil.policy.subjects."svc.web" = {
  domain = "host-process";
  match.all = [
    { "process.uid" = 9001; }
    { "process.gid.supplementary" = 110; }
  ];
};

services.basil.policy.rules = [
  {
    id = "web-can-sign";
    subjects = [ "svc.web" ];
    action = [ "role:signer" ];
    target = [ "web.tls.signing_key" ];
  }
];
```

`services.basil.policy.unixSubjects` remains a source-level shortcut for simple host-process
UID/GID subjects. The exported policy still contains a mandatory `domain`, recursive `match`, and
numeric credential leaves.

## Where to go next

- [Policy explain / dry-run](/operations/policy-explain/): inspect grants without performing an operation.
- [Sealed invocations](/clients/sealed-invocations/): bind a local presenter and remote signing key.
- [Threat model](/introduction/threat-model/): understand the evidence and host trust boundaries.
- [Approvals & change control](/configuration/approvals/): the `writable` hard cap above the allow-list.
