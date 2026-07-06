+++
title = "Threat model"
weight = 35
+++

# Threat model

This page states what Basil protects, what it trusts, and what it does not
defend against. Read it before you deploy Basil in a security-sensitive place,
and read it before you report a vulnerability, so we're reasoning about the same
boundaries.

Basil is a **host-local broker**. Its whole job is to change *who holds what* on
a single machine: keys stay in a backend and are used in place, callers are
attested by the kernel, and every operation is authorized and logged. That model
has clear edges, and being honest about them is part of the design.

![Basil's trust boundary on a single host. Trusted: the kernel (the trust root, via SO_PEERCRED), the Basil broker, the sealed bundle, and the audit log. The calling workload is attested but not trusted; it proves only its uid and holds no backend token. Backends are separate trust domains, trusted only for custody: in-place transit backends (OpenBao, Vault, AWS KMS, GCP KMS) never let the private key cross, while store-only backends (db-keystore, 1Password) are materialize-to-use, briefly holding the key in process for one operation. Out of scope: host or kernel compromise, backend compromise, a workload abusing what it is allowed to do, a bad policy, supply chain, and side channels. A workload calls Basil over a local socket; Basil brokers the operation to the backend; every decision is written to the audit log.](/images/trust-boundaries.png)

## What Basil protects

The assets Basil is responsible for, and the property it gives each:

| Asset                                         | Property Basil provides                                                                                            |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Private keys (signing, encryption, issuer/CA) | Used **in place** in the backend; with an in-place backend they never cross the socket or touch a workload's disk. |
| Secrets / values (`engine: kv2`)              | Fetched on demand under policy, logged, and rotatable without a rebuild. Never baked into an image.                |
| Identity issuance (SPIFFE SVIDs, NATS JWTs)   | Minted **short-lived** and narrowly scoped, so a leaked credential expires on its own.                             |
| The act of using a key                        | Authorized per call against a **default-deny** policy, and recorded in the audit log.                              |
| AEAD nonces                                   | Owned by Basil, so a caller cannot reuse or supply an invalid one.                                                 |

## Trust boundaries

Basil sits between a workload and a backend, on one host. What it trusts, and
what it does not:

| Component                     | Trusted?         | Why, and the caveat                                                                                                                               |
| ----------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| The kernel                    | Yes              | `SO_PEERCRED` is the root of caller identity. If the kernel is compromised, Basil's attestation is meaningless.                                   |
| The host (root)               | Yes              | Root can read Basil's memory, its sealed bundle, and its unlock secret. Basil does not defend a workload against a host-root compromise.          |
| The backend (OpenBao / Vault) | Yes, for custody | In-place keys live and are used there. Basil trusts it to hold and not leak key material.                                                         |
| The local socket              | Partially        | Filesystem mode/group controls who can *open* it. That is a coarse first gate; every RPC is still authorized from peer credentials and policy.    |
| The catalog and policy        | Yes, as authored | Validated at load; Basil fails closed on a malformed policy but cannot know your *intent*. A grant you wrote is honored.                          |
| The calling workload          | No               | The caller proves nothing but its uid/gid. It holds no backend credential and is allowed only what policy grants its subject.                     |
| The network                   | No               | Basil brokers over a local Unix socket, not remote callers. Its HTTP server is opt-in and only binds when the JWKS surface is explicitly enabled. |

## What Basil assumes (its trusted computing base)

For Basil's guarantees to hold, these must be true:

- **The kernel honestly reports peer credentials.** Identity is `SO_PEERCRED`,
  so a compromised kernel breaks the model.
- **The host is not root-compromised.** Basil raises the cost of stealing a key
  (there often *is* no key on the host to steal), but it is not a sandbox
  against a privileged host attacker.
- **Each workload runs under its own uid.** The uid *is* the identity. Two
  services sharing a uid share every grant.
- **The backend keeps key material.** With an in-place backend, custody is the
  backend's job; Basil never persists the private half.
- **The catalog and policy are delivered with integrity.** On NixOS they are
  declarative, versioned, and immutable, referenced at stable paths. Elsewhere
  their integrity depends on host file protections.
- **The unlock secret is held safely.** Opening the sealed bundle yields the
  backend credential. Whoever can unlock the bundle can reach the backend as
  Basil.

## Threats Basil defends against

- **Secrets sitting on disk.** With an in-place backend there is no secret file
  to read, leak, or back up by accident. Values fetched from `kv2` are delivered
  under policy and logged, not left on the image.
- **A stolen backend token.** Workloads hold no backend credential at all, so
  there is nothing to lift from a service's environment or config.
- **A caller pretending to be someone else.** Identity comes from the kernel, not
  a bearer token, so a process cannot claim a uid it is not running as.
- **A low-privilege service overreaching.** Default-deny means a service can only
  perform the exact operations policy grants its subject on the exact keys named.
  Read and write are distinct; rotating or overwriting is never implied by read.
- **Nonce-reuse crypto footguns.** Basil owns AEAD nonces, removing a whole class
  of caller mistakes.
- **Over-broad wildcard grants.** A `*` (any-key) target is rejected unless the
  subject is explicitly marked `breakGlass`, and `op:use_software_custody` is
  excluded from wildcard expansion.
- **Long-lived credential theft.** Where a raw secret is not required, Basil hands
  out a short-lived lease that expires on its own instead of a standing secret.
- **Replayed or forged bridged invocations.** Sealed invocations authenticate the
  actor by a signature-key subject and check replay, expiry, and audience before
  policy evaluation.

{% caution(title="Basil authorizes the workload, not its code") %}
Attestation proves the caller's uid/gid, not *which binary* is running under that
uid. A different program started as the same uid presents the same identity and
gets the same grants. Give each workload its own uid, keep those uids from being
reused by other software, and treat "can run code as this uid" as equivalent to
"holds this subject's authority". Richer attestation (systemd unit, container,
TPM node identity) is <span class="pill gap">roadmap</span>.
{% end %}

## What Basil does not defend against

Being explicit here is deliberate. These are out of scope:

- **A root or kernel compromise of the host.** Root can read Basil's process
  memory, its sealed bundle, and its unlock secret. Basil is not a sandbox.
- **A workload abusing what it is *allowed* to do.** If `svc.web` is granted
  `sign` on its key, a compromised `svc.web` can sign. Basil constrains *which*
  operations a subject may perform; it cannot tell a legitimate use from a
  malicious one within that grant. Narrow the grant and keep leases short.
- **Backend compromise.** If the backend that holds the keys is compromised,
  in-place custody no longer helps. Basil trusts the backend by design.
- **A bad policy.** Basil enforces the policy you wrote. An over-broad rule is
  honored. Use [policy explain](/operations/policy-explain/) to check "would this
  be allowed, and why?" before shipping.
- **The materialize-to-use exposure window.** For store-only backends
  (`db-keystore`, `1password`) Basil briefly holds the key bytes in process for
  one operation, then zeroizes them. That window does not exist for in-place
  transit backends. See [Backends & custody](/introduction/backends-and-custody/).
- **Supply-chain trust in the Basil binary itself.** Reproducible Nix builds
  reduce this, but you still choose to trust the build you run.
- **Physical attacks and side channels.** Cold-boot, timing, and hardware attacks
  are outside Basil's model.

{% caution(title="One broker, one host: availability") %}
Basil is a single host-local process and a single point of availability for the
workloads on that host. It is written to a strict no-panic rule precisely because
a crash while it holds the keys stops the world and needs manual unlock. Plan for
its restart/unlock story; it is not clustered.
{% end %}

## The attestation boundary

`SO_PEERCRED` gives Basil the caller's uid, gid, and pid.
Authorization binds to the subject resolved from uid/gid; the pid and
presenter names are recorded for the audit trail but are not the decision tuple.
Understand the limits:

- **uid reuse and sharing.** Identity is only as strong as your uid hygiene. A
  reused or shared uid dilutes the subject.
- **Not binary attestation.** As above, the same uid means the same identity
  regardless of the executable.
- **Local only.** `SO_PEERCRED` works because the caller is on the same host over
  a Unix socket. Basil does not attest remote callers, and cross-host federation
  is <span class="pill gap">roadmap</span>.

## The single-host boundary

Basil's guarantees stop at the machine. It brokers for local callers over a local
socket, and each host runs its own broker with its own policy and its own backend
reachability. There is no shared network authority to attack, and equally no
built-in multi-host identity: fleet-wide SPIFFE with federation is
<span class="pill gap">roadmap</span>, and today Basil interoperates with SPIRE
for that role rather than replacing it. See
[How it compares](/introduction/comparisons/).

## Reporting a vulnerability

If you find a way to break one of the properties above, report it privately
to security@openbasil.org, not in a poblic issue.
[Security policy](https://github.com/openbasil/basil/blob/main/SECURITY.md)

## Where to go next

- [How it works](/introduction/how-it-works/): the two gates that every call passes.
- [Backends & custody](/introduction/backends-and-custody/): in-place vs. materialize-to-use exposure.
- [The policy](/configuration/policy/): writing default-deny grants and break-glass subjects.
- [Unlock & bundle](/configuration/unlock-and-bundle/): how the backend credential is sealed and opened.
