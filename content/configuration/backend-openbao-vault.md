+++
title = "OpenBao & Vault"
weight = 42
+++

# OpenBao & Vault

**OpenBao** (and **HashiCorp Vault** CE, which speaks the same wire API) is Basil's default
strong-custody backend. Its **transit** engine is a keep-in-place cryptographic service: the private
key lives inside the vault and is *never exportable*, so when Basil signs or decrypts, it POSTs the
message to transit and gets back only the result. This is **in-place custody**: key bytes never cross
the Unix socket, never enter Basil's address space, and never touch disk. Basil brokers the
*operation*, not the key.

This page takes you from an empty server to a running broker: a throwaway dev server for evaluation,
then a production setup with the exact mounts Basil talks to, ready-to-upload least-privilege ACL
policies, the sealed credential, and the checks that confirm it all works. For *which* engines and
capabilities a backend provides and how Basil enforces `required ⊆ provided`, see
[Backends & capabilities](/configuration/backends/); this page is the how-to.

{% note(title="One kind, two servers") %}
OpenBao and HashiCorp Vault CE are one backend `kind` (`vault`) to Basil, tested against both. The CLI
binary differs only in name: `bao` for OpenBao, `vault` for HashiCorp Vault. Every command below works
with either. HashiCorp Vault Enterprise is untested: <span class="pill gap">roadmap</span>.
{% end %}

## Dev quickstart (evaluation only)

The fastest way to see Basil work end to end is a **dev-mode** server: in-memory, auto-unsealed, with
a fixed root token and no seal or TLS to manage. Use it to learn the moving parts, never for anything
real.

Start the server and point your shell at it:

```sh
bao server -dev -dev-root-token-id=root -dev-listen-address=127.0.0.1:8200
# in another shell:
export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root
```

Enable the engines Basil uses. In dev mode `secret/` is already a KV-v2 mount, so you only add
`transit`:

```sh
bao secrets enable transit
```

Scaffold a starter config, seal the dev token into a bundle, validate, and run. `basil init`
writes catalog, policy, and agent TOML (never secrets); the token goes into a `0600` file that
`basil bundle create` seals:

```sh
basil init --backend openbao --unlock bip39 --dir ./basil
printf '%s\n' root > ./basil/backend-token
chmod 600 ./basil/backend-token
basil bundle create ./basil/bundle.sealed \
    --slot bip39 \
    --backend id=primary,type=openbao,addr=http://127.0.0.1:8200,token-file=./basil/backend-token
basil doctor -c ./basil/basil-agent.toml
basil agent -c ./basil/basil-agent.toml
```

On first boot Basil's startup reconcile creates the scaffolded `example.signing_key` in transit, then
binds the socket. Exercise it: `basil --socket ./basil/basil.sock sign --key-id example.signing_key
'hello'`. See [First run](/getting-started/first-run/) for the scaffold in full.

{% danger(title="Dev mode is not a deployment") %}
`bao server -dev` holds every key in memory, unsealed, behind an unexpiring root token, over plain
HTTP. It loses all state on exit and has no least-privilege boundary at all. Never point a real
workload at it, and never seal a dev root token into a bundle you keep. The rest of this page is the
path you actually ship.
{% end %}

## Production: enable the mounts Basil talks to

A production server starts **sealed** and must be initialized and unsealed (Shamir shares or an
auto-unseal backend) before it serves any request. That is the server's own seal layer, separate from
Basil's sealed bundle. Once the server is unsealed and reachable over TLS, enable exactly the engines
your catalog routes to:

```sh
bao secrets enable transit                        # sign / verify / encrypt / decrypt in place
bao secrets enable -path=secret -version=2 kv     # stored values + materialize-to-use private halves
bao secrets enable pki                            # only if you use Basil's SPIFFE X.509-SVID issuance
```

Basil reaches these mounts at fixed request shapes. The transit **mount** is a single deployment-wide
setting (`transit-mount`, default `transit`) applied to every `vault` backend; the KV and PKI mounts
are not separately configured, because each key's catalog `path` already carries its own mount
(`secret/data/...`, `pki/issue/...`). Knowing the exact paths matters because they are what your ACL
policy grants:

