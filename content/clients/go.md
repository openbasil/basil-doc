+++
title = "Go client"
weight = 30
+++

# Go client

The Go client is the **`github.com/openbasil/basil-go`** module. The client package lives at the
`basil` subpath, so the import path is `github.com/openbasil/basil-go/basil`. It talks to the broker
over the local Unix socket, maps every RPC to context-aware Go methods, and keeps the core package
lean: SPIFFE helpers and streaming encryption live in separate subpackages.

The broker still authenticates the caller with `SO_PEERCRED`. The Go client does not present a token
or certificate; run the process under the uid/gid evidence you want Basil to resolve to a policy
subject.

## Install and connect

```sh
go get github.com/openbasil/basil-go/basil
```

```go
import "github.com/openbasil/basil-go/basil"

client, err := basil.Dial("/run/basil/basil.sock")
if err != nil {
    return err
}
defer client.Close()
```

`Dial` is lazy: an unreachable socket fails on the first RPC, not at construction. The transport is
plain gRPC over a Unix socket with a pinned `localhost` HTTP/2 authority; without that authority, a raw
filesystem path can leak into `:authority` and be rejected by the HTTP/2 stack.

Options:

| Option | Use |
| --- | --- |
| `basil.WithTimeout(d)` | Per-RPC timeout when the caller's context has no deadline. Default is `30s`; pass `0` to require caller deadlines. |
| `basil.WithDialOptions(...)` | Extra gRPC dial options such as interceptors or message-size limits. The Unix dialer and local transport credentials are fixed. |

## Errors

Broker failures surface as `*basil.StatusError`:

```go
sig, err := client.Sign(ctx, "web.tls.signing_key", msg)
if se, ok := basil.AsStatusError(err); ok {
    log.Printf("code=%s reason=%s op=%s", se.Code, se.Reason, se.Op)
}
```

`Code` is the canonical gRPC status code. `Reason` and `Op` come from Basil's `BrokerErrorInfo`
detail, for example `UNAUTHORIZED` / `sign` or `BACKEND_UNAVAILABLE` / `encrypt`. The type works with
`errors.As` and `status.Code(err)`. Use `basil.FromError(err)` when you need to normalize an error from
the raw go-spiffe client returned by `spiffe.Client.Workload()`.

`Verify` and `ValidateNatsJwt` have authoritative negative results: `Verify` returns `(false, nil)`
for a bad signature, and NATS validation returns `Valid=false` with a typed reason. A non-nil error
means the broker could not perform the operation.

## Signing and key lifecycle

```go
msg := []byte("release v1.2.3")

sig, err := client.Sign(ctx, "web.tls.signing_key", msg)
ok, err := client.Verify(ctx, "web.tls.signing_key", msg, sig)
pub, err := client.GetPublicKey(ctx, "web.tls.signing_key", nil)

sig, err = client.SignWithAlgorithm(ctx, "nats.account", msg,
    basil.SigningAlgorithmEd25519NKey)
```

The broker signs the message bytes you pass, not a caller-prehashed digest. The algorithm is normally
derived from the catalog key; use `SignWithAlgorithm` / `VerifyWithAlgorithm` only when a key supports
an explicit profile such as NATS NKey signing.

Create or import keys through the catalog name. Only the public half comes back:

```go
h, err := client.NewKey(ctx, "app.pqc.sign", basil.KeyTypeMLDSA65)

h, err = client.Import(ctx, "nats.operator", basil.KeyTypeEd25519,
    basil.Ed25519SeedMaterial(seed))

keys, err := client.ImportSet(ctx, []basil.ImportEntry{
    {KeyID: "nats.operator", KeyType: basil.KeyTypeEd25519,
        Material: basil.Ed25519SeedMaterial(operatorSeed)},
    {KeyID: "web.tls", KeyType: basil.KeyTypeRSA2048,
        Material: basil.PKCS8DERMaterial(rsaDER)},
})
```

`KeyMaterial` is deliberately sealed and write-only: callers can construct
`Ed25519SeedMaterial` or `PKCS8DERMaterial`, but no RPC returns imported private material. Custody and
storage stay catalog-controlled.

## AEAD and KEM envelopes

```go
ct, err := client.Encrypt(ctx, "app.aead", basil.AeadAlgorithmAES256GCM, plaintext, aad)
pt, err := client.Decrypt(ctx, "app.aead", ct, aad)

wrapped, err := client.WrapEnvelope(ctx, "app.kem",
    basil.KemAlgorithmMLKEM768, basil.EnvelopeAlgorithmAES256GCM, cek, aad)
cek, err = client.UnwrapEnvelope(ctx, "app.kem", wrapped, aad)
```

