+++
title = "What is Basil?"
weight = 10
+++

# What is Basil?

> **Basil is a host-local secrets broker: your app never touches the key.** The kernel attests who's
> calling, a default-deny policy decides, the key is used where it lives (OpenBao/Vault, KMS, or a
> sealed local store), and every operation is audited.

**Basil** is a small agent that lets your app use secrets without needing to touch them.
Basil sits in front of a secrets backend like HashiCorp Vault or KMS,
and provides gRPC services to your app over a local Unix socket: attested identity,
managed authorization, and crypto operations.

Basil is designed to be easy to use and safe, always using secure defaults
and strict API validation. It is built on open standards (SPIFFE, COSE, NATS),
written in Rust for memory safety and reliability, and includes post-quantum cryptography (PQC).

## The problem

Your app needs a secret key to sign or decrypt some data, and you need to safely deliver
the key to your app. If the key is on disk, it risks being read, leaked, or backed up by
accident, and you can't easily log who accessed it or when. You could put the key in a vault,
but then you need another secret to open the vault, and *that* secret needs to be delivered,
protected, and rotated.

Basil removes both risks. With the default in-place backend, your app and Basil never touch secret
bytes at all:

- When a service needs to sign or decrypt, Basil asks the backend to perform the operation in
  place. The key is used where it lives and never crosses the socket.
- When a service needs to prove who it is, Basil mints a credential that expires in minutes, not
  months.
- Before Basil does anything, it confirms the identity of the connecting process, guaranteed by
  the kernel.

The result: fewer secrets that can be stolen, short-lived ones where you can't avoid them, and a
clear, auditable answer to *"who's asking for what, and are they allowed?"*

## What's in the name

Basil does four things, and they spell its name.

### 🛡️ Attestation: Basil knows who's calling

When requests arrive over a local Unix socket, Basil establishes the process's identity from the OS
kernel using `SO_PEERCRED`: the process user, group, and PID. No password or bearer token
is used, so it can't be leaked. For attestation to work, each workload must run
with its own uid.

### 🔑 Secrets: used in place, not handed out

Sign, verify, encrypt, decrypt, store, rotate. With a Vault or KMS backend,
keys stay in the vault and are used *in place*; Basil brokers the operation, not the key. The
API removes common crypto footguns by construction: Basil owns the AEAD encryption nonces, so a caller can't
reuse one by accident.

### 🪪 Identity: open SPIFFE standard

Basil issues identity certificates using the open [SPIFFE](https://spiffe.io)
standard (X.509 and JWT *SVIDs*), so services can prove their identity
without credentials baked into config or environment.
The standard **SPIFFE Workload API** is validated using an interop test suite with `rust-spiffe`
and `go-spiffe` clients.

### ⏳ Leases: authority that expires on its own

Basil mints **short-lived, narrowly-scoped** credentials (NATS JWTs, SPIFFE tokens) that expire
on their own.

## What Basil is *not*

Basil doesn't replace your secret backend or your identity infrastructure. It sits in front of them
on a single host and changes who holds what. It augments the backend; it doesn't remove it. See
[Comparisons](/introduction/comparisons/) for how Basil relates to talking to Vault directly,
SPIFFE/SPIRE, and systemd credentials.

{% best(title="One uid per workload") %}
A workload's uid *is* its identity. Give each app or service its own uid (and/or gid). Policy rules
grant operations to uids, and the kernel vouches for them, so two services that share a uid share
every grant, and you can't tell them apart in the audit log.
{% end %}

## Where to go next

- [How it works](/introduction/how-it-works/): the request path and the two gates every call passes.
- [Backends & custody](/introduction/backends-and-custody/): in-place vs. materialize-to-use.
- [Quickstart](/getting-started/quickstart/): see Basil work end to end in under five minutes.
