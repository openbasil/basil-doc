+++
title = "NATS integration"
weight = 40
+++

# NATS integration

Basil treats NATS identity as an operation surface, not a seed-distribution mechanism. NKey issuer
seeds stay in the backend, callers ask Basil to mint or validate JWTs, and policy decides which local
uids may use which issuer keys.

The broker API has a dedicated **`NatsService`** for all NATS-specific RPCs. `MintingService`
keeps only generic JWT minting and X.509 certificate issuance.

## Service split

| Surface | RPCs |
| --- | --- |
| `MintingService` | `MintJwt`, `IssueCertificate` |
| `NatsService` | `MintNatsUser`, `MintNatsAccount`, `MintNatsOperator`, `MintNatsSigner`, `MintNatsServer`, `MintNatsCurve`, `SignNatsJwt`, `ValidateNatsJwt`, `EncryptNatsCurve`, `DecryptNatsCurve` |

The `basil` CLI exposes the common mint/sign path (`mint-nats-user`, `sign-nats-jwt`) and a local
`.creds` assembler (`issue-nats-creds`). Use the Rust, Go, or generated gRPC clients for
`ValidateNatsJwt` and NATS curve xkey boxes.

## Catalog and policy

Declare NATS signing keys as transit-backed `ed25519-nkey` keys with a `nats_type` label. There is no
catalog `engine: nats`; the NATS role is metadata on a signing key.

```json
{
	"keys": {
		"nats.account": {
			"class": "asymmetric",
			"keyType": "ed25519-nkey",
			"backend": "bao",
			"path": "nats/account",
			"missing": "generate",
			"labels": { "nats_type": "A" }
		},
		"nats.xkey": {
			"class": "sealing",
			"keyType": "x25519",
			"backend": "bao",
			"engine": "kv2",
			"path": "secret/data/nats/xkey/private",
			"publicPath": "secret/data/nats/xkey/public",
			"missing": "error"
		}
	}
}
```

Policy grants are separate, so a service that can mint a user JWT does not automatically validate or
decrypt NATS curve payloads:

```yaml
roles:
  nats_minter:    [mint, sign_nats_jwt]
  nats_validator: [validate_nats_jwt]
  nats_box:       [encrypt_nats_curve, decrypt_nats_curve]
```

`ValidateNatsJwt` authorizes `op:validate_nats_jwt` only for candidate signers supplied as catalog
keys. A raw public NKey candidate is just public material, so it does not require a catalog-key grant.
The RPC itself still requires an attested peer that resolves to a policy subject, and the presented
token is bounded by the broker payload cap; an unknown caller is rejected before any verification
runs.

## Validate a presented NATS JWT

Validation is an authoritative result, not an exception path. A malformed token, bad signature,
unknown signer, expired token, future `nbf`, or wrong `nats.type` returns `valid=false` with a typed
reason; transport errors are reserved for "the broker could not perform validation."

Rust:

```rust
use basil::{AllowedNatsSigner, Client, NatsJwtType, NatsJwtValidationReason};

# async fn run(mut client: Client, token: &str) -> basil::Result<()> {
let result = client
    .validate_nats_jwt(
        token,
        [
            AllowedNatsSigner::key_id("nats.account"),
            AllowedNatsSigner::nats_public_key("ADVCJ4FZLS..."),
        ],
        Some(NatsJwtType::User),
    )
    .await?;

if !result.valid {
    match result.reason {
        NatsJwtValidationReason::Expired => { /* refresh */ }
        NatsJwtValidationReason::UnknownSigner => { /* reject issuer */ }
        _ => { /* reject */ }
    }
}
# Ok(())
# }
```

Go:

```go
res, err := client.Nats().ValidateNatsJwt(ctx, basil.ValidateNatsJwtRequest{
    JWT: token,
    AllowedSigners: []basil.AllowedSigner{
        basil.AllowedSignerKeyID("nats.account"),
        basil.AllowedSignerNatsPublicKey("ADVCJ4FZLS..."),
    },
    ExpectedType: basil.NatsJwtTypeUser,
})
if err != nil {
    return err
}
if !res.Valid {
    switch res.Reason {
    case basil.NatsJwtValidationReasonExpired:
        // refresh
    case basil.NatsJwtValidationReasonUnknownSigner:
        // reject issuer
    }
}
```

The response carries `subject`, `issuer`, `jwt_type`, optional `exp`/`iat`, and
`matched_signer_key_id` when the winning candidate was a catalog key.

## Sign rich caller-assembled claims

Use `SignNatsJwt` when you need rich NATS claims that Basil's convenience minters do not model. The
caller builds the claim document, Basil validates `sub`, `nats.type`, issuer role, timestamps, and
`jti`, then signs with the fixed `ed25519-nkey` profile. The issuer seed remains in the backend.

The gRPC field is `claims_json`: raw UTF-8 JSON object bytes, not `google.protobuf.Struct`. That
keeps integer-valued NATS claims such as byte limits, revocation timestamps, and nanosecond
durations out of protobuf's `double` number path. The Rust client accepts any `serde::Serialize`
value and also exposes `sign_nats_jwt_json` for pre-encoded bytes. The Go client accepts maps,
structs, `json.RawMessage`, `[]byte`, or JSON strings; use `json.Decoder.UseNumber` when decoding
JSON into maps so large integers do not become `float64` before Basil sees them.

