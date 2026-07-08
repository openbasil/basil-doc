+++
title = "How it compares"
weight = 40
+++

# How it compares

Secrets management requires multiple infrastructure components, including identity, secret storage,
and policy. Basil doesn't replace identity or secret storage; instead, it sits in front of them.
Basil provides secrets-related services, keeping keys in place, using kernel-attested identity, and
ensuring every operation is authorized and audited.

## Talking to Vault / a KMS directly

An app can connect to Vault or a cloud KMS itself, but then the app needs a credential to authenticate to
that backend. That bootstrapping secret has its own risks: it must be delivered, rotated, and protected,
and, significantly, that token is not an identity. Access is gated by the value of the token, not the
identity of the process.

Basil fronts the backend instead:

- it identifies the caller **from the kernel** (no token to distribute or steal),
- enforces a **local default-deny policy**, and
- brokers the operation, so the workload needs **no backend credential at all**.

It also removes some crypto footguns by design. For example, the API doesn't ask for a nonce, so the
app cannot accidentally reuse one. What's the downside? There's an extra agent process, plus one
extra communication hop over a local Unix socket. Vault and OpenBao have an answer for this, discussed
in the next section.

## Vault Agent / OpenBao's `bao agent`

Vault's answer to the bootstrap problem is
[Vault Agent](https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent), and OpenBao has `bao agent`.
These agents act as a host-local sidecar that auto-authenticates to the server (cloud IAM,
Kubernetes SA, AppRole, TLS cert), keeps the token renewed, and renders secrets into files or a
child process's environment. They are mature, widely deployed, and if you already run Vault or
OpenBao, you may already be using one. Like Basil, these agents relieve the app of the responsibility
of storing or rotating the secret.

The differences are in what happens after authentication. With vault/bao agent,:

- **The identity is the host's, not the caller's.** Auto-auth proves the machine (or pod) to the
  server; anything on the host that can read a rendered file or reach the agent's proxy inherits
  that identity. Basil attests each calling process from the kernel and applies a default-deny
  policy per uid, per operation.
- **It still delivers values.** Templated secrets land in files or env and live in the app's
  memory, with no per-operation authorization or audit of who read them. Basil brokers the
  operation, so in-place keys never leave the backend, and auditing is each use, not first delivery.
- **On bare hosts, bootstrap moves rather than disappears.** In cloud or Kubernetes, auto-auth
  builds on the platform identity, and the problem is genuinely solved. On plain machines, the agent
  needs an AppRole `secret_id` or a client cert, now held by the agent. Basil has the same needs,
  but differs in what is unlocked. The token unlocks every caller. Basil continues to attest each caller.

To be fair, Basil has additional costs relative to Vault Agent. Basil is another daemon to operate,
a policy file to maintain, and clients need to speak Basil's API (or run its CLI) instead of just
reading a file. If your workloads run in cloud or Kubernetes and only need values in files,
Vault Agent or Bao Agent are simpler and probably enough. The two can coexist: Vault Agent for workloads
that genuinely need a rendered config file, and Basil in front of the same server for the things that
are really keys (TLS, signing, encryption) and for per-process authorization and audit on shared hosts.

## SPIFFE / SPIRE

[SPIRE](https://github.com/spiffe/spire) is the reference SPIFFE implementation: a server plus
per-node agents, a rich set of node/workload attestors, and full federation.

Basil also serves the **standard SPIFFE Workload API** and issues X.509/JWT SVIDs, and it's verified
against the upstream `rust-spiffe` client. But it's a **single local broker** (no server/agent
split), attests with `SO_PEERCRED` (uid/gid), and keeps issuer/CA keys in a Vault-compatible backend,
used in place. It also brokers general secrets and crypto (sign / encrypt / mint NATS) that SPIRE
doesn't.

|                | SPIRE                          | Basil                                        |
| -------------- | ------------------------------ | -------------------------------------------- |
| Topology       | Server + per-node agents       | Single host-local broker                     |
| Attestation    | Pluggable (k8s, cloud, TPM, …) | `SO_PEERCRED` (uid/gid/pid)                  |
| Issuer/CA keys | Plugin-dependent               | In a Vault-compatible backend, used in place |
| Beyond SPIFFE  | None                           | General secrets, sign/encrypt, NATS minting  |
| Federation     | Yes                            | <span class="pill gap">roadmap</span>        |

Use SPIRE for fleet-wide SPIFFE infrastructure with cloud/k8s attestation and federation; use Basil
when you want one host-local broker that *also* speaks SPIFFE. They interoperate rather than
compete.

## systemd credentials

