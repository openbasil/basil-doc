+++
title = "AWS KMS"
weight = 44
+++

# AWS KMS

When you back a key with **AWS KMS**, the private key is created inside KMS and never leaves it. There
is nothing to export, nothing to materialize, and no key bytes to steal off the broker host. Basil
authenticates the caller, checks policy, and then asks KMS to perform the one operation. The signature
or ciphertext comes back; the key stays put. This is the same **in-place transit** custody model as the
`vault` backend, pointed at a cloud service instead of a self-hosted one.

That custody is the whole reason to choose KMS. It is also the reason this page spends most of its
length on *identity*: because Basil holds no key, the only thing standing between a request and a KMS
operation is the AWS IAM policy attached to whatever identity the broker runs as. Get that policy right
and least privilege is enforced by AWS itself. This page walks the full path: the exact IAM policies
Basil needs (derived from the operations the backend actually calls), provisioning keys without the
console, wiring the catalog, and depositing the credential into the sealed bundle.

{% note() %}
The AWS KMS backend lives behind the `aws-kms` cargo feature and is **off by default**. The operations
below are implemented and unit-tested for their encoding logic, but they are **not exercised against a
live AWS account in this repository's CI** (which runs live `OpenBao`/Vault only). Treat a first
deployment as something to validate end to end yourself.
{% end %}

## What KMS gives you, and what it does not

A KMS backend provides exactly one engine: **`transit`**. It brokers `sign`, `verify`, `encrypt`, and
`decrypt` in place, reads public material, and (with the right identity) provisions keys. It does not
provide `kv2` stored values, `pki` leaf issuance, NATS identity minting, or the materialize-to-use
path. Those stay on `vault` or `keystore` backends. See
[Backends & capabilities](/configuration/backends/) for the full capability matrix rather than trusting
this summary in isolation.

The supported algorithms are a deliberate subset of what the catalog can name:

| Catalog `keyType` | KMS `KeySpec` | KMS `KeyUsage` | Basil operation |
| --- | --- | --- | --- |
| `ed25519` | `ECC_NIST_EDWARDS25519` | `SIGN_VERIFY` | sign / verify (raw message) |
| `ecdsa-p256` | `ECC_NIST_P256` | `SIGN_VERIFY` | sign / verify as `ES256` |
| `ecdsa-p384` | `ECC_NIST_P384` | `SIGN_VERIFY` | sign / verify as `ES384` |
| `ecdsa-p521` | `ECC_NIST_P521` | `SIGN_VERIFY` | sign / verify as `ES512` |
| `aes-256-gcm` | `SYMMETRIC_DEFAULT` | `ENCRYPT_DECRYPT` | encrypt / decrypt |

Anything else fails closed. `rsa-2048`, `chacha20-poly1305`, `x25519`, and the ML-KEM / ML-DSA
post-quantum types are refused by the backend rather than silently substituted. A few honest edges to
plan around:

- **ECDSA signatures** come back from KMS as ASN.1 DER; Basil converts them to and from the raw
  `r‖s` form that JWS expects. `ES512` needs a P-521 key, which is why `ecdsa-p521` maps straight to it.
- **`ed25519`** relies on the `ECC_NIST_EDWARDS25519` key spec, which is comparatively recent in KMS.
  Confirm it is offered in your target region before you commit a catalog to it.
- **Symmetric encrypt/decrypt** uses a KMS-owned nonce and an opaque, self-describing ciphertext.
  Basil never supplies the nonce, and KMS caps a single `encrypt`/`decrypt` payload at 4 KiB. For larger
  payloads, use an envelope pattern (encrypt a data key, not the payload).
- **Rotation is not in-place.** KMS has no transit-style version counter for an asymmetric key, so a
  rotate is a *new key plus alias swap*, not a version bump. See [Rotating keys](/operations/rotating-keys/).

## Build with the `aws-kms` feature

The AWS SDK is heavy, so the backend is gated. Build the `basil` binary with the feature enabled:

```sh
cargo build --release --features aws-kms
# or, to include every optional backend and integration:
cargo build --release --all-features
```

If a catalog names an `aws-kms` backend but the running binary was built without the feature,
`basil doctor` reports the gap by name (`feature_compatibility`) instead of failing obscurely at
request time. Preflight with it before you deploy: see [Doctor](/operations/doctor/).

## The IAM identities Basil needs

Split the work across **two** identities, because they need very different authority and run at
different times.

- The **runtime** identity is what the long-running broker assumes. It should be able to *use* keys and
  nothing more: sign, verify, get public keys, encrypt, decrypt. It never needs to create a key.