For AEAD, Basil owns the nonce. Treat `*basil.Ciphertext` as opaque and round-trip its suite, version,
nonce, and ciphertext unchanged. KEM envelopes use `*basil.KemEnvelope` for X25519 or ML-KEM wrapping;
the private decapsulation key stays custodied by the broker.

For files or large payloads, use the separate [`stream` subpackage](/clients/stream/). It encrypts an
`io.Reader` into an `io.Writer` in bounded chunks, wire-identical to Rust `basil::stream`.

## Secrets and catalog

```go
sec, err := client.GetSecret(ctx, "app.db_password", nil) // nil = latest
ver, err := client.SetSecret(ctx, "app.db_password", []byte("new value"))
ver, err = client.RotateSecret(ctx, "app.db_password")
entries, err := client.ListCatalog(ctx, nil) // nil = no prefix filter
```

`ListCatalog` drains the server stream into `[]basil.CatalogEntry`. It returns inventory metadata, not
secret values.

## Minting, NATS, and certificates

Generic JWT minting stays on `MintingService`:

```go
cred, err := client.MintJwt(ctx, basil.JwtRequest{
    KeyID:   "app.jwt_issuer",
    Subject: "svc-a",
    TTL:     15 * time.Minute,
    Claims:  map[string]any{"scope": "orders:read"},
})
```

`JwtRequest.Claims` is serialized as raw UTF-8 JSON object bytes in the broker's
`extra_claims_json` field. It may be a map, struct, `json.RawMessage`, `[]byte`, or JSON string. Use
`json.RawMessage` or `[]byte` when you need byte-exact claim JSON, and use
`json.Decoder.UseNumber` before placing decoded JSON in a map with large integer claims.

NATS-specific calls live on the `NatsService` sub-client:

```go
user, err := client.Nats().MintNatsUser(ctx, basil.NatsUserRequest{
    KeyID:           "nats.account",
    SubjectUserNKey: userNKey,
    Name:            "orders-api",
    TTL:             time.Hour,
})

signed, err := client.Nats().SignNatsJwt(ctx, basil.NatsJwtRequest{
    KeyID:        "nats.account",
    Claims:       claims,
    ExpectedType: basil.NatsJwtTypeUser,
    TTL:          time.Hour,
})

validation, err := client.Nats().ValidateNatsJwt(ctx, basil.ValidateNatsJwtRequest{
    JWT: token,
    AllowedSigners: []basil.AllowedSigner{
        basil.AllowedSignerKeyID("nats.account"),
        basil.AllowedSignerNatsPublicKey("ADVCJ4FZLS..."),
    },
    ExpectedType: basil.NatsJwtTypeUser,
})
```

`NatsJwtRequest.Claims` uses the same raw JSON pattern for the full NATS claim object, sent as
`claims_json`; it may be a map, struct, `json.RawMessage`, `[]byte`, or JSON string. The
[NATS JWT reference](/reference/nats-jwt-reference/) documents every account and user claim
`SignNatsJwt` accepts and the semantic defaults Basil applies.

`ValidateNatsJwt` returns `Valid`, `Reason`, `Subject`, `Issuer`, `JWTType`,
`MatchedSignerKeyID`, `ExpiresAt`, and `IssuedAt`. Reasons include malformed, bad signature, unknown
signer, expired, not-yet-valid, and wrong type.

NATS curve xkey boxes also live on `NatsService`:

```go
box, err := client.Nats().EncryptNatsCurve(ctx, basil.NatsCurveEncryptRequest{
    KeyID:               "nats.xkey",
    RecipientPublicXKey: "XBCRECIPIENT...",
    Plaintext:           payload,
})
payload, err = client.Nats().DecryptNatsCurve(ctx, basil.NatsCurveDecryptRequest{
    KeyID:            "nats.xkey",
    SenderPublicXKey: "XBCSENDER...",
    Ciphertext:       box,
})
```

See [NATS integration](/clients/nats/) for the service split, catalog shape, policy grants, and the
`xkv1` wire format.

Certificate issuance returns the sole broker result containing private key material: the freshly
minted leaf key that a TLS server needs.

```go
cert, err := client.IssueCertificate(ctx, basil.CertificateRequest{
    IssuerKeyID: "web.tls.cert_issuer",
    CommonName:  "svc.example.org",
    DNSSANs:     []string{"svc.example.org"},
    TTL:         24 * time.Hour,
})
// cert.CertChainDER, cert.PrivateKeyDER, cert.CAChainDER
```

## Status and admin

```go
st, err := client.Status(ctx)
health, err := client.Health(ctx)
ready, err := client.Readiness(ctx)
```

