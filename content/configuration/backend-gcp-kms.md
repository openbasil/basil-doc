+++
title = "Google Cloud KMS"
weight = 46
+++

# Google Cloud KMS

Google Cloud KMS is an **in-place transit** backend: the private key is generated inside Cloud KMS
and cannot be exported, so Basil never sees key bytes. Basil brokers the *operation*, not the key. A
sign, verify, encrypt, or decrypt request arrives over the local socket, Basil authorizes the caller
against the catalog and policy, then calls Cloud KMS to perform the operation on the key that stays
put. The identity Basil authenticates as gets only permission to *use* the keys, never to read or
export them, which is exactly the least-privilege posture you want fronting a KMS.

This page takes you end to end: the service account and IAM grants, the key ring and keys, the catalog
and credential wiring, and how to confirm it works. It assumes you have used Basil with a
vault-compatible backend before. If not, start with the [Configuration
overview](/configuration/overview/) and [Backends & capabilities](/configuration/backends/) first.

## How Basil uses Cloud KMS

Basil talks to Cloud KMS over gRPC and HTTP/2 through the opt-in `gcp-kms` build feature. It calls
a deliberately small set of RPCs, and each one maps to a single Cloud KMS IAM permission. The table
below lists the minimum permissions required for each operation.

| Basil operation | Cloud KMS RPC | IAM permission it needs |
| --- | --- | --- |
| Startup reconcile / `config check` existence probe | `GetCryptoKey` | `cloudkms.cryptoKeys.get` |
| Sign (`ES256`/`ES384`, `Ed25519`) | `AsymmetricSign` | `cloudkms.cryptoKeyVersions.useToSign` |
| Get public key (and JWKS) | `GetPublicKey` | `cloudkms.cryptoKeyVersions.viewPublicKey` |
| Verify a signature | none (done locally) | `cloudkms.cryptoKeyVersions.viewPublicKey` |
| Encrypt (`AES-256-GCM`) | `Encrypt` | `cloudkms.cryptoKeyVersions.useToEncrypt` |
| Decrypt (`AES-256-GCM`) | `Decrypt` | `cloudkms.cryptoKeyVersions.useToDecrypt` |
| Provision a key (optional) | `CreateCryptoKey` | `cloudkms.cryptoKeys.create` |

Permissions you don't need for Basil:

**Cloud KMS has no server-side asymmetric verify**, so Basil fetches the public key and verifies
the signature in its own process. The runtime identity therefore never needs
`cloudkms.cryptoKeyVersions.useToVerify`.

**Provisioning is a separate concern from serving**. Creating keys is a one-time admin action.
Basil doesn't need `cloudkms.cryptoKeys.create`. That's more appropriate for a provisioner
identity (a person, or your CI) instead. The sections below split the grants exactly this way.

{% note(title="Basil owns the nonces") %}
The `Encrypt` ciphertext Cloud KMS returns is opaque and self-describing: Cloud KMS chose and embedded
the nonce and the key version. There is no caller-supplied nonce path to get wrong, which is the same
footgun-free `AES-256-GCM` contract Basil enforces everywhere.
{% end %}

## Before you begin

You need the `gcloud` CLI authenticated as a project owner or IAM admin, a target project, and a
`basil` binary built with the `gcp-kms` feature. A binary compiled without it fails closed at startup
with `kind gcp-kms requires the gcp-kms feature` rather than silently ignoring the backend. Throughout,
replace `PROJECT` with your project id and `us-west1` with your chosen KMS location (`global` is also
valid).

## Create the service account and grant IAM

Basil authenticates to Cloud KMS as a **service account**. Create one dedicated to the broker so its
grants are auditable and revocable on their own.

To *create* the service account and (only if you plan to seal a key file, see below) its JSON key, the
operator running `gcloud` needs these project-level roles:

| Task | Role to run it |
| --- | --- |
| Create the service account | `roles/iam.serviceAccountCreator` (or `roles/iam.serviceAccountAdmin`) |
| Create a JSON key for it | `roles/iam.serviceAccountKeyAdmin` |
| Bind KMS roles on the key ring | `roles/cloudkms.admin` on the ring (grants `setIamPolicy` there) |

Create the account:

```sh
gcloud iam service-accounts create basil-broker \
  --project PROJECT \
  --display-name "Basil broker (Cloud KMS runtime)"
```

### The runtime grant (least privilege)

