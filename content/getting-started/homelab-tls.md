+++
title = "Issue TLS certificates for your internal services"
weight = 60
+++

# Issue TLS certificates for your internal services

Internal services deserve real TLS, but running your own CA the usual way means a CA private key
sitting in a file that any backup job, sync tool, or compromised script can copy. Whoever holds
that file *is* your CA. This tutorial builds the same homelab CA with the key held **in place** in
a backend PKI engine: Basil brokers leaf issuance, policy limits who may mint, and the CA key never
leaves the engine. A systemd timer renews short-lived leaves and reloads your web server.

## Prerequisites

Certificate issuance uses the backend's `pki` engine, which only the `vault` backend kind provides
(OpenBao or HashiCorp Vault CE; see [Backends & capabilities](/configuration/backends/)). The
built-in db-keystore backend does **not** support `pki`, so `basil demo` and a keystore-only setup
cannot issue certificates. You need:

- a running OpenBao (`bao`) or Vault (`vault`) instance Basil already fronts;
- a working broker setup: catalog, policy, sealed bundle, socket
  ([First run](/getting-started/first-run/) gets you there);
- the web server you want to serve TLS with (the reload hooks below cover nginx and Caddy).

## 1. Create the CA inside the engine

Mount a `pki` engine, generate an **internal** root, and define an issue role. `bao` and `vault`
take identical commands here. The root's private key is generated inside the engine and is never
exported; that is the custody win this whole page is about.

```sh
bao secrets enable -path=pki pki
bao secrets tune -max-lease-ttl=87600h pki
# Internal root: generated and held in the engine, never exported.
bao write -f pki/root/generate/internal common_name="homelab-root" ttl=87600h
# The issue role bounds what leaves this CA: which names, which SANs, how long.
bao write pki/roles/homelab \
    allowed_domains="home.arpa" \
    allow_subdomains=true \
    allow_ip_sans=true \
    max_ttl=720h
```

The role is your first policy layer: even a caller Basil authorizes can only get leaves for
`*.home.arpa` names, with a TTL the role caps. Import the root into your clients' trust stores once
(`bao read -field=certificate pki/cert/ca` prints it); leaves rotate underneath it from then on.

## 2. Declare the issuer in the catalog

A certificate issuer is a catalog key whose `path` names the engine's issue role,
`pki/issue/<role>`:

```json
"homelab.cert_issuer": {
  "class": "asymmetric",
  "keyType": "ed25519",
  "backend": "bao",
  "engine": "pki",
  "path": "pki/issue/homelab",
  "writable": false,
  "missing": "warn",
  "description": "Homelab CA issue role; the CA key stays in the engine, the broker mints leaves in place."
}
```

`missing: warn` keeps the key routable: the existence probe reads transit metadata, which a `pki`
issue path answers with a 404, so `warn` avoids a fatal reconcile for a role that provably works.

## 3. Grant `mint` to the renewal service only

Give the renewal job its own uid and grant it exactly one thing: `op:mint` over the issuer key.
Issuance is a credential-emitting operation, so it is gated by `mint`, not by `sign` or `get`.

```json
{
  "schema": "policy",
  "subjects": {
    "svc.cert-renew": {
      "domain": "host-process",
      "match": { "all": [{ "process.uid": 990 }] }
    }
  },
  "rules": [
    {
      "id": "cert-renew-can-mint-leaves",
      "subjects": ["svc.cert-renew"],
      "action": ["op:mint"],
      "target": ["homelab.cert_issuer"],
      "comment": "The renewal service may mint TLS leaves. Nothing else; nobody else."
    }
  ]
}
```

Your interactive user does not need this grant. If you want to issue one leaf by hand to test,
grant yourself temporarily and remove it, or run the check as the service uid with
`runuser -u cert-renew`. Verify the grant offline before deploying:

```sh
basil explain --catalog catalog.json --policy policy.json \
  --subject svc.cert-renew --op mint --key homelab.cert_issuer
```

## 4. Issue a leaf

