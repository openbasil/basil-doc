+++
title = "Unlock & the sealed bundle"
weight = 60
+++

# Unlock & the sealed bundle

The bundle is a `0600` file holding the backend credential, encrypted under a master key that is itself
wrapped to one or more **unlock slots**. At startup Basil recovers the master key from whichever slot
you supply, decrypts the credential, and zeroizes the key. It fails closed if no slot opens.

## What the bundle carries

The decrypted payload is a map of backend id → `BackendCred`. One credential per backend; the broker
hands each one to the matching backend at startup, then zeroizes the whole map.

| Credential | Backend kind | What it holds |
| --- | --- | --- |
| `VaultToken` | `vault` | A static bearer token: simplest, for dev or tightly controlled automation. |
| `VaultAppRole` | `vault` | A `role_id` + `secret_id` exchanged for a short-lived token at startup, the standard production choice. |
| `SpiffeSigner` | `vault` | A private signing key the broker uses to self-mint a JWT-SVID at `auth/<mount>/login`. No static backend secret on disk. |
| `DbKeystoreDek` | `keystore` (`db-keystore`) | The 32-byte DEK that opens the encrypted local database. |
| `OnePassword` | `keystore` (`1password`) | Provider URI, project, and profile for the 1Password materialize-to-use backend. |
| `AwsKms` | `aws-kms` | AWS region and optional profile for the in-place AWS KMS transit backend. |
| `GcpKms` | `gcp-kms` | GCP project, location, key ring, and optional sealed service-account JSON for the in-place GCP Cloud KMS transit backend. |

See [Backends & capabilities](/configuration/backends/) for the full authentication detail and when to
choose each credential kind.

## Unlock slots

| Slot | Config key | Notes |
| --- | --- | --- |
| age / YubiKey | `age-yubikey = true` | Master key wrapped to an age recipient; a YubiKey touch/PIN (via `age-plugin-yubikey`) recovers it. Strongest interactive production slot. |
| Passphrase | `unlock-passphrase-file = "<FILE>"` | A production passphrase read from a `0600` file or systemd credential, Argon2id-stretched, then wiped by default after startup reads it. |
| BIP39 | `bip39-phrase-file = "<FILE>"` | A 24-word recovery phrase read from a `0600` file (never argv/env), then wiped by default after startup reads it. Break-glass. |
| TPM | `unlock-tpm = true` | <span class="pill impl">implemented</span> Master KEK sealed to host TPM 2.0 PCR state; unattended boot, no operator secret. Needs the `unlock-tpm` build. |

Set `strict-bundle-perms = true` to refuse startup if the bundle isn't `0600` (default is warn-only).

For read-only credential mounts, set `unlock-passphrase-no-wipe = true` for the passphrase slot.
Otherwise Basil attempts a best-effort overwrite and remove after it has read passphrase and BIP39
phrase files into zeroizing memory.

The TPM slot is available in a binary built with the non-default `unlock-tpm` feature. It seals the
master KEK to the host's TPM 2.0 PCR state, so the host unlocks itself at boot with no operator secret.
Create it with `basil bundle create --slot tpm[:pcrs=0,2,4,7]` (PCRs default to `0,2,4,7`, hash bank
`sha256`) and enable it with `[unlock] unlock-tpm = true`. A binary without the feature fails the slot
closed. See [Automated boot unlock](/operations/automated-boot-unlock/).

## Choosing an unlock method

The right slot depends on what you are optimizing: operator presence, unattended boot, or emergency
recovery. Rank them by the trust root you are willing to stand behind.

| Rank | Method | Trust root | Main risk |
| --- | --- | --- | --- |
| 1 | `age-yubikey` | Hardware token plus operator PIN/touch; the private key never leaves the token. | Token theft plus PIN compromise; availability depends on the token being present. |
| 2 | TPM (`unlock-tpm` build) | A KEK bound to host TPM 2.0 PCR state. | Host compromise; no operator presence once the measured state matches. |
| 3 | File-sourced passphrase | The passphrase file or systemd credential, Argon2id-stretched by the bundle slot. | Reduces to how the file is protected; a fetcher adds its own standing token. |
| 4 | BIP39 | The phrase itself. | If the phrase store leaks, the bundle is offline-attackable; use it for break-glass only. |

{% best(title="Automated boot unlock") %}
Use the passphrase slot when a service must start unattended. Basil stays source-agnostic: a systemd
unit, 1Password `op read`, or another fetcher can write the passphrase to a file before `basil agent`
starts. Scope and rotate that upstream token as if it can unlock the vault, because it can. See
[Automated boot unlock](/operations/automated-boot-unlock/).
{% end %}