| Basil operation | HTTP request | ACL capability |
| --- | --- | --- |
| Sign / verify | `POST transit/sign/<key>`, `transit/verify/<key>` | `update` |
| Encrypt / decrypt | `POST transit/encrypt/<key>`, `transit/decrypt/<key>` | `update` |
| Read public half + metadata | `GET transit/keys/<key>` | `read` |
| Reconcile-generate a key | `POST transit/keys/<key>` | `create`, `update` |
| Rotate | `POST transit/keys/<key>/rotate` | `update` |
| Set grace/retention window | `POST transit/keys/<key>/config` | `update` |
| BYOK import | `GET transit/wrapping_key`, `POST transit/keys/<key>/import` | `read`, `update` |
| Read / write a value | `GET` / `POST secret/data/<path>` | `read`, `create`, `update` |
| Issue an X.509 leaf | `POST <pki>/issue/<role>` | `update` |
| Read CA chain + CRL | `GET <pki>/ca_chain`, `<pki>/crl/pem` | `read` |

Transit keys are non-exportable, so even `read` on `transit/keys/*` returns only the public half and
version metadata, never private material. That property is what lets the runtime policy below stay
tight.

## Least-privilege ACL policies

Basil authenticates every backend request with a bearer token in the `X-Vault-Token` header. It never
reads or writes key material outside these paths, so the policy attached to that token is the whole
blast radius if the broker host is compromised. Grant only what the operations above require, and
separate the *running broker* from the *one-time provisioner* that sets the server up.

### The agent runtime policy

This is bound to the role Basil logs in as. Delete any block whose feature your deployment does not
use, and replace `secret`/`pki` with your actual mount names.

```hcl
# basil-agent.hcl: least-privilege policy for the running broker.

# Transit crypto, brokered in place (POST -> update). Key bytes never returned.
path "transit/sign/*"    { capabilities = ["update"] }
path "transit/verify/*"  { capabilities = ["update"] }
path "transit/encrypt/*" { capabilities = ["update"] }
path "transit/decrypt/*" { capabilities = ["update"] }

# Public half + version/algorithm metadata (GET). Transit keys are
# non-exportable, so this never yields private material. To let startup
# reconcile CREATE missing=generate keys, widen this to
# ["read", "create", "update"].
path "transit/keys/*" { capabilities = ["read"] }

# Rotate and set the grace/retention window through the broker (drop if you
# rotate out of band with a separate operator token).
path "transit/keys/*/rotate" { capabilities = ["update"] }
path "transit/keys/*/config" { capabilities = ["update"] }

# BYOK import through the broker (drop if you never import).
path "transit/wrapping_key"  { capabilities = ["read"] }
path "transit/keys/*/import" { capabilities = ["update"] }

# KV-v2 stored values and materialize-to-use private halves. Drop create/update
# if the broker only reads values; scope the path to your key prefixes.
path "secret/data/*" { capabilities = ["read", "create", "update"] }

# PKI leaf issuance (only with Basil's SPIFFE X.509-SVID issuance).
path "pki/issue/*"  { capabilities = ["update"] }
path "pki/ca_chain" { capabilities = ["read"] }
path "pki/crl/pem"  { capabilities = ["read"] }
```

{% best(title="Tighten transit paths to named keys") %}
`transit/sign/*` grants signing with *every* transit key in the mount. If your key set is stable, list
the key names explicitly (`path "transit/sign/web-tls"`, `path "transit/sign/nats-account"`) so a
stolen token cannot exercise a key the broker was never meant to use. Basil already gates each caller
per key through its own policy, but the backend ACL is a second, independent fence.
{% end %}

### The one-time provisioner policy

Setting up mounts, writing the agent policy, and creating the login role are privileged acts that the
running broker must never be able to perform. Use a separate, short-lived token for them (in dev, your
root token stands in). Revoke it when setup is done.

