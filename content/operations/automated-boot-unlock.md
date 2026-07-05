+++
title = "Automated boot unlock"
weight = 90
+++

# Automated boot unlock

Some hosts need Basil to start without an operator at the console. The production passphrase slot is
the intended automation hook: an external trust root fetches the passphrase at boot, writes it to a
local file or systemd credential, and `basil agent` opens the sealed bundle from that file. If the
fetch fails, the unit fails and the bundle stays sealed.

This does not make the upstream secret store part of Basil. It makes it the trust root for boot
unlock, so scope and monitor it with the same care as the bundle itself.

{% note(title="TPM-sealed slot: no external trust root") %}
On a host with a TPM 2.0, a TPM-sealed unlock slot removes the external fetcher entirely: the slot key
is sealed to the host's PCRs and unsealed at boot, so no operator secret or upstream store sits on the
unlock path. It is feature-gated behind the off-by-default `unlock-tpm` build. Create the slot with
`basil bundle create --slot tpm:pcrs=0,2,4,7`, scaffold config with `basil config init --unlock tpm`,
and set `[unlock] unlock-tpm = true`. The passphrase-fetch pattern below suits hosts without a usable
TPM.
{% end %}

## Unit shape

This example uses a 1Password service-account token delivered as a systemd credential. The token is
not baked into the unit environment; `ExecStartPre` reads it from `$CREDENTIALS_DIRECTORY`, fetches the
passphrase, verifies the bundle opens, and leaves the file for `basil agent` to consume.

```ini
[Unit]
Description=Basil agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=basil
Group=basil
RuntimeDirectory=basil
StateDirectory=basil
ConfigurationDirectory=basil
LoadCredential=op-token:/etc/basil/op-service-token
ExecStartPre=/usr/bin/env bash -euc 'umask 077; export OP_SERVICE_ACCOUNT_TOKEN="$(cat "$CREDENTIALS_DIRECTORY/op-token")"; op read "op://platform/basil-unlock/passphrase" > /run/basil/unlock-passphrase; basil bundle verify /var/lib/basil/bundle.sealed --open passphrase:file=/run/basil/unlock-passphrase'
ExecStart=/usr/bin/basil agent --config /etc/basil/agent.toml
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

The matching agent config points at the fetched file:

```toml
bundle = "/var/lib/basil/bundle.sealed"

[unlock]
unlock-passphrase-file = "/run/basil/unlock-passphrase"
strict-bundle-perms = true
```

By default Basil overwrites and removes `unlock-passphrase-file` after startup reads it. That is the
right behavior for a writable tmpfs file such as `/run/basil/unlock-passphrase`.

## Read-only credential files

If the passphrase itself is supplied as a systemd credential, `$CREDENTIALS_DIRECTORY` may be
read-only. In that case configure Basil not to wipe it:

```toml
[unlock]
unlock-passphrase-file = "/run/credentials/basil.service/basil-unlock-passphrase"
unlock-passphrase-no-wipe = true
```

Use `unlock-passphrase-no-wipe` only for read-only credential mounts or other stores whose lifecycle is
owned outside Basil. For normal files, let Basil wipe after read.

## Preflight and expiry monitoring

Run the same fetch plus `bundle verify` path on a timer so an expired upstream token is caught before a
restart turns it into an outage.

```ini
[Unit]
Description=Verify Basil automated unlock

[Service]
Type=oneshot
User=basil
Group=basil
RuntimeDirectory=basil
LoadCredential=op-token:/etc/basil/op-service-token
ExecStart=/usr/bin/env bash -euc 'umask 077; export OP_SERVICE_ACCOUNT_TOKEN="$(cat "$CREDENTIALS_DIRECTORY/op-token")"; op read "op://platform/basil-unlock/passphrase" > /run/basil/unlock-passphrase.check; basil bundle verify /var/lib/basil/bundle.sealed --open passphrase:file=/run/basil/unlock-passphrase.check; rm -f /run/basil/unlock-passphrase.check'
```

```ini
[Unit]
Description=Periodic Basil automated unlock verification

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

{% caution(title="The fetcher token is unlock authority") %}
For 1Password, scope the service-account token to the single item that holds the passphrase, keep it
short-lived where your process allows, and rotate it on a schedule. A token that can fetch the slot
passphrase can unlock the Basil bundle.
{% end %}

## Where to go next

- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): slot ranking and bundle commands.
- [Configuration overview](/configuration/overview/): where `[unlock]` lives in the agent TOML.
- [Incident runbook](/troubleshooting/incident-runbook/): lost unlock secrets and rollback recovery.
