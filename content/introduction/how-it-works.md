+++
title = "How it works"
weight = 20
+++

# How it works

Basil runs as a small service connecting to a backend vault or key store. It listens on one local
socket and exposes two APIs:

- a **Workload API** that issues identity documents (SPIFFE SVIDs), and
- a **broker API** for secrets and crypto: `sign` / `verify` / `encrypt` / `decrypt` / `get` / `set`
  / `rotate` / `list` / `mint`.

![Basil request flow: a workload (or the Basil CLI) calls Basil over a local Unix socket; Basil attests the caller from the kernel, checks a default-deny policy, and brokers the operation against a backend, recording every decision to an audit log. In-place transit backends (OpenBao, Vault, AWS KMS, GCP KMS) keep keys in place; store-only backends (db-keystore, 1Password) are materialize-to-use, holding the key in memory for one operation.](/images/architecture.png)

## The two gates

Every call passes through two checks before Basil passes anything to the backend.

### 1. Who are you? (attested identity)

Basil attests the caller from the kernel using `SO_PEERCRED`. The kernel returns the uid, gid, and pid of the
process on the other end of the socket. The caller id can't be impersonated: a process cannot
claim a uid it isn't running as, and there's no token to forge. This is why each workload should run
under its own uid (systemd with `User=`/`Group=` or `DynamicUser=`).

### 2. Are you allowed? (authorization)

Basil checks a declarative, **default-deny** policy that maps a resolved subject to the exact
operations it may run on the exact keys it may touch. Nothing is permitted until a rule grants it.

After verifying identity and authorization, the allow or deny decision is recorded in the **audit log**.

{% note(title="The decision binds to the subject") %}
Authorization resolves the kernel-attested uid/gid evidence to a configured subject, then evaluates
that subject against policy. The pid and presenter uid/gid are recorded for the audit trail but are
not the PDP tuple.
{% end %}

## The request lifecycle

1. A workload, or the `basil` CLI, opens the Unix socket and makes a gRPC call.
2. Basil reads the peer's uid/gid/pid from the kernel.
3. The policy decision point evaluates `(subject, op, key)` against the loaded policy. Policies are
   default-deny, so all rules are allow rules.
4. On allow, Basil routes the request to the backend and engine declared in the catalog.
5. On a transit backend (Vault-compatible or cloud KMS), the operation (sign, encrypt, issue a
   cert) runs inside the backend and the key never moves. On a store-only backend (`db-keystore` or
   `1password`), the key is briefly materialized in the agent for the one operation, then wiped.
6. The result (a signature, a ciphertext envelope, a minted credential) is returned to the client.
7. The decision and its reason are appended to the audit log.

## Basil configuration

The Basil agent requires three inputs, specified in a TOML config file, as CLI flags, or as
environment variables.

| Input             | What it is                                                                                            |
| ----------------- | ----------------------------------------------------------------------------------------------------- |
| **Catalog**       | The inventory of keys: name, path, algorithm, and which backend/engine holds it.                      |
| **Policy**        | A default-deny allow-list mapping resolved subjects to operations on keys.                            |
| **Sealed bundle** | The encrypted credential that lets the broker reach the backend, opened at startup by an unlock slot. |

Validate the config and input files with the `basil` CLI; `basil agent` validates them again at
startup. The [Configuration](/configuration/overview/) section covers each in depth.

## Identity rotation, natively

Workload API X.509-SVID streams reissue leaf material on the configured `svid-ttl-secs` cadence, so
standard SPIFFE clients (such as `rust-spiffe`) observe rotation without any Basil-specific TLS
adapters. Short TTLs are the design: an un-revoked credential stays valid for minutes, not months.

## Where to go next

- [Backends & custody](/introduction/backends-and-custody/): supported backends, and how keys are held.
- [Configuration overview](/configuration/overview/): the startup config and how to run the daemon.
- [The policy](/configuration/policy/): how authorization rules are written and evaluated.