The claim object must contain `sub` and `nats`; top-level `name` is optional, matching upstream NATS
`omitempty` behavior. Basil computes `jti` from the actual standard claims, including optional `aud`
and `nbf`. If you pass `--ttl-secs` and the claim already carries `iat`, Basil derives `exp` from
that `iat`; an explicit `--issued-at-unix` overrides the claim value.

For lower-level libraries, the same pattern is: build the exact NATS signing input outside Basil, call
`Sign` with the `ED25519_NKEY` signing profile on a catalog-held issuer key, then append the returned
raw signature with `basil_nats::assemble`. Prefer `SignNatsJwt` when the standard NATS claim checks
should be enforced by the broker.

CLI:

```sh
basil --socket /run/basil/basil.sock sign-nats-jwt \
  --key-id nats.account \
  --claims-file ./user-claims.json \
  --expect-type user \
  --ttl-secs 3600
```

## Issuer identity: account keys and signing keys

A NATS user JWT is signed by an account, but an account can hold more than one issuing key. NATS
distinguishes the account **identity key** (the account's own `A…` NKey, whose public value *is* the
account id) from account **signing keys** (additional `A…` keys the account authorizes to issue on
its behalf, so you can rotate signing material without changing the account id).

When Basil signs a user JWT with a signing key rather than the identity key, the token's `iss` is the
signing key, which is not the account id. nats-server then needs to know which account owns that
signer, so the user JWT must also carry `nats.issuer_account` naming the account identity. Supply it
with `--issuer-account`, whose value is the owning account's identity public NKey (`A…`):

```sh
basil --socket /run/basil/basil.sock mint-nats-user \
  --key-id nats.account_signing \
  --user-nkey "$USER_PUBLIC_NKEY" \
  --issuer-account "ADVCJ4FZLS..." \
  --name device-42 \
  --ttl-secs 3600 > /run/secrets/device-42.jwt
```

The minted user JWT then stamps `nats.issuer_account` with that account id, and nats-server maps the
signer back to its account.

{% caution(title="Required for signing-key issuers") %}
If you omit `--issuer-account` when `--key-id` is a signing key, nats-server rejects the connection
with an authorization violation: the `iss` is an authorized signer the server cannot map to an
account. Basil cannot tell a signing key from an identity key from the key material alone, so naming
the account is the caller's job. Omit the flag only when `--key-id` *is* the account identity key,
where `iss` already equals the account id.
{% end %}

The Rust and Go clients take the same optional `issuer_account` argument on `mint_nats_user`; leave it
unset for an identity-key issuer.

## Write a user `.creds` file

A NATS user `.creds` file combines two different authorities:

- the user JWT, signed by the account issuer key that stays in Basil; and
- the user's own seed, generated or held by the client that will connect to NATS.

Basil deliberately does not mint the user seed for you. Generate or load the user NKey seed locally,
mint or sign the user JWT through Basil, then assemble the canonical `nsc`-style file:

```sh
basil --socket /run/basil/basil.sock mint-nats-user \
  --key-id nats.account \
  --user-nkey "$USER_PUBLIC_NKEY" \
  --name device-42 \
  --ttl-secs 3600 > /run/secrets/device-42.jwt

basil issue-nats-creds \
  --jwt-file /run/secrets/device-42.jwt \
  --seed-file /run/secrets/device-42.seed \
  --out-file /run/secrets/device-42.creds
```

`issue-nats-creds` is local file plumbing, so it does not need the Basil socket. It trims the JWT and
seed, rejects multiline input, writes atomically, and enforces `0600` by default. Use `--mode 0660`
when a service group needs to read the resulting credentials file.

## NATS curve xkey boxes

NATS auth callouts can use curve xkeys to protect request or response payloads. Basil supports the
upstream `nats-io/nkeys` wire format:

```text
xkv1 || 24-byte nonce || XSalsa20-Poly1305 ciphertext
```

`EncryptNatsCurve` uses the custodied sender xkey and the recipient public `X...` key. `DecryptNatsCurve`
uses the custodied recipient xkey, authenticates the sender public `X...` key, and returns plaintext.
The private xkey is the materialize-to-use exception: it is read via the secret `kv_get_secret` path,
used for one box operation, and zeroized. The public half belongs at `publicPath` so public operations
do not materialize the private.

Rust:

```rust
# async fn run(mut client: basil::Client) -> basil::Result<()> {
let ciphertext = client
    .encrypt_nats_curve("nats.xkey", "XBCRECIPIENT...", b"callout body")
    .await?;
let plaintext = client
    .decrypt_nats_curve("nats.xkey", "XBCSENDER...", &ciphertext)
    .await?;
# Ok(())
# }
```

Go:

```go
ciphertext, err := client.Nats().EncryptNatsCurve(ctx, basil.NatsCurveEncryptRequest{
    KeyID:               "nats.xkey",
    RecipientPublicXKey: "XBCRECIPIENT...",
    Plaintext:           []byte("callout body"),
})
plaintext, err := client.Nats().DecryptNatsCurve(ctx, basil.NatsCurveDecryptRequest{
    KeyID:            "nats.xkey",
    SenderPublicXKey: "XBCSENDER...",
    Ciphertext:       ciphertext,
})
```

## Where to go next

- [The catalog](/configuration/catalog/): `ed25519-nkey`, `nats_type`, and `publicPath`.
- [The policy](/configuration/policy/): the NATS operation grants.
- [Rust client](/clients/rust/) and [Go client](/clients/go/): client method surfaces.
