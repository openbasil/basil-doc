+++
title = "Production hardening checklist"
weight = 110
+++

# Production hardening checklist

The pieces of a hardened deployment are documented across this site; this page is the single walk
an operator can do before go-live. Basil is secure by default in its authorization model
(default-deny policy, kernel attestation), but the *host wiring* around it (socket location, file
modes, unit sandboxing) is yours to get right. Work the sections in order.

## The socket

- **Move the socket out of `/tmp`.** The compiled-in default is `/tmp/basil-agent.sock`, which is
  fine for a dev fixture and wrong for production. Use a dedicated runtime directory:

```toml
socket = "/run/basil/basil.sock"
socket-mode = "0660"
socket-group = "basil-clients"
```

- The default `socket-mode` is `0600` (owner-only). Widen it deliberately, with a dedicated
  group, only if other local users must connect. Basil binds under a tightened umask so the
  socket is never looser than configured, even for a moment.
- Remember what the mode is and is not: it controls who can *open* the transport. Every RPC is
  still authorized from kernel peer credentials against the policy, so a connectable socket grants
  nothing by itself.

## Files, ownership, and uid layout

- Run the agent as a dedicated system user (`basil`), not root and not a shared service account.
- State directory (`/var/lib/basil` by convention): owned by `basil`, mode `0700`. It holds the
  sealed bundle, the `.epoch` sidecar, and the keystore DB if you use the embedded backend.
- The bundle must be `0600`. Set `strict-bundle-perms = true` under `[unlock]` so a loose mode
  refuses startup instead of warning. The TOML default is warn-only; the NixOS module already
  defaults it to `true`.
- Client identity is uid/gid, so **uid hygiene is policy hygiene**: one uid per workload, no
  shared or recycled uids among things you want to distinguish. See the
  [threat model](/introduction/threat-model/) on the attestation boundary.

## The systemd unit

The NixOS module ships these; on any other distro, write them into your unit yourself:

```ini
[Service]
User=basil
Group=basil
StateDirectory=basil
StateDirectoryMode=0700
RuntimeDirectory=basil
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/basil /var/lib/basil
```

Add your audit-log directory to `ReadWritePaths` if it lives elsewhere. Reload catalog/policy
with `ExecReload` sending `SIGHUP`; see [Hot reload](/operations/hot-reload/).

## Backend least privilege

- Scope the broker's backend credential to exactly the mounts and paths the catalog uses;
  reading and writing are separate grants. See
  [OpenBao & Vault](/configuration/backend-openbao-vault/) for the least-privilege ACL policy.
- Prefer AppRole (or `SpiffeSigner`) over a static token; rotate the credential with
  `basil bundle set-backend` rather than editing anything in place.
- Keep `capability-policy = "strict"` (the default) so a backend that cannot provide what the
  catalog needs stops the broker instead of silently degrading.

## Surfaces that stay off

- The **JWKS HTTP listener** is off by default and loopback-scoped when enabled. If you must
  expose it beyond the host, front it with TLS (`http-tls` feature or a reverse proxy). It serves
  only public keys, but an exposed listener is still attack surface.
- **Sealed invocation** rejects requests unless `[invocation] enable = true` with explicit key
  bindings.
- Enable the [audit log](/operations/audit-logs/) and point it at persistent storage; it is your
  authority on what was requested during an incident.

## Preflight: what `doctor --strict` does and does not catch

Wire `basil doctor` in as a pre-start gate (`ExecStartPre=`) and into provisioning. `--strict`
adds **no new checks**; it turns advisory warnings (loose bundle perms, no `bao` on `PATH`,
a `missing=generate` key under `--keys`) into non-zero exits, which is what you want in CI and
provisioning. Add `--keys` where the pre-start environment holds the unlock material, so the
per-key existence probe runs too.

Know its limits. Doctor validates the environment the config describes; it does not audit your
deployment choices. It will not flag:

- a socket configured *in* `/tmp` (it checks the parent dir and mode, not the location's wisdom);
- missing systemd sandboxing, or the unit running as root;
- a bundle whose only unlock slot is TPM-sealed and therefore unrecoverable off-host;
- weak passphrase entropy, or an unlock secret stored next to the bundle;
- anything about backend ACL scope beyond capability probes.

Those are exactly the items above, which is why this page exists.

## The checklist

- [ ] Socket in `/run/basil`, mode `0600` (or `0660` + dedicated group), not `/tmp`.
- [ ] Agent runs as the `basil` user; state dir `0700`; bundle `0600`.
- [ ] `strict-bundle-perms = true`.
- [ ] Unit sandboxing: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`.
- [ ] One uid per client workload; no shared uids across trust boundaries.
- [ ] Backend credential is least-privilege AppRole (or `SpiffeSigner`), not a root token.
- [ ] A portable break-glass unlock slot exists and its phrase is stored offline.
- [ ] Bundle + `.epoch` sidecar in backups; restore drilled with `bundle verify`. See
      [Backup & disaster recovery](/operations/backup-and-recovery/).
- [ ] Audit log enabled on persistent storage.
- [ ] JWKS off, or TLS-fronted and consciously exposed.
- [ ] `basil doctor --strict` green as an `ExecStartPre=` gate.

## Where to go next

- [Doctor (preflight checks)](/operations/doctor/): every check, its severity, and the JSON.
- [Automated boot unlock](/operations/automated-boot-unlock/): unattended start without weakening
  the unlock story.
- [Backup & disaster recovery](/operations/backup-and-recovery/): the other half of go-live.
- [Limits & resource controls](/configuration/limits/): payload caps and version retention.