Scope the broker's grants to the **key ring**, not the project, so the broker can only touch the keys
you route to it. The tightest predefined-role set that covers Basil's runtime RPCs is `signer` plus
`publicKeyViewer` plus `cryptoKeyEncrypterDecrypter` plus `viewer`:

```sh
RING="basil"
LOCATION="us-west1"
SA="basil-broker@PROJECT.iam.gserviceaccount.com"

for ROLE in \
  roles/cloudkms.viewer \
  roles/cloudkms.signer \
  roles/cloudkms.publicKeyViewer \
  roles/cloudkms.cryptoKeyEncrypterDecrypter
do
  gcloud kms keyrings add-iam-policy-binding "$RING" \
    --project PROJECT --location "$LOCATION" \
    --member "serviceAccount:$SA" --role "$ROLE"
done
```

Grant only the roles the deployment actually uses. Every Cloud KMS-backed broker still needs
`viewer`, because startup reconcile reads the base `CryptoKey` with `GetCryptoKey` before Basil will
use or generate the key. A broker that only signs needs `viewer` plus `signer` plus
`publicKeyViewer`; drop `cryptoKeyEncrypterDecrypter` if you route no `AES-256-GCM` keys to Cloud
KMS.

{% caution(title="The predefined viewer role is broader than Basil's probe") %}
`roles/cloudkms.viewer` is the predefined role that carries `cloudkms.cryptoKeys.get`, but Google also
puts list/read permissions in that role. If you need exact least privilege, use a custom role with the
permissions below instead of the predefined-role set.
{% end %}

{% caution(title="Why not roles/cloudkms.signerVerifier") %}
`roles/cloudkms.signerVerifier` is convenient because it is one role, but it also grants
`cloudkms.cryptoKeyVersions.useToVerify`, which Basil never calls (it verifies locally). Preferring
`signer` plus `publicKeyViewer` avoids the unused server-side verify grant; use the custom role below
if you also need the read scope to match exactly.
{% end %}

If you want the grant tighter than any predefined role, define a custom role with exactly the five
permissions Basil uses at runtime, then bind it on the ring. Write the definition to a file:

```yaml
title: "Basil KMS runtime"
description: "Least-privilege runtime permissions for the Basil broker"
stage: "GA"
includedPermissions:
- cloudkms.cryptoKeys.get
- cloudkms.cryptoKeyVersions.viewPublicKey
- cloudkms.cryptoKeyVersions.useToSign
- cloudkms.cryptoKeyVersions.useToEncrypt
- cloudkms.cryptoKeyVersions.useToDecrypt
```

Then create and bind it. Keep `cloudkms.cryptoKeys.get` for every Cloud KMS-backed deployment; drop
only the signing or encrypt/decrypt permissions the deployment does not use:

```sh
gcloud iam roles create basilKmsRuntime --project PROJECT \
  --file basil-kms-runtime.yaml

gcloud kms keyrings add-iam-policy-binding basil \
  --project PROJECT --location us-west1 \
  --member "serviceAccount:basil-broker@PROJECT.iam.gserviceaccount.com" \
  --role projects/PROJECT/roles/basilKmsRuntime
```

### The provisioner grant

Key creation needs `cloudkms.cryptoKeys.create` (and `cloudkms.keyRings.create` for the ring itself).
`roles/cloudkms.admin` bundles both. Give it to the human operator or CI identity that provisions, and
keep it off the broker's runtime account:

```sh
gcloud kms keyrings add-iam-policy-binding basil \
  --project PROJECT --location us-west1 \
  --member "user:provisioner@example.com" \
  --role roles/cloudkms.admin
```

Creating the ring itself is a project-level action (the ring does not exist yet to bind against), so
the provisioner needs `roles/cloudkms.admin` at the project the first time, or you create the ring once
as a project admin and scope everything after that to the ring.

## Provision the key ring and keys

Create the ring, then a key per purpose. Basil supports `Ed25519`, `ES256` (P-256), and `ES384`
(P-384) for signing, and `AES-256-GCM` for encrypt and decrypt. Use the matching `gcloud` algorithm
token:

```sh
gcloud kms keyrings create basil --project PROJECT --location us-west1

gcloud kms keys create broker-response \
  --project PROJECT --keyring basil --location us-west1 \
  --purpose asymmetric-signing --default-algorithm ec-sign-ed25519 \
  --protection-level software

gcloud kms keys create request-envelope \
  --project PROJECT --keyring basil --location us-west1 \
  --purpose encryption --default-algorithm google-symmetric-encryption \
  --protection-level software
```