```hcl
# basil-provisioner.hcl: one-time setup, NOT for the running broker.

# Enable/tune the secrets engines Basil uses.
path "sys/mounts/transit" { capabilities = ["create", "update", "read"] }
path "sys/mounts/secret"  { capabilities = ["create", "update", "read"] }
path "sys/mounts/pki"     { capabilities = ["create", "update", "read"] }

# Write the runtime ACL policy.
path "sys/policies/acl/basil-agent" { capabilities = ["create", "update", "read"] }

# Enable AppRole and configure the broker's login role.
path "sys/auth/approle"                  { capabilities = ["create", "update", "read"] }
path "auth/approle/role/basil"           { capabilities = ["create", "update", "read"] }
path "auth/approle/role/basil/role-id"   { capabilities = ["read"] }
path "auth/approle/role/basil/secret-id" { capabilities = ["create", "update"] }

# Seed transit keys / kv values out of band (optional; match your catalog).
path "transit/keys/*" { capabilities = ["create", "read", "update"] }
path "secret/data/*"  { capabilities = ["create", "read", "update"] }

# Instead of AppRole, if the broker authenticates with a SPIFFE JWT-SVID:
path "sys/auth/jwt"        { capabilities = ["create", "update", "read"] }
path "auth/jwt/config"     { capabilities = ["create", "update"] }
path "auth/jwt/role/basil" { capabilities = ["create", "update", "read"] }

# If you use PKI issuance: configure the mount and a role that permits uri_sans.
path "pki/roles/*"         { capabilities = ["create", "update", "read"] }
path "pki/root/generate/*" { capabilities = ["create", "update"] }
path "pki/config/*"        { capabilities = ["create", "update", "read"] }
```

### How Basil obtains its token

Basil supports exactly three ways to get the `X-Vault-Token`, and no others (no `userpass`, no TLS
cert auth). Pick one when you seal the credential:

| Credential | How the token is obtained | When to use |
| --- | --- | --- |
| `VaultToken` | A static token used verbatim on every request. | Dev, or tightly controlled automation. |
| `VaultAppRole` | `role_id` + `secret_id` exchanged once at startup at the fixed path `auth/approle/login`. | The standard production choice. |
| `SpiffeSigner` | Basil self-mints a JWT-SVID and exchanges it at `auth/<jwt-auth-mount>/login`, re-logging in before expiry. No static backend secret on disk. | When you already run SPIFFE. |

For `VaultAppRole`, the AppRole auth method must be mounted at the default `approle` path (Basil posts
to `auth/approle/login`; that mount is not configurable). For `SpiffeSigner`, register the broker's
JWT validation public key with the jwt auth method (`jwt_validation_pubkeys`) and set the config keys
`jwt-auth-mount` (default `jwt`), `jwt-role` (**required**, fails closed if empty), `jwt-audience`
(default `openbao`), and `svid-ttl-secs` (default `300`). In every case, the *authorization* of what
the broker may do is the runtime policy the role's `token_policies` binds.

### Upload the policy and mint the AppRole

```sh
# 1. Upload the runtime policy.
bao policy write basil-agent basil-agent.hcl

# 2. Enable AppRole and bind the policy to a role for the broker.
bao auth enable approle
bao write auth/approle/role/basil \
    token_policies=basil-agent \
    token_ttl=20m token_max_ttl=1h

# 3. Read the role_id (not secret) and mint a secret_id, both into 0600 files.
bao read -field=role_id auth/approle/role/basil/role-id > role-id.txt
bao write -f -field=secret_id auth/approle/role/basil/secret-id > secret-id.txt
chmod 600 role-id.txt secret-id.txt
```

## Deposit the credential and wire the config

Basil never takes a plaintext backend token on the command line. The credential lives in the `0600`
**sealed bundle**, keyed by a backend id that must match the catalog backend name. Seal the AppRole
credential you just minted (the `role_id` is not secret and goes inline; only the `secret_id` is read
from a file):

```sh
basil bundle create /var/lib/basil/bundle.sealed \
    --slot passphrase:file=/run/secrets/basil-unlock-passphrase \
    --slot bip39 \
    --backend id=primary,type=openbao,addr=https://bao.example:8200,role-id="$(cat role-id.txt)",secret-id-file=secret-id.txt
```

The `type=` selects the CLI-facing kind (`openbao` or `vault`; both seal the same `vault` credential).
Swap the credential fields for the other auth methods:

- Static token: `...,token-file=/run/secrets/bao-token`.
- SPIFFE signer: `...,spiffe-key-file=/run/secrets/basil-svid-signer.pem,spiffe-id=spiffe://example.org/basil`.

To rotate just the backend credential later, use `basil bundle set-backend ... --open <slot>`; to hand
one credential to a contributor who should *not* hold the unlock secret, use the signed
`basil bundle deposit` flow. Both are covered in
[Unlock & the sealed bundle](/configuration/unlock-and-bundle/).

