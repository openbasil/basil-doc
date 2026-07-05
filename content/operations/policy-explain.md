+++
title = "Policy explain / dry-run"
weight = 70
+++

# Policy explain / dry-run

`basil explain` answers "would this request be allowed, and why?" **without performing it**. By
**default** it is an *offline* dry-run: it loads *only* the catalog and policy JSON (no sealed bundle,
no backend I/O, no socket, no secret material), builds the real policy decision point, and evaluates a
proposed subject/op/key tuple through the same matcher the live broker enforces with. There is no
second copy of the matching logic, so a dry-run can never report a different answer than enforcement;
default-deny holds exactly as it does at request time.

Add `--live` to instead query the **running** broker's serving generation over the global `--socket`
(a gated admin RPC — see the grant below). The two modes are one verb: use the default offline path
for pre-deploy review of proposed files; use `--live` when an operator needs to interrogate the
currently serving generation. `--effective` (preview every grant for a subject) is offline-only and
conflicts with `--live`.

## Live explain grant

Live explain can enumerate policy reachability, so it is gated by a dedicated broker-admin op. It is
not implied by data-plane grants, `op:reload`, or wildcard `*`. Grant `op:explain` explicitly over
the reserved target `broker.explain`:

```json
{
  "schemaVersion": 2,
  "subjects": {
    "svc.explain": { "allOf": [ { "kind": "unix", "uid": 4242 } ] }
  },
  "rules": [
    { "id": "broker-admin-explain",
      "subjects": ["svc.explain"],
      "action":   ["op:explain"],
      "target":   ["broker.explain"] }
  ]
}
```

```nix
services.basil.policy.subjects."svc.explain" = {
  allOf = [ { kind = "unix"; uid = 4242; } ];
};
services.basil.policy.rules = [
  { id = "broker-admin-explain";
    subjects = [ "svc.explain" ];
    action    = [ "op:explain" ];
    target    = [ "broker.explain" ]; }
];
```

Run the command under the granted identity; Basil attests the caller through Unix-socket peer
credentials.

```sh
basil explain --live --subject svc.grafana --op get --key grafana.admin_password --json
```

## The subcommand & flags

```sh
basil explain --catalog catalog.json --policy policy.json \
  --subject svc.grafana --op get --key grafana.admin_password [--json]
```

| Flag | Meaning |
| --- | --- |
| `--catalog` / `--policy` | The exported catalog & policy JSON the offline dry-run reads (also honored from a `--config` TOML or `BASIL_CATALOG`/`BASIL_POLICY`). The bundle is **not** needed. Ignored on the `--live` path, which reads the broker's serving generation. |
| `--subject` | The registered policy subject to evaluate. Offline explain evaluates the subject name directly; live requests resolve a caller to a subject before enforcement. |
| `--op` | One policy op token (the full list follows this table). Required unless `--effective`. |
| `--key` | The catalog key/target to evaluate. Required unless `--effective`. |
| `--effective` | Preview **every** `(key, op)` the subject is granted across the whole catalog (ignores `--op`/`--key`). Offline-only; conflicts with `--live`. |
| `--live` | Query the **running** broker's serving generation over the global `--socket` instead of the offline file dry-run. Needs the `explain` admin grant (above). |
| `--json` | Emit a stable machine-readable object instead of human-readable text. |

The `--op` tokens are: `get`, `list`, `get_public_key`, `verify`, `sign`, `sign_nats_jwt`,
`validate_nats_jwt`, `encrypt`, `decrypt`, `encrypt_nats_curve`, `decrypt_nats_curve`, `mint`,
`validate`, `set`, `rotate`, `import`, `new_key`, `use_software_custody`, `reload`, `explain`, and
`revoke`.

{% note(title="Subjects are the authorization boundary") %}
Runtime authorization first resolves the attested caller to a configured **subject**. The `uid`,
`gid`, and `pid` stay as authentication evidence and presenter context in the audit trail; the PDP
itself evaluates `(subject, op, key)`.
{% end %}

