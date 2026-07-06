+++
title = "Make it your own"
weight = 40
+++

# Make it your own

[`basil-example.nix`](https://github.com/openbasil/basil/tree/main/examples/nix) is a self-contained catalog + policy + NixOS module + foreground runner. It's
the fastest way from "the fixture works" to "Basil runs *my* keys for *my* services." Copy it and edit
two things:

- **`keys`**: the catalog of what exists (each key's class, algorithm, backend engine, and path).
- **`subjects` + `rules`**: who may do what to which key, with subjects resolved from uid/gid
  evidence.

{% best(title="Give each app or service its own uid (and/or gid)") %}
The uid is usually the workload's strongest local proof. Policy rules grant operations to subjects,
and the kernel vouches for the uid/gid evidence that resolves those subjects. **Two services sharing a
subject share authority**. Use systemd `User=`/`Group=` (or `DynamicUser=`) so each service gets a
distinct identity.
{% end %}

## Run it

After creating a real sealed bundle for your backend credential with `basil bundle create …`:

```sh
nix run -f ./basil-example.nix run
```

## Why Nix

On NixOS, the catalog and policy are declarative, versioned, and immutable. You write policy in a
friendlier source form (where a subject can be backed by a symbolic user/group name like `svc-web`),
and the exporter resolves each name to its numeric uid/gid and emits the JSON Basil actually reads.

Configuration and policy are checked **twice**: at build time (when rules are converted to JSON) and
again at runtime, so a malformed or unsatisfiable policy fails closed before the broker serves. Driving
catalog and policy from version control also gives you a reviewable **approval gate**: every change to
*who can do what* goes through code review before it reaches the broker. See
[Approvals & change control](/configuration/approvals/).

## Where to go next

- [The catalog](/configuration/catalog/): the fields you set on each key.
- [The policy](/configuration/policy/): roles, rules, and source-vs-exported policy.
- [Migrating from sops-nix to Basil](/getting-started/sops-nix-to-basil/): move an existing NixOS
  secret one step at a time.
- [Configuration overview](/configuration/overview/): the daemon startup config.
