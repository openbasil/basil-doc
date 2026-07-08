+++
title = "Uninstall & removal"
weight = 120
+++

# Uninstall & removal

Removing Basil cleanly is short work, because the broker keeps almost nothing on the host: the
keys it brokered live in the backend and stay there. This page lists everything Basil touches, in
removal order, and what "destroying a bundle" actually revokes.

## What lives where

| Artifact | Typical location | Notes |
| --- | --- | --- |
| Binaries | `/usr/bin/basil`, `/usr/bin/basil-nats-bridge` | Via the Arch package (`basil-bin`), the Nix-built `.deb` (package name `basil`), or a manual copy. |
| State | `/var/lib/basil/` | The sealed bundle, its `.epoch` sidecar, and the keystore DB if you use the embedded `db-keystore` backend. |
| Runtime | `/run/basil/` | The Unix socket; gone on reboot. The dev default is `/tmp/basil-agent.sock`. |
| Config | `/etc/basil/` | Agent TOML, catalog, policy. Paths are operator-chosen; `/etc/basil` is the convention the NixOS module and docs use. |
| Audit log | wherever `audit-log` points | Decision records; keep or archive per your retention policy before deleting. |
| Unit & user | `basil-agent.service`, the `basil` system user/group | Created by the NixOS module, or by you on other distros. |

## Removal order

1. **Stop the unit** (`systemctl stop basil-agent`). The socket is the only ingress: no process,
   no requests.
2. **Revoke the broker's backend credential** in the backend: revoke the AppRole `secret_id` or
   token in OpenBao/Vault, or the service-account access for a cloud KMS. Deleting the bundle
   file alone removes the *local copy* of the credential; revocation at the source is what
   actually retires it.
3. **Delete the state**: remove the bundle and its sidecar together
   (`rm /var/lib/basil/bundle.sealed*`), then the rest of `/var/lib/basil`. There is no
   `bundle destroy` subcommand; deleting the file is the destruction, and the bundle is encrypted
   at rest, so a deleted-but-recoverable copy without its unlock secrets stays sealed.
4. **Remove config and unit**: `/etc/basil/`, the service unit, and the `basil` user/group. On
   NixOS, drop the `service.basil` module from your configuration instead.
5. **Remove the package**: `pacman -R basil-bin`, `dpkg -r basil`, or delete the manually
   installed binaries.

## What removal does not remove

Basil brokers operations; it does not own the keys. Everything in the backend survives:

- **Keys in OpenBao/Vault/KMS** remain, along with anything encrypted or signed under them.
  Delete or retire them in the backend, deliberately and out of band, only if you are
  decommissioning the keys themselves and not just the broker.
- **Minted credentials** (short-lived leases, JWT-SVIDs, NATS JWTs) expire on their own TTLs;
  there is nothing to clean up.
- **BIP39 phrases and passphrases** stored outside the host are now unlock secrets for a bundle
  that no longer exists. Retire them from their stores so they do not linger as mystery secrets.

{% note(title="Keep the audit log") %}
The audit log is the record of every decision the broker made. If the removal follows an
incident, archive it before deleting the host state; it is the one artifact you cannot
reconstruct later.
{% end %}

## Where to go next

- [Backup & disaster recovery](/operations/backup-and-recovery/): if you are migrating rather
  than removing, back up first.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): what the bundle holds and why
  deleting it is safe.
- [Installation](/getting-started/installation/): the mirror image of this page.