systemd's `LoadCredential=` / `ImportCredential=` (and `systemd-creds`, optionally TPM-sealed)
deliver secrets to a unit at start. That's a solid fit for *static, boot-time* material. But it
hands the process a **value**: once loaded it lives in the app's memory, it doesn't expire, and
there's no per-operation authorization or audit.

Basil brokers the *operation* (the key is used in place, never delivered), mints credentials that
expire on their own, and authorizes and logs every call. The two compose well: let systemd deliver
Basil's unlock secret, and let Basil hand out the short-lived rest.

## Secret managers (Doppler, Infisical, 1Password)

[Doppler](https://doppler.com), [Infisical](https://infisical.com), and
[1Password](https://1password.com) (with its secrets-automation features) are **secret managers**: a
central store, usually with a web UI and cross-environment sync, that ships secrets to your app
through a CLI, an agent, a sidecar, or a Kubernetes operator.

They solve a real and different problem: giving a *team* a place to store, share, version, and rotate
secrets, and getting those values to where they run. But the delivery model is the one Basil is built
to avoid. The app authenticates with a service token or machine identity, and the manager hands it a
value that then lives in the app's environment, a file, or its memory.

Basil gives you access to the key without your app ever touching it:

- the workload holds no token to the manager; its identity is the kernel-attested uid,
- keys are used in place and never delivered (with an in-place backend), and
- every use is authorized by a default-deny policy and written to an audit log.

Basil can front secret managers through store-only backends: `db-keystore`, a local encrypted
SQLite-compatible file, and `1password`, a provider-backed store that may be on the host or remote.
1Password is in the default build; `db-keystore` is opt-in. Since these are not transit engines,
crypto operations do not
happen in the vault. The secret is briefly materialized in Basil for a single operation, then the
memory that held it is wiped. If you want a team-facing secrets manager with a UI and
cross-environment sync, or if you are running in a memory-constrained device, one of these might be a
good fit. If you want to keep the delivered secret off the workload's disk and broker its use on the
host, that is Basil's job.

## Encrypted secrets in Git (SOPS, sops-nix, agenix)

[SOPS](https://github.com/getsops/sops) and the NixOS tools built on it,
[sops-nix](https://github.com/Mic92/sops-nix) and [agenix](https://github.com/ryantm/agenix), encrypt
secrets into your Git repo and decrypt them at deploy or activation time into files (typically
under `/run/secrets`). A master key (age, PGP, or a cloud KMS) can decrypt everything.

This is an excellent fit for declarative, GitOps-style config secrets, and it needs no running
service. The trade-offs are the ones Basil is built to remove:

- the decrypted secret is a value on disk that anything running as its owner can read,
- rotation means re-encrypting and redeploying (on NixOS, a rebuild), and
- there is no per-operation authorization and no audit of who read what.

Basil keeps the material off disk (used in place, or fetched on demand under policy), rotates live
without a rebuild, and authorizes and logs every access. The cost is a running broker plus a backend.
The two coexist: migrate one secret at a time, and keep SOPS for the rest.

{% tip(title="Migrating from sops-nix") %}
Move one secret at a time. Start with the drop-in tier: keep it a value (`engine: kv2`) but fetch it
from Basil under policy instead of reading a decrypted file, so it is off disk, authorized, and
audited without a rebuild. Then upgrade the things that are really keys (TLS, signing, encryption) to
the in-place tier, where the private half never lands anywhere.
{% end %}

## Summary

| You want…                                                                                             | Reach for…                                                                   |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Auto-auth and templated secret files from an existing Vault/OpenBao                                   | Vault Agent / `bao agent` (with Basil brokering key use on the same server)  |
| Fleet-wide SPIFFE with cloud/k8s attestation + federation                                             | SPIRE (with Basil as a local broker if useful)                               |
| Static, boot-time secrets delivered to a unit                                                         | systemd credentials (delivering Basil's unlock secret)                       |
| A team secrets manager with a UI, sharing, and cross-environment sync                                 | Doppler / Infisical / 1Password (which Basil can source through `1password`) |
| Declarative secrets encrypted in Git and decrypted at deploy                                          | SOPS / sops-nix / agenix (migrate to Basil one secret at a time)             |
| A host-local broker that keeps keys in place, attests from the kernel, and mints short-lived identity | **Basil**                                                                    |

## Where to go next

- [What is Basil?](/introduction/what-is-basil/): the model in one page.
- [Threat model](/introduction/threat-model/): the trust boundaries behind these comparisons.
- [Integration patterns](/clients/integration-patterns/): native client, sidecar, and last-resort pre-fetch.
