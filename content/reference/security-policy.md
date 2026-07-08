+++
title = "Security policy"
weight = 60
+++

# Security policy

Basil is a security infrastructure component, and we want to know about any vulnerability in it.
This page is the docs-site home of the repository's
[`SECURITY.md`](https://github.com/openbasil/basil/blob/main/SECURITY.md), which is canonical if
the two ever differ. We pledge to investigate all credible reported security issues.

## Reporting a vulnerability

Report privately. **Do not open a public issue, discussion, or pull request for a suspected
vulnerability, and do not publish a reproducible test case.**

- **Email (preferred)**: [security@openbasil.org](mailto:security@openbasil.org)
- **GitHub private vulnerability reporting**: the repository's **Security** tab →
  **Report a vulnerability**. This opens a private advisory only you and the maintainers can see.

Include what you can: the Basil version or commit (`basil --version`), whether it is a release
binary or custom build and with which features, the backend in use and its version, the OS, a
description of the impact, and reproduction steps. **Redact real secrets, keys, or tokens** from
anything you attach.

## What to expect

There is no bug bounty and no formal SLA. We aim to acknowledge a credible report within
**2 business days**, and we practice **coordinated disclosure**: we agree on a disclosure timeline
with you and, unless you prefer otherwise, credit you in the release notes and advisory.

## Scope

In scope, roughly: anything that breaks a property the [threat model](/introduction/threat-model/)
claims. Concretely:

- `SO_PEERCRED` caller-attestation bypass or wrong-subject resolution.
- Policy-engine flaws: privilege escalation, wildcard or `breakGlass` bypass, `writable` cap
  bypass.
- Private key material leaking across the socket, into logs, or onto disk with an in-place
  backend.
- Nonce reuse or AEAD-envelope weaknesses.
- Sealed-bundle unlock weaknesses (age/YubiKey, BIP39 break-glass, passphrase, TPM sealing).
- Memory-safety issues (the codebase is `forbid(unsafe_code)` with a strict no-panic runtime
  rule, so any panic reachable from the socket is a finding).

Out of scope: issues in your own catalog or policy configuration, in the backend (OpenBao/Vault)
itself, or in the host OS.

## Trust model

Basil is a single host-local broker. It trusts the kernel's `SO_PEERCRED` attestation and the
integrity of the host it runs on; it is not a sandbox and does not defend against root-level host
compromise. The [threat model](/introduction/threat-model/) states the properties Basil claims
and the ones it deliberately does not.

## Where to go next

- [Threat model](/introduction/threat-model/): the properties a report would break.
- [Stability & upgrades](/reference/stability-and-upgrades/): how fixes reach you.
- [Licenses](/reference/licenses/): how Basil and this documentation are licensed.