- The **provisioner** identity is used only when keys are first created (by Basil's own provisioning
  path, or by an operator running `aws kms` directly). It creates keys and aliases. Keeping it separate
  means the steady-state broker cannot mint new key material even if its credentials leak.

Both policies below list *only* the KMS actions the corresponding code path invokes. Nothing is padded
"just in case". One action is easy to overlook: the backend **does** call `kms:DescribeKey`, because the
startup reconcile probes each catalog key for existence with a non-mutating `DescribeKey` before the
broker will use or generate it. Without it the broker fails to reconcile and never binds its socket. It
still never calls `kms:TagResource` or `kms:ScheduleKeyDeletion`, so those stay deliberately absent.

### Runtime policy (least privilege for the broker)

The broker's backend calls exactly six KMS actions. Five are the in-place operations, `Sign`, `Verify`,
`GetPublicKey`, `Encrypt`, and `Decrypt`; the sixth, `DescribeKey`, is the existence probe the startup
reconcile runs against every catalog key before the broker binds. Scope them to the specific key ARNs
the catalog uses. Save this as `basil-kms-runtime.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BasilBrokerInPlaceOps",
      "Effect": "Allow",
      "Action": [
        "kms:Sign",
        "kms:Verify",
        "kms:GetPublicKey",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:Decrypt"
      ],
      "Resource": [
        "arn:aws:kms:us-east-1:111122223333:key/1111abcd-12ab-34cd-56ef-1234567890ab",
        "arn:aws:kms:us-east-1:111122223333:key/2222abcd-12ab-34cd-56ef-1234567890ab"
      ]
    }
  ]
}
```

An IAM statement identifies a key operation by the key's **ARN**, never by its alias name. If you would
rather grant the whole Basil alias namespace than enumerate key ARNs, keep `"Resource"` on the keys and
add a condition on the alias used to reach them:

```json
"Condition": {
  "ForAnyValue:StringLike": { "kms:RequestAlias": "alias/basil/*" }
}
```

{% best() %}
Give the broker the runtime policy and nothing else. If a deployment only ever uses pre-provisioned
keys (the recommended posture, with each catalog key set to `missing: error`), this is the *complete*
set of KMS permissions the running daemon requires.
{% end %}

### Provisioner policy (create keys and aliases)

Key creation requires `kms:CreateKey`, `kms:CreateAlias`, and `kms:GetPublicKey` (Basil reads the public
half back immediately after creating an asymmetric key). A provisioning run reconciles first, so it also
needs `kms:DescribeKey`: reconcile probes a key **absent** before it decides to create it. Save this as
`basil-kms-provisioner.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BasilCreateKeys",
      "Effect": "Allow",
      "Action": "kms:CreateKey",
      "Resource": "*"
    },
    {
      "Sid": "BasilCreateAliases",
      "Effect": "Allow",
      "Action": "kms:CreateAlias",
      "Resource": [
        "arn:aws:kms:us-east-1:111122223333:alias/basil/*",
        "arn:aws:kms:us-east-1:111122223333:key/*"
      ]
    },
    {
      "Sid": "BasilReadAndProbeKeys",
      "Effect": "Allow",
      "Action": [
        "kms:GetPublicKey",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:us-east-1:111122223333:key/*"
    }
  ]
}
```

Two AWS rules are important for understanding that document:

- **`kms:CreateKey` cannot be scoped to a key ARN.** The key does not exist yet, so AWS requires
  `"Resource": "*"`. Tighten it with condition keys (for example `aws:RequestTag`) if your account
  policy demands it.
- **`kms:CreateAlias` needs permission on *both* the alias and the target key.** The alias resource is
  scoped to `alias/basil/*` because that is the namespace Basil generates deterministic aliases in; the
  key resource is broad because the target key ARN is freshly minted. If you point a catalog `path` at a
  custom alias name, widen the alias resource to match.

{% caution(title="The provisioner is an admin identity, not the daemon") %}
Do not attach the provisioner policy to the long-running broker. Attach it to a break-glass operator
role, a one-shot bootstrap job, or a CI provisioning step. In steady state the broker should not be able
to call `kms:CreateKey` at all.
{% end %}

### How Basil resolves AWS credentials

Basil holds **no AWS secret**. The backend builds its KMS client from the **ambient AWS credential
chain**: environment variables, a shared profile in `~/.aws/config` / `~/.aws/credentials`, SSO, an EC2
instance profile via IMDS, or an EKS web-identity token (IRSA / Pod Identity). Whatever the AWS SDK's
default provider chain resolves is what Basil uses. That is why the sealed bundle carries only a region
and an optional profile name for this backend, never a key.