{% caution(title="There is no `kms set-cred` command") %}
Depositing or replacing a backend credential is done with `basil bundle create` / `set-backend` /
`deposit`. Older notes referencing a `config bundle set-cred` surface describe a pre-release CLI
that has been removed (the whole `basil config` namespace is gone); there is no separate `kms` verb. The same `bundle` verbs also seal cloud KMS
credentials (`type=aws-kms` / `type=gcp-kms`) when you use those backends instead.
{% end %}

### The catalog and agent config

The catalog is exported JSON with **camelCase** field names and kebab-case enum values. A minimal
backend entry plus one transit signing key (the backend id `primary` matches the `--backend id=` above):

```json
{
  "schemaVersion": 1,
  "backends": {
    "primary": {
      "kind": "vault",
      "addr": "https://bao.example:8200",
      "engines": ["transit", "kv2"],
      "mintKeyTypes": ["ed25519"]
    }
  },
  "keys": {
    "web.tls.signing_key": {
      "class": "asymmetric",
      "keyType": "ed25519",
      "backend": "primary",
      "engine": "transit",
      "path": "web-tls",
      "writable": false,
      "missing": "generate",
      "description": "Web TLS signing key"
    }
  }
}
```

`kind` is `vault` for both OpenBao and HashiCorp Vault. A transit key's `path` is the **bare** key name
(`web-tls`), which Basil composes into `transit/sign/web-tls` and the other verbs; a KV-v2 key's `path`
is the mount-qualified locator (`secret/data/<...>`). `missing: generate` asks the startup reconcile
to create the key, which needs `create`+`update` on `transit/keys/*` in the runtime policy above. Full
schema in [The catalog](/configuration/catalog/).

The agent TOML uses kebab-case keys. The backend address comes from the sealed credential (or
`vault-addr` / `VAULT_ADDR` as a fallback); keep the catalog `addr` in agreement, since `basil doctor`
reads it for its reachability check:

```toml
catalog = "/etc/basil/catalog.json"
policy  = "/etc/basil/policy.json"
bundle  = "/var/lib/basil/bundle.sealed"
socket  = "/run/basil/agent.sock"

vault-addr    = "https://bao.example:8200"
transit-mount = "transit"

# Only for the SpiffeSigner credential:
# jwt-auth-mount = "jwt"
# jwt-role       = "basil"
# jwt-audience   = "openbao"
# svid-ttl-secs  = 300

[unlock]
unlock-passphrase-file = "/run/secrets/basil-unlock-passphrase"
```

## Verify and troubleshoot

Confirm the wiring before and after the broker starts. `basil doctor` resolves the same config the
daemon does and runs read-only diagnostics:

```sh
basil doctor -c /etc/basil/agent.toml            # offline: reachability, bundle perms, catalog/policy, capability
basil doctor -c /etc/basil/agent.toml --keys     # also unlock + read-only key-existence probe
basil doctor -c /etc/basil/agent.toml --strict   # treat warnings as failures too
```

Doctor's `backend_reachability` check hits the unauthenticated `GET /v1/sys/health` on each configured
address, so a `fatal` there means the server is down, sealed, or the address is wrong, independent of
your token. Adding `--keys` unlocks the bundle, performs the AppRole/JWT login, and runs the same
metadata and KV existence reads startup reconcile would, without generating or mutating anything. Read
[Doctor](/operations/doctor/) for every check and its remediation.

Common failure signatures and where they point:

- **`403 permission denied`** on a transit or KV path: the runtime policy is missing that path or
  capability. Cross-check the operation against the ACL table above (a `sign` needs `update` on
  `transit/sign/<key>`, a reconcile-generate needs `create` on `transit/keys/<key>`).
- **Login fails at startup**: the AppRole `secret_id` expired or the `role_id` is wrong, or (for
  SPIFFE) `jwt-role` is unset or the validation public key is not registered.
- **KV value decodes wrong**: Basil stores values base64-encoded under a `value` field. If you seed a
  KV key by hand, write it the same way (`bao kv put secret/<p> value="$(printf '%s' <val> |
  base64 -w0)"`), or the read fails.

For error strings and incident recovery, see [Error reference](/troubleshooting/error-reference/) and
the [Incident runbook](/troubleshooting/incident-runbook/).

## Where to go next

- [Backends & capabilities](/configuration/backends/): what a backend provides and `required ⊆ provided`.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): rotating the credential and signed deposits.
- [Capability policy & reconcile](/configuration/capability-and-reconcile/): what a clean startup checks.
- [Doctor](/operations/doctor/): the full preflight before you start the daemon.