`Health` is cheap liveness. `Readiness` probes backend reachability and key presence, returning only
counts and coarse reasons. `Status` names the configured backend kind, so the broker answers it only
for peers that resolve to a policy subject (no further grant needed); `Health` and `Readiness` stay
ungated.

Admin mutations are permission-gated and not implied by data-plane grants:

```go
reload, err := client.Reload(ctx, false) // check=true dry-runs without swapping
explain, err := client.Explain(ctx, "svc.app", "sign", "app.signing")
revoked, err := client.Revoke(ctx, "example.org", jti, expiresAtUnix)
```

`Reload` re-reads the broker's configured on-disk catalog/policy paths; the request carries no config.
A validation or routing rejection is returned as `ReloadResult.Rejection`, not by swapping in a bad
generation.

`Watch` is a long-lived server stream for key rotation, bundle changes, and revocations. Like the
other admin ops it needs an explicit grant: `op:watch` over the reserved target `broker.watch`. It is
exempt from the default per-RPC timeout; the caller owns and closes it. Delivery is at-most-once over
a bounded buffer: a stream that falls too far behind is closed with the `DataLoss` code instead of
silently skipping events (a missed revocation is never invisible); reconnect and re-fetch the state
you mirror.

```go
watch, err := client.Watch(ctx, basil.EventKindKeyRotated)
if err != nil {
    return err
}
defer watch.Close()

for ev, err := range watch.Events() {
    if err != nil {
        return err
    }
    if ev.Kind == basil.EventKindKeyRotated {
        log.Printf("%s -> v%d", ev.KeyRotated.KeyID, ev.KeyRotated.NewVersion)
    }
}
```

You can also use `Recv()` directly; clean close returns `io.EOF`.

## SPIFFE subpackage

The `github.com/openbasil/basil-go/spiffe` subpackage wraps go-spiffe's Workload API client
over the Basil socket. It attaches the mandatory `workload.spiffe.io: true` header, parses SVIDs and
bundles into standard go-spiffe types, and normalizes Basil gRPC errors with `basil.FromError`.

```go
import "github.com/openbasil/basil-go/spiffe"

sc, err := spiffe.Dial(ctx, "/run/basil/basil.sock")
if err != nil {
    return err
}
defer sc.Close()

x509svid, err := sc.FetchX509SVID(ctx)
x509svids, err := sc.FetchX509SVIDs(ctx)
x509Bundles, err := sc.FetchX509Bundles(ctx)
x509Context, err := sc.FetchX509Context(ctx)

jwt, err := sc.FetchJWTSVID(ctx, "orders")
jwts, err := sc.FetchJWTSVIDs(ctx, "orders")
jwtBundles, err := sc.FetchJWTBundles(ctx)
validated, err := sc.ValidateJWTSVID(ctx, token, "orders")
```

The X.509-SVID includes the workload's own private key, as the SPIFFE standard requires. For
long-running processes, use rotation-aware sources:

```go
xsrc, err := spiffe.NewX509Source(ctx, "/run/basil/basil.sock")
defer xsrc.Close()

jsrc, err := spiffe.NewJWTSource(ctx, "/run/basil/basil.sock")
defer jsrc.Close()
```

`WatchX509Context` and `WatchJWTBundles` expose the raw rotation streams when you need to react to
updates yourself. `Workload()` returns the underlying go-spiffe client for advanced cases.

## Streaming subpackage

The `github.com/openbasil/basil-go/stream` subpackage encrypts files and large payloads in
bounded chunks. It is wire-identical to Rust `basil::stream`, and it is isolated so callers that do not
need post-quantum streaming do not link those dependencies.

```go
import "github.com/openbasil/basil-go/stream"

cek, err := stream.EncryptAEAD(dst, src, stream.SuiteAES256GCM,
    stream.GenerateCEK(), stream.DefaultChunkSize)
err = stream.DecryptAEAD(out, encrypted, cek)

err = stream.EncryptMLKEM(dst, src, stream.SuiteMLKEM768, recipientPubKey,
    stream.DefaultChunkSize)
rec := stream.NewBrokerCEKRecovery(client, "app.kem_key", stream.SuiteMLKEM768)
err = stream.DecryptMLKEM(ctx, out, encrypted, rec)
```

See [Streaming encryption](/clients/stream/) for the container, CEK recovery model, and interop tests.

## Where to go next

- [NATS integration](/clients/nats/): NATS service split, validation, and xkey boxes.
- [Streaming encryption](/clients/stream/): file and large-payload encryption.
- [Integration patterns](/clients/integration-patterns/): native client, sidecar, and pre-fetch.
