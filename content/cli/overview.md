+++
title = "CLI overview"
weight = 10
+++

# CLI overview

There is one binary, `basil`. It is both the broker daemon and the client/operator CLI, split into
subcommands. Two broad groups:

- **Daemon & offline commands** run the broker or work on config files directly (no running broker
  needed).
- **Client commands** connect to a running broker over its Unix socket and authorize by your
  **kernel-attested uid/gid**.

{% note(title="The CLI cannot impersonate") %}
Client commands take a global `--socket <path>` and are authorized by the caller's real uid/gid, read
from the kernel (`SO_PEERCRED`). Running the CLI as a different user is exactly what scopes a request to
that user's grants. Use systemd `User=`/`Group=` or `runuser -u <svc>` to act as a service identity.
{% end %}

## Daemon & offline commands

| Command | Purpose |
| --- | --- |
| `basil agent` | Run the broker daemon. |
| `basil init` | First-run scaffolding: write a starter catalog + least-privilege policy + config. See [First run](/getting-started/first-run/). |
| `basil bundle` | Create, update, verify, review, and promote sealed credential bundles. See [Unlock & the sealed bundle](/configuration/unlock-and-bundle/). |
| `basil explain` | Offline policy dry-run by default: "would this be allowed, and why?" `--live` queries the running broker. See [Policy explain](/operations/policy-explain/). |
| `basil doctor` | Preflight diagnostics before the daemon starts: validate catalog + policy, enforce capability + invocation bindings, and (with `--keys`) probe the backend for declared keys. See [Doctor](/operations/doctor/). |

## Client & operator commands

Run against a live broker over `--socket`. They fall into:

- **Status & probes**: `status`, `health`, `ready`.
- **Keys**: `new-key`, `import`, `import-set`, `rotate`, `list`.
- **Crypto**: `sign`, `verify`, `encrypt`, `decrypt`.
- **Secrets/values**: `get`, `set`.
- **Minting & identity**: `mint-jwt`, `mint-nats-user`, `sign-nats-jwt`, `issue-nats-creds`, `issue-cert`.
- **Admin** (permission-gated): `reload`, `explain`, `revoke`.

The full table, with signatures, is in the [command reference](/cli/command-reference/). What any
invocation is *allowed* to do is bounded by the caller's identity and the [policy](/configuration/policy/).

## Where to go next

- [Command reference](/cli/command-reference/): every command with its flags and signatures.
- [The policy](/configuration/policy/): what a caller's identity is actually allowed to do.
- [First run](/getting-started/first-run/): scaffold a working config with `basil init`.