For an ECDSA signing key use `--default-algorithm ec-sign-p256-sha256` or `ec-sign-p384-sha384`. When
*Basil* provisions a key it requests the `software` protection level; when you provision with `gcloud`
you may choose `hsm` instead, and Basil's sign, encrypt, and decrypt calls work the same either way.

{% note(title="What Cloud KMS cannot do here") %}
`ES512` (P-521) is unavailable because Cloud KMS exposes no P-521 signing key, and `RSA` signing,
`ChaCha20-Poly1305`, and the post-quantum algorithms are not wired to this backend. A request for one
of those fails closed rather than falling back. See the capability list at the end of this page.
{% end %}

## Declare the backend and keys in the catalog

The catalog is the exported JSON Basil loads at startup (`camelCase` keys). Add the backend under
`backends` with `kind` set to `gcp-kms`, then route keys to it. The `gcp-kms` backend takes its
project, location, and key ring from the sealed credential (next section), not from the catalog, so the
schema-required `addr` field is only a readable label here. Declaring `engines: ["transit"]` turns on
capability enforcement for the backend.

```json
{
  "schemaVersion": 1,
  "backends": {
    "gcp": {
      "kind": "gcp-kms",
      "addr": "projects/PROJECT/locations/us-west1/keyRings/basil",
      "engines": ["transit"]
    }
  },
  "keys": {
    "broker.response": {
      "class": "asymmetric",
      "keyType": "ed25519",
      "backend": "gcp",
      "engine": "transit",
      "path": "broker-response/cryptoKeyVersions/1",
      "missing": "error",
      "description": "broker response signing key (Cloud KMS)"
    },
    "request.envelope": {
      "class": "symmetric",
      "keyType": "aes-256-gcm",
      "backend": "gcp",
      "engine": "transit",
      "path": "request-envelope",
      "missing": "error",
      "description": "request envelope AEAD key (Cloud KMS)"
    }
  }
}
```

The `path` is where Cloud KMS's addressing rules meet the catalog, and there are two rules to get right.

{% caution(title="Asymmetric paths must pin an explicit cryptoKeyVersion") %}
Cloud KMS requires an exact version to sign or read a public key, so an `asymmetric` key's `path` must
end in `/cryptoKeyVersions/<N>` (for example `broker-response/cryptoKeyVersions/1`). A versionless
asymmetric path is rejected at request time. A `symmetric` key's `path` is just the crypto-key id with
no version: Cloud KMS selects the primary version and binds it into the ciphertext itself.
{% end %}

The other rule concerns the crypto-key id in `path`. If the base id (the part before
`/cryptoKeyVersions/`) is already a valid Cloud KMS crypto-key id (alphanumeric, `-`, `_`, at most 63
characters), Basil uses it verbatim, so it must equal the id you created with `gcloud`. If it contains
other characters (for example dots, as in `jwt.signing.primary`), Basil rewrites it to a slugged,
hashed id, which will *not* match a hand-provisioned key. For pre-provisioned Cloud KMS keys, name the
key with a KMS-valid id and use exactly that id in `path`.

## Give Basil its credential

The sealed bundle carries a `GcpKms` credential for the backend id you used in the catalog. It always
holds the non-secret addressing (project, location, key ring). How Basil *authenticates* has two modes.

**Application Default Credentials (ADC), recommended on GKE or GCE.** Attach the `basil-broker` service
account to the workload and Basil resolves credentials from the environment
(`GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_APPLICATION_CREDENTIALS_JSON`) or the metadata server. No
key material is sealed in the bundle at all. This is the least-standing-secret option: rotate the
binding, not a file. Seal a `GcpKms` credential with just the addressing:

```sh
basil bundle set-backend /var/lib/basil/bundle.sealed \
  --backend id=gcp,type=gcp-kms,project=PROJECT,location=us-west1,key-ring=basil \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase
```

**Sealed service-account JSON, for non-GKE, cross-cloud, or CI hosts** where ambient credentials are
not available. Create a JSON key for the service account and seal the whole file into the bundle with
`key-file`. Basil uses it in place of ADC when present:

```sh
gcloud iam service-accounts keys create /run/secrets/gcp-sa.json \
  --iam-account basil-broker@PROJECT.iam.gserviceaccount.com

basil bundle set-backend /var/lib/basil/bundle.sealed \
  --backend id=gcp,type=gcp-kms,project=PROJECT,location=us-west1,key-ring=basil,key-file=/run/secrets/gcp-sa.json \
  --open passphrase:file=/run/secrets/basil-unlock-passphrase
```

