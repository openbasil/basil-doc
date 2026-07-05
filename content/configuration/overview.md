+++
title = "Configuration overview"
weight = 10
+++

# Configuration overview

Basil runs from a TOML startup config that names three core inputs: a **catalog** (what keys exist and
where), a **policy** (who may do what), and a **sealed bundle** (the credential that lets the broker
reach the backend). Get these right and the rest of operations is routine. Basil validates them before
serving, so mistakes surface at startup, not under traffic.

## The subcommands

The broker is one binary, `basil`, with these config/daemon subcommands (plus
[`config init`](/getting-started/first-run/) for first-run scaffolding):

| Command | Purpose |
| --- | --- |
| `basil config init` | First-run scaffolding: a starter catalog + least-privilege policy + config. |
| `basil agent` | Run the broker daemon. |
| `basil config check` | Pre-flight: validate catalog + policy, enforce capability requirements, and read-only probe the backend for declared keys. |
| `basil config explain` | Offline policy dry-run: "would this be allowed, and why?" See [Policy explain](/operations/policy-explain/). |
| `basil bundle` | Create, update, verify, review, and promote sealed credential bundles. See [Unlock & the sealed bundle](/configuration/unlock-and-bundle/). |
| `basil doctor` | Preflight environment diagnostics before the daemon starts. See [Doctor](/operations/doctor/). |

## Startup config

Put daemon startup settings in a TOML file and start with `basil agent --config /etc/basil/agent.toml`.
For deploy-time relocation and tests, only the config path and the catalog/policy/bundle/socket/vault
address may be overridden by CLI or environment.

```toml
catalog = "/etc/basil/catalog.json"
policy = "/etc/basil/policy.json"
bundle = "/var/lib/basil/bundle.sealed"
socket = "/run/basil/agent.sock"
socket-mode = "0660"
socket-group = "basil-clients"
vault-addr = "https://vault.example:8200"
transit-mount = "transit"
capability-policy = "strict"   # strict | degraded | off
svid-ttl-secs = 300
max-encrypt-size = 1048576
max-payload-size = 1048576
grace-versions = 1
retention-sweep-secs = 3600
# retain-versions = 30
# audit-log = "/var/log/basil/audit.jsonl"
# no-reconcile = false

[unlock]
age-yubikey = true
# unlock-passphrase-file = "/run/basil/unlock-passphrase"
# unlock-passphrase-no-wipe = true
# bip39-phrase-file = "/run/secrets/basil-recovery.txt"
# strict-bundle-perms = true

[broker-identity]
# id = "basil://prod/us-east-1/agent-a"
# response-signing-key-id = "broker.response_signing.2026q3"

[invocation]
enable = false
# audience = ["basil://prod/us-east-1/agent-a"]
# request-encryption-key-id = "broker.request_encryption.2026q3"
# max-ttl-secs = 60
# clock-skew-secs = 30
# replay-cache-capacity = 4096
```

