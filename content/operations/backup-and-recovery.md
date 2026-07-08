+++
title = "Backup & disaster recovery"
weight = 100
+++

# Backup & disaster recovery

Basil is deliberately light on state, but the little state it has is the difference between a
restart and a re-bootstrap. Two things must survive a disaster: the **backend** (where the keys
actually live) and the **sealed bundle plus its epoch sidecar** (how the broker authenticates to
that backend). Back up both, because neither substitutes for the other.

## What to back up

| Artifact | What it is | Where it may go |
| --- | --- | --- |
| The backend (OpenBao/Vault, KMS, keystore DB) | The keys themselves. If this is lost, everything signed or encrypted with those keys is unrecoverable. | Your backend's own backup story (Raft snapshots, cloud KMS durability). Basil adds nothing here. |
| Sealed bundle (e.g. `/var/lib/basil/bundle.sealed`) | The broker's backend credentials, encrypted under a master key wrapped to your unlock slots. | Ordinary encrypted-at-rest backups are acceptable; see below for the caveats. |
| Epoch sidecar (`<bundle>.epoch`) | A one-line anti-rollback counter next to the bundle. Not a secret. | Back it up **together with** the bundle it belongs to. |
| Catalog, policy, agent TOML | Plain configuration, no secrets. | Version control. |
| Unlock secrets (BIP39 phrase, passphrase source) | What opens the bundle. | **Never** in the same store as the bundle. See below. |

Audit logs are worth backing up for forensics, but they are not needed for recovery.

## How bundle backup interacts with backend backup

The bundle holds *access material*, never key material. The private keys stay in the backend and
are used in place. That split decides what each restore gets you:

- **Bundle restored, backend lost:** you can authenticate to nothing. The keys, and everything
  protected by them, are gone. The backend backup is the one that protects your data.
- **Backend restored, bundle lost:** the keys are intact, and nothing is unrecoverable. Issue a
  fresh backend credential (a new AppRole `secret_id`, a new token) and
  `basil bundle create` a new bundle. No secret material is exposed in the process.

A lost bundle is therefore an inconvenience; a lost backend is a disaster. Spend your backup
diligence accordingly.

## What is safe to store where

The bundle is encrypted at rest: the payload under `AES-256-GCM`, the master key wrapped
independently per unlock slot, and phrase-based slots stretched with **Argon2id**. A backup copy
leaking does not directly leak the backend credential. Two caveats keep that true:

- A stolen bundle copy is **offline-attackable through its passphrase slot**. The Argon2id
  stretch buys time, not immunity: use a high-entropy passphrase, and treat a suspected bundle
  leak as a reason to rotate the backend credential (`basil bundle set-backend`) so the copy goes
  stale.
- An unlock secret stored next to the bundle turns your backup archive into the credential
  itself. Keep the BIP39 phrase offline and access-logged, and keep the passphrase in its
  upstream store (see [Automated boot unlock](/operations/automated-boot-unlock/)); back up
  neither alongside the bundle.

{% caution(title="TPM slots do not travel") %}
A TPM unlock slot is sealed to the originating TPM and is meaningless on any other machine. A
bundle whose only slot is TPM cannot be recovered on replacement hardware, no matter how good the
backup. Always keep a portable slot (BIP39 break-glass or passphrase) on a bundle you intend to
restore elsewhere.
{% end %}

## Restoring

Restore the bundle and its `.epoch` sidecar as a pair, then prove the restore *before* a restart
depends on it:

```sh
basil bundle verify /var/lib/basil/bundle.sealed \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase
```

The epoch check runs before any unlock and fails closed in one direction: restoring an **older
bundle over a newer sidecar** is refused, so a credential you rotated out cannot be silently
reinstated from a stale backup. If the rollback is deliberate (a real disaster recovery to a
known-good older state), re-establish the epoch with a fresh `basil bundle create` or
`basil bundle set-backend`. Restoring a bundle with **no** sidecar re-initializes the sidecar
from the bundle's own epoch, which is why the pair should be backed up together: the sidecar is
what remembers that a newer bundle existed. See the
[incident runbook](/troubleshooting/incident-runbook/) for the recovery steps.

{% best(title="Drill the restore") %}
`bundle verify` is read-only and cheap. Run it against your restored artifacts on a schedule, the
same way you test any backup, so the first real restore is not the first restore ever. If all
slots are lost, recovery is re-bootstrap by design: new backend credential, new bundle. There is
no backdoor.
{% end %}

## Where to go next

- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): slots, credentials, and bundle
  commands.
- [Incident runbook](/troubleshooting/incident-runbook/): lost unlock secrets and epoch-mismatch
  recovery.
- [Production hardening checklist](/operations/production-hardening/): the go-live walk that
  includes backups.