`issue-cert` requests a leaf from the issue role. `--dns-san` and `--ip-san` repeat for multiple
SANs; `--ttl-secs` is required and bounded by the role's `max_ttl`:

```sh
basil --socket /run/basil/basil.sock issue-cert \
  --key-id homelab.cert_issuer \
  --common-name grafana.home.arpa \
  --dns-san grafana.home.arpa \
  --dns-san metrics.home.arpa \
  --ttl-secs 604800
```

The output is PEM: the leaf and its chain as `CERTIFICATE` blocks, then the issuing-CA chain, then
the leaf's private key as a single `PRIVATE KEY` block. The leaf key is the one broker result that
*is* private material, because your web server needs it to terminate TLS; it is freshly generated
per leaf and belongs only to this certificate. The CA key it was signed with stays in the engine.

## 5. Renew on a timer

A short-TTL leaf plus a timer beats a long-lived certificate you will forget about. The renewal
script splits the PEM output and reloads the server:

```sh
#!/usr/bin/env bash
# /usr/local/bin/renew-grafana-cert
set -euo pipefail
dir=/var/lib/homelab-certs
out=$(basil --socket /run/basil/basil.sock issue-cert \
  --key-id homelab.cert_issuer \
  --common-name grafana.home.arpa \
  --dns-san grafana.home.arpa \
  --ttl-secs 604800)
umask 027
printf '%s\n' "$out" | sed -n '/BEGIN CERTIFICATE/,/END CERTIFICATE/p' > "$dir/grafana.crt.new"
printf '%s\n' "$out" | sed -n '/BEGIN PRIVATE KEY/,/END PRIVATE KEY/p' > "$dir/grafana.key.new"
mv "$dir/grafana.crt.new" "$dir/grafana.crt"
mv "$dir/grafana.key.new" "$dir/grafana.key"
systemctl reload nginx    # Caddy: systemctl reload caddy
```

The certificate file carries every `CERTIFICATE` block (leaf first, then the chain), which is what
nginx's `ssl_certificate` and Caddy's `tls` directive expect. Wire the script to a oneshot service
and a timer, running as the granted uid:

```ini
# /etc/systemd/system/renew-grafana-cert.service
[Unit]
Description=Renew grafana TLS leaf through Basil
After=basil.service
Requires=basil.service

[Service]
Type=oneshot
User=cert-renew
Group=nginx
ExecStart=/usr/local/bin/renew-grafana-cert
```

```ini
# /etc/systemd/system/renew-grafana-cert.timer
[Unit]
Description=Renew grafana TLS leaf twice a week

[Timer]
OnCalendar=Mon,Thu 03:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

Renewing twice a week against a 7-day TTL means a missed run is a warning, not an outage.
`User=cert-renew` is what makes the policy work: the broker resolves that uid from `SO_PEERCRED`,
so the timer's identity *is* its authorization. `Group=nginx` plus the `umask` gives the web server
group read on the key without making it world-readable.

{% caution(title="The leaf key is on disk; the CA key is not") %}
This design accepts a short-lived leaf key on the host, because a TLS server cannot terminate
connections without it. What it removes is the standing prize: a stolen leaf key ages out in days,
while the CA key that could mint arbitrary identities never leaves the engine. Audit shows every
mint, so an attacker minting extra leaves leaves a trail.
{% end %}

{% note(title="If anything failed") %}
Run `basil doctor --keys -c <config>` to validate the catalog, policy, and the authenticated
per-key probe (it exercises the issuer path), and see [Troubleshooting](/troubleshooting/) for the
error reference.
{% end %}

## Where to go next

- [Backends & capabilities](/configuration/backends/): which backend kinds provide the `pki` engine.
- [The policy](/configuration/policy/): subjects, `op:mint`, and least-privilege grants.
- [Rotating keys](/operations/rotating-keys/): rotation for the non-PKI keys in the same catalog.
- [Audit logs](/operations/audit-logs/): the per-mint trail the timer leaves behind.