| Config key | What it does |
| --- | --- |
| `catalog` | Path to the catalog JSON. Required unless supplied by override. |
| `policy` | Path to the policy JSON. Required unless supplied by override. |
| `bundle` | Path to the `0600` sealed bundle. Required unless supplied by override. |
| `socket` | Unix socket to listen on. Defaults to Basil's built-in socket path. |
| `socket-mode` | Octal Unix socket mode. Default `0600`; use `"0660"` with `socket-group` for authorized local service users. |
| `socket-group` | Optional group name or numeric gid applied to the socket before serving. |
| `vault-addr` | Default backend address when a credential pins none. Default `http://127.0.0.1:8200`. |
| `transit-mount` | Transit engine mount path. Default `transit`. |
| `jwt-auth-mount` | JWT auth method mount for `SpiffeSigner` backend login. Default `jwt`. |
| `jwt-role` | Vault/OpenBao JWT role for `SpiffeSigner`. Required when any backend uses that credential type. |
| `jwt-audience` | JWT-SVID audience for `SpiffeSigner` login. Default `openbao`. |
| `db-keystore-cipher` | Default cipher for `db-keystore` backends when the sealed credential omits it. Requires a keystore-capable build. |
| `onepassword-provider-uri` | Default 1Password provider URI when the sealed `OnePassword` credential leaves it empty. 1Password is in the default build. |
| `onepassword-project` | Default 1Password project. 1Password is in the default build. |
| `onepassword-profile` | Default 1Password profile. 1Password is in the default build. |
| `svid-ttl-secs` | SVID lifetime (seconds) for broker self-login JWT-SVIDs and Workload API X.509-SVID issuance/refresh. Default 300. |
| `capability-policy` | `strict` (default) · `degraded` · `off`. See [Capability & reconcile](/configuration/capability-and-reconcile/). |
| `no-reconcile` | Skip the startup key-existence reconcile. Escape hatch. |
| `audit-log` | Append each authorization decision as JSONL to this file. See [Audit logs](/operations/audit-logs/). |
| `grace-versions` | Rotation grace window in key versions. Default 1; `0` = newest only. See [Rotating keys](/operations/rotating-keys/). |
| `retain-versions` | Retention floor; the sweep prunes archived versions below it. Omit to retain all. |
| `retention-sweep-secs` | Sweep interval (seconds). Default 3600; `0` disables. |
| `max-encrypt-size` | Cap on `encrypt` plaintext / `decrypt` ciphertext. Default 1 MiB. |
| `max-payload-size` | Cap on `set` value / `import` material. Default 1 MiB. |

Socket access only controls who can connect; Basil still authorizes each RPC by peer credentials and
policy. The `[logging]` section configures the `stdout`, `journald`, and `opentelemetry` log sinks (see
[Audit logs](/operations/audit-logs/)), and the opt-in `[jwks]` section publishes issuer public keys
over HTTP when the binary is built with `http` support (see [JWKS HTTP surface](/configuration/jwks/)).

Unlock config keys are covered in [Unlock & the sealed bundle](/configuration/unlock-and-bundle/).
Sealed invocation config is covered in [Sealed invocations](/clients/sealed-invocations/); the service
is registered but disabled unless `[invocation] enable = true`, and enabling it without an
`audience`, broker identity, response-signing key id, or request-encryption key id fails closed.
Each accepted request must also name a valid requester `response_encryption_key_id` so Basil can
return a signed, encrypted operation response.

## Allowed startup overrides

| Flag | Env | What it overrides |
| --- | --- | --- |
| `-c`, `--config` | `BASIL_CONFIG` | Path to the TOML startup config. |
| `--catalog` | `BASIL_CATALOG` | Path to the catalog JSON. Required. |
| `--policy` | `BASIL_POLICY` | Path to the policy JSON. Required. |
| `--bundle` | `BASIL_BUNDLE` | Path to the `0600` sealed bundle. Required. |
| `--socket` | `BASIL_SOCKET` | Unix socket to listen on. |
| `--vault-addr` | `VAULT_ADDR` | Default backend address when a credential pins none. |

{% best() %}
Run `basil config check --catalog … --policy … --bundle …` in CI and before every deploy. It parses
both files, confirms each backend can provide what the catalog requires, and probes the backend for
declared keys. Add `--require` to exit non-zero when a required (`missing=error`) key is absent,
turning a 3am surprise into a failed pipeline.
{% end %}

{% note() %}
The catalog and policy are normally generated from your NixOS configuration (see
[Make it your own](/getting-started/make-it-your-own/)), which validates them a second time at build.
The JSON files are the export Basil consumes; you rarely hand-edit them.
{% end %}

## Where to go next

- [The catalog](/configuration/catalog/): the keys Basil knows about and where they live.
- [The policy](/configuration/policy/): who may do what, default-deny.
- [Backends & capabilities](/configuration/backends/): what a backend provides and `required ⊆ provided`.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): the backend credential and how it's sealed.