Because credential resolution is the SDK's job, both an IAM-role path and an access-key path work. The
role path is the better security posture: no long-lived secret to store, rotate, or leak. Use access
keys only where an assumable role is genuinely unavailable.

{% note() %}
Basil relies on the AWS SDK's default chain rather than implementing provider logic itself. As far as we
know every provider in that chain (instance profile, IRSA, static keys) works, but the individual
providers are not exercised in this repository's CI. Validate whichever one you deploy.
{% end %}

### Role path (instance profile or IRSA)

First create the customer-managed policies once, then a role that trusts the right principal.

```sh
aws iam create-policy --policy-name BasilKmsRuntime \
  --policy-document file://basil-kms-runtime.json
aws iam create-policy --policy-name BasilKmsProvisioner \
  --policy-document file://basil-kms-provisioner.json
```

For an **EC2 host**, trust the EC2 service and expose the role through an instance profile. Save this as
`ec2-trust.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

```sh
aws iam create-role --role-name basil-agent \
  --assume-role-policy-document file://ec2-trust.json
aws iam attach-role-policy --role-name basil-agent \
  --policy-arn arn:aws:iam::111122223333:policy/BasilKmsRuntime
aws iam create-instance-profile --instance-profile-name basil-agent
aws iam add-role-to-instance-profile \
  --instance-profile-name basil-agent --role-name basil-agent
```

For **EKS (IRSA)**, trust the cluster's OIDC provider and pin the Kubernetes service account. Save this
as `irsa-trust.json` (substitute your OIDC provider URL, account, and namespace/service-account):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE:sub": "system:serviceaccount:basil:basil-agent",
          "oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B71EXAMPLE:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

```sh
aws iam create-role --role-name basil-agent \
  --assume-role-policy-document file://irsa-trust.json
aws iam attach-role-policy --role-name basil-agent \
  --policy-arn arn:aws:iam::111122223333:policy/BasilKmsRuntime
```

Then annotate the pod's service account with
`eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/basil-agent` so the web-identity token lands
where the SDK expects it.

### Access-key path

Where no assumable role exists, attach the policy to an IAM user and mint an access key:

```sh
aws iam create-user --user-name basil-agent
aws iam attach-user-policy --user-name basil-agent \
  --policy-arn arn:aws:iam::111122223333:policy/BasilKmsRuntime
aws iam create-access-key --user-name basil-agent
```

Deliver the resulting `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` to the broker through the
environment or a named profile in `~/.aws/credentials`. If you use a named profile, name it in the
backend credential (below) so the right identity is selected.

{% danger() %}
A static access key is a long-lived secret sitting on the broker host. It is the identity to a `sign`
or `decrypt` on every key in the runtime policy. Prefer the role path; where you cannot, rotate the key
on a schedule and scope the runtime policy to the exact key ARNs.
{% end %}

## Provision the keys and aliases

You have two console-free options, and they map cleanly onto the two IAM identities.

**Let Basil provision.** Declare the backend's `mintKeyTypes` and set a key's `missing` policy to
`generate` (or drive it with the `new-key` client command). Reconcile then calls `kms:CreateKey` and
`kms:CreateAlias`, reads the public half back, and records the key. This path needs the **provisioner**
policy. Basil names the alias deterministically in the `alias/basil/` namespace, so a given catalog
`path` always maps to the same alias.

**Provision out of band with `aws kms`.** Create the keys yourself, then point the catalog `path` at the
resulting alias or key ARN. This keeps the broker on the runtime policy only.

```sh
# An ES256 signing key
aws kms create-key --key-spec ECC_NIST_P256 --key-usage SIGN_VERIFY \
  --description "Basil jwt signing key"
aws kms create-alias --alias-name alias/basil/jwt-signing-primary \
  --target-key-id <key-id-from-create-key>

# A symmetric AES-256-GCM key
aws kms create-key --key-spec SYMMETRIC_DEFAULT --key-usage ENCRYPT_DECRYPT \
  --description "Basil payload AEAD key"
aws kms create-alias --alias-name alias/basil/payload-aead \
  --target-key-id <key-id-from-create-key>