Explain evaluates a registered policy subject, not a raw uid/gid principal. `--subject`, Rust
`client.explain(subject, op, key)`, and Go `client.Explain(ctx, subject, op, key)` all name the
subject to evaluate. The `--effective` view uses the same subject input and returns the grants
reachable by that subject, not by a raw Unix principal expression.

{% caution(title="Software custody is an explicit second grant") %}
For software-custodied PQC keys, explain both the underlying operation and `use_software_custody`.
That op is intentionally not implied by wildcard grants, even root `*/*`, because it authorizes
materializing a PQC private seed in the broker process for one operation.
{% end %}

## Allow: the matched rule

```sh
$ basil explain --catalog catalog.json --policy policy.json \
    --subject svc.grafana --op get --key grafana.admin_password
ALLOW  subject svc.grafana  get  grafana.admin_password  (via subject:svc.grafana)
  matched rule `grafana-reader`: action `role:reader` over target `grafana.admin_password`
```

When the granting subject definition combines several proofs with `allOf`, the matched rule still
names the canonical subject. The rule provenance tells you which subject the policy granted, not the
raw uid/gid predicate that happened to resolve it:

```sh
ALLOW  subject svc.app  sign  app.signing_key  (via subject:svc.app)
  matched rule `app-signer`: action `role:signer` over target `app.signing_key`
```

With `--json`:

```json
{
  "subject": "svc.grafana",
  "op": "get",
  "key": "grafana.admin_password",
  "decision": "allow",
  "via": "subject:svc.grafana",
  "matched_rule": {
    "rule": "grafana-reader",
    "via": "subject:svc.grafana",
    "action": "role:reader",
    "target": "grafana.admin_password",
    "subject": "svc.grafana"
  }
}
```

A world-readable (`class: public`) read is allowed with `"via": "public_class"` and
`"matched_rule": null`. No policy *rule* produces it.

## Deny: the reason (default-deny)

```json
{
  "subject": "svc.unknown",
  "op": "get",
  "key": "grafana.admin_password",
  "decision": "deny",
  "reason": "not_permitted"
}
```

| `reason` | Meaning |
| --- | --- |
| `not_permitted` | No policy grant matches this (subject, op, key): plain default-deny. |
| `not_writable` | A write op against a key whose `writable: false`: the write hard-cap denies regardless of any policy grant. |
| `unknown_key` | The key is not in the catalog (reported first, so the tool does not leak which finer check would otherwise have failed). |

## JSON schema (single tuple)

| Field | Type | Meaning |
| --- | --- | --- |
| `subject` | string | The evaluated policy subject. |
| `op` | string | The evaluated op token. |
| `key` | string | The evaluated catalog key. |
| `decision` | string | `allow` or `deny`. |
| `via` | string | (allow only) The scope that granted it: `subject:<name>` or `public_class`. |
| `matched_rule` | object / null | (allow only) The granting rule: `rule` (id), `via`, `action`, `target`, and matched `subject`. `null` for a `public_class` allow. |
| `reason` | string | (deny only) `not_permitted` / `not_writable` / `unknown_key`. |

The `--effective` view emits `{"subject":…,"effective":[{"key","op","via","rule"},…]}`; `rule` is
`null` for a world-readable public-class read.

{% best() %}
Before merging a catalog/policy change, run `basil explain` in CI against the *proposed* files
for the tuples you care about (the service identities that must keep working and the ones that must
stay denied), and assert on the `--json` `decision`. Because `explain` runs the identical matcher the
broker enforces with, a green dry-run is a real guarantee, not an approximation. Pair it with
[`basil doctor`](/operations/doctor/) so a change that would be rejected at load *or* would
change an authorization outcome is caught pre-merge. Use `--effective --json` to diff the full granted
`(key, op)` set for an identity across the old and new policy.
{% end %}

## Where to go next

- [The policy](/configuration/policy/): the rules `explain` evaluates.
- [Hot reload](/operations/hot-reload/): apply a reviewed change to the serving generation.
- [Doctor](/operations/doctor/): the environment-level preflight companion.