## Building & updating a bundle

```sh
# create a bundle with BIP39 break-glass, a passphrase slot, and an AppRole backend cred
# (secret_id read from a 0600 file, never inline)
basil bundle create /var/lib/basil/bundle.sealed \
  --slot bip39 \
  --slot passphrase:file=/run/secrets/basil-unlock-passphrase \
  --backend id=bao,type=openbao,addr=https://bao.example,role-id=ROLE_ID,secret-id-file=/run/secrets/approle-secret-id

# rotate just the backend credential in the sealed payload
basil bundle set-backend /var/lib/basil/bundle.sealed \
  --backend id=bao,type=openbao,addr=https://bao.example,role-id=NEW_ROLE_ID,secret-id-file=/run/secrets/new-secret-id \
  --open bip39:file=/run/secrets/breakglass.txt
```

{% caution(title="The BIP39 phrase is shown once") %}
`bundle create --slot bip39` generates and prints the 24-word phrase a single time. Capture it then
(offline, out of band): there's no way to recover it later, and it's your last way back in if the
primary slot is lost. Secrets are always read from `0600` files, never inline arguments.
{% end %}

Use `bundle verify` as a non-destructive preflight before a restart or before changing the source of a
passphrase file:

```sh
basil bundle verify /var/lib/basil/bundle.sealed \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase
```

## Credential deposits

Credential deposits separate **contributing one backend credential** from **opening the whole
bundle**. This is useful when a cloud administrator owns a credential such as a GCP service-account
JSON, but should not receive the unlock secret that exposes every other backend credential.

The bundle stores an X25519 ingest private key and contributor allow-list inside the sealed payload.
The public recipient can be written at create time:

```sh
basil bundle create /var/lib/basil/bundle.sealed \
  --slot passphrase:file=/run/secrets/basil-unlock-passphrase \
  --backend id=bao,type=openbao,addr=https://bao.example,token-file=/run/secrets/bao-token \
  --deposit-key /var/lib/basil/deposit.pub
```

An admin allows a contributor signing key for one or more backend ids:

```sh
basil bundle allow /var/lib/basil/bundle.sealed \
  --contributor <ed25519-public-token> \
  --backend gcp1 \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase
```

The contributor then appends a signed deposit without an unlock secret:

```sh
basil bundle deposit /var/lib/basil/bundle.sealed \
  --backend id=gcp1,type=gcp-kms,project=PROJECT,location=global,key-ring=RING,key-file=/run/secrets/gcp-sa.json \
  -r /var/lib/basil/deposit.pub \
  -i /run/secrets/alice.ed25519.seed
```

At startup, Basil unlocks the normal sealed payload first, verifies the allow-list and signature, and
then overlays the newest authorized current-epoch deposit for that backend id. Invalid, stale,
unauthorized, superseded, or undecryptable deposits are ignored for startup rather than crashing the
broker.

Review before committing deposits into the sealed payload:

```sh
basil bundle promote /var/lib/basil/bundle.sealed --dry-run \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase

basil bundle promote /var/lib/basil/bundle.sealed --backend gcp1 \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase
```

`show` without `--open` lists only plaintext deposit metadata. `show --open` and `promote --dry-run`
add authorization status and non-secret fingerprints. GCP service-account deposits display the
service account identity fields when present; otherwise Basil prints a `SHA-256` fingerprint of the
serialized credential.

{% note(title="Anti-rollback") %}
The bundle carries a monotonic epoch, checked against an epoch sidecar file before any unlock is
attempted. Restoring an old bundle over a newer one is refused, so a credential you rotated out
can't be *accidentally* reinstated from a backup. This is a safety net, not a security boundary: an
attacker who can replace the broker-owned bundle can also delete the sidecar, and a missing sidecar
is re-initialized from the bundle's own epoch. Deliberate rollback resistance (TPM-backed epoch
storage) is <span class="pill gap">roadmap</span>.
{% end %}

## Where to go next

- [Backends & capabilities](/configuration/backends/): the credential kinds a bundle can carry.
- Backend how-tos: [OpenBao & Vault](/configuration/backend-openbao-vault/),
  [AWS KMS](/configuration/backend-aws-kms/), [Google Cloud KMS](/configuration/backend-gcp-kms/),
  [1Password](/configuration/backend-1password/): creating the credentials you deposit here.
- [Automated boot unlock](/operations/automated-boot-unlock/): unattended startup with a passphrase slot.
- [Incident runbook](/troubleshooting/incident-runbook/): lost unlock secret, epoch mismatch recovery.