The `key-file` is read from a `0600` file into zeroizing memory and sealed as one opaque secret; the
plaintext file on disk is yours to remove afterward. Prefer ADC when you can, and treat any
service-account key file as a long-lived secret that must be scoped and rotated like the vault itself.

{% best(title="Deposit a KMS credential without opening the whole bundle") %}
When a cloud administrator owns the service-account JSON but should not hold the unlock secret that
exposes every other backend credential, use a signed **credential deposit** instead of `set-backend`:
the admin appends only the `gcp` credential, and Basil overlays it at startup after verifying the
allow-list and signature. The `type=gcp-kms` field syntax is identical. See the deposit workflow in
[Unlock & the sealed bundle](/configuration/unlock-and-bundle/).
{% end %}

## Verify the wiring

Confirm the catalog and backend agree before you depend on them. `basil config check` parses the
catalog and policy, enforces that each backend provides what the catalog requires, and read-only probes
the backend for declared keys. Add `--require` to exit non-zero when a `missing=error` key is absent,
so a broken deploy fails the pipeline instead of surfacing under traffic:

```sh
basil config check --catalog /etc/basil/catalog.json \
  --policy /etc/basil/policy.json \
  --bundle /var/lib/basil/bundle.sealed --require
```

`basil doctor` runs broader preflight environment and deployment checks, and once the agent is running,
`basil ready` maps runtime readiness (can it actually serve, are required keys reachable) to a process
exit code your orchestrator can gate on.

{% caution(title="The live probe needs working credentials and network") %}
The key-existence probe in `config check` and the readiness reachability check call Cloud KMS
(`GetCryptoKey` for the base key, and `GetPublicKey` when Basil needs the public half), so they need
resolvable ADC or a sealed key file and outbound network to `cloudkms.googleapis.com`. A probe
failure there points at credentials, IAM, or connectivity, not at a catalog mistake.
{% end %}

{% caution(title="Doctor does not prove the Cloud KMS IAM path") %}
`basil doctor` catches feature and configuration mismatches, but it does not unlock the broker or run
startup reconcile against Cloud KMS. A green `doctor` does not prove that `cloudkms.cryptoKeys.get`
is present; a missing grant surfaces when `config check`, `ready`, or the broker startup reconcile
performs the live key-existence probe.
{% end %}

## Capabilities and honesty

The Cloud KMS backend implements the transit-shaped operations and nothing else. This is deliberate:
Basil fails closed on anything it does not truly support rather than pretending.

| Status | Capability on Cloud KMS |
| --- | --- |
| Supported | `Ed25519`, `ES256` (P-256), `ES384` (P-384) signing and local verify |
| Supported | `AES-256-GCM` encrypt and decrypt |
| Supported | Optional key provisioning via `CreateCryptoKey` |
| Not supported | `ES512` / P-521, `RSA` signing, `ChaCha20-Poly1305`, post-quantum algorithms |
| Not supported | KV storage, PKI / X.509-SVID issuance, server-side verify, NATS minting over KMS |

For the full backend-kind comparison and the custody model, see [Backends &
capabilities](/configuration/backends/) rather than duplicating it here.

Rotation is worth calling out. Because an asymmetric `path` pins an explicit `cryptoKeyVersions/<N>`,
rotating an asymmetric Cloud KMS key means provisioning a new version and updating the catalog `path`
to point at it, not an in-place primary-version bump. Symmetric keys rotate transparently because Cloud
KMS binds the version into each ciphertext. See [Rotating keys](/operations/rotating-keys/).

{% caution(title="Not exercised against live Cloud KMS in CI") %}
As of this writing, Basil's CI has no live Google Cloud KMS lane. The offline unit tests cover the
resource-name construction (key-ring, crypto-key, and version paths); the sign, verify, encrypt,
decrypt, and provisioning calls themselves require live Cloud KMS credentials and are not run in CI.
Treat the end-to-end flow as validated by construction and design, and verify it against your own
project with `basil config check` before you rely on it.
{% end %}

## Where to go next

- [Backends & capabilities](/configuration/backends/): the backend-kind matrix and the custody model.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): where the `GcpKms` credential lives and the deposit workflow.
- [The catalog (keys)](/configuration/catalog/): the key-entry fields the snippet above uses.
- [Rotating keys](/operations/rotating-keys/): versioned rotation for pinned Cloud KMS asymmetric keys.