```

A catalog `path` may be an alias (`alias/basil/jwt-signing-primary`), a full key ARN, or a bare key-id
UUID. Any other string is treated as a logical name and resolved to a generated `alias/basil/<name>-<hash>`
alias, which is what the provisioning path creates.

## Declare the backend and keys in the catalog

Add a `backends` entry of kind `aws-kms` that *provides* `transit`, and point keys at it. The catalog is
authored and exported to JSON with camelCase keys:

```json
{
  "schemaVersion": 1,
  "backends": {
    "kms": {
      "kind": "aws-kms",
      "addr": "aws-kms:us-east-1",
      "engines": ["transit"],
      "mintKeyTypes": ["ecdsa-p256", "aes-256-gcm"]
    }
  },
  "keys": {
    "jwt.signing.primary": {
      "class": "asymmetric",
      "keyType": "ecdsa-p256",
      "backend": "kms",
      "engine": "transit",
      "path": "alias/basil/jwt-signing-primary",
      "writable": false,
      "missing": "error",
      "description": "JWT signing key held in AWS KMS"
    },
    "payload.aead": {
      "class": "symmetric",
      "keyType": "aes-256-gcm",
      "backend": "kms",
      "engine": "transit",
      "path": "alias/basil/payload-aead",
      "writable": false,
      "missing": "error",
      "description": "Envelope AEAD key held in AWS KMS"
    }
  }
}
```

Two things worth calling out:

- The backend's **`addr` is a label** for an `aws-kms` backend, not a routing target. KMS addressing
  comes from the credential's region (below), so use `addr` for human readability. Only `vault`-kind
  backends have their `addr` dialed.
- Declare **`mintKeyTypes`** only for algorithms you want Basil to be able to provision. Leaving it out
  (with every key `missing: error`) is the tightest posture: the catalog can *use* pre-provisioned keys
  but never generate one, matching a broker that holds only the runtime IAM policy. See
  [Capability policy & reconcile](/configuration/capability-and-reconcile/) for how this is enforced at
  startup, and [The catalog](/configuration/catalog/) for every key field.

## Deposit the credential into the bundle

The backend credential is stored in the sealed bundle, alongside the unlock methods. For AWS KMS it
carries only non-secret addressing: a required `region` and an optional `profile`. Add it to a bundle
with `bundle set-backend`, matching the `id` to the catalog backend name (`kms` above):

```sh
basil bundle set-backend creds.sealed \
  --backend id=kms,type=aws-kms,region=us-east-1 \
  --open passphrase:file=/run/basil/pass
```

Add `profile=<name>` to select a named profile from `~/.aws/config`; omit it to use the default chain:

```sh
basil bundle set-backend creds.sealed \
  --backend id=kms,type=aws-kms,region=us-east-1,profile=basil-agent \
  --open passphrase:file=/run/basil/pass
```

You can seed the same `--backend id=...,type=aws-kms,...` spec at `basil bundle create` time, or add it
without opening the bundle through the signed `bundle deposit` flow. See
[Unlock & the sealed bundle](/configuration/unlock-and-bundle/) for the full credential-deposit surface
and the `--open` method syntax.

{% note() %}
Because no AWS secret is sealed, rotating the broker's AWS credentials never touches the bundle. You
rotate the IAM role or access key in AWS; the region in the bundle is unchanged.
{% end %}

## Verify it

Run the preflight and readiness checks before you send real traffic:

- **`basil doctor`** confirms the `aws-kms` feature is built in (`feature_compatibility`) and that the
  catalog and capability policy load and agree. It is the fastest way to catch a feature-gap or a
  `mintKeyTypes` mismatch.
- **`basil ready`** reports broker readiness once it has unlocked and reconciled. See
  [Health & readiness](/operations/health-and-readiness/).

{% caution(title="Doctor does not probe AWS reachability") %}
The `backend_reachability` check probes only `vault`-kind backends (an unauthenticated Vault health
endpoint). It does **not** reach out to AWS KMS, so a green `doctor` does not prove your IAM policy,
region, or credentials are correct. In particular it will not catch a missing `kms:DescribeKey`: that
surfaces only at startup, where the reconcile existence probe fails and the broker never binds its
socket. Confirm the live path yourself by driving one real `sign` and `verify` (or `encrypt` and
`decrypt`) against a KMS-backed key after startup.
{% end %}

## Where to go next

- [Backends & capabilities](/configuration/backends/): the capability matrix and how `required ⊆ provided` is enforced.
- [The catalog](/configuration/catalog/): every key field, including `path`, `missing`, and `mintKeyTypes`.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): where the backend credential lives and how it is deposited.
- [Doctor](/operations/doctor/): preflight the feature and catalog before the daemon unlocks and binds.
