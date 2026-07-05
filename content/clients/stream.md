+++
title = "Streaming encryption"
weight = 25
+++

# Streaming encryption

Streaming encryption is the client-side format for files and large payloads. It encrypts an
`AsyncRead` / `io.Reader` into an `AsyncWrite` / `io.Writer` without buffering the whole source, while
keeping Basil's nonce rule intact: callers choose the suite and key source, but never provide nonces.

Rust exposes it as `basil::stream`; Go exposes a wire-identical `stream` subpackage. The byte format is
specified in the normative Basil repo spec, `docs/specs/streaming-encryption-format.md`.

## Suites

| Suite | Chunk AEAD | Key establishment |
| --- | --- | --- |
| `AeadSuite::Aes256Gcm` / `stream.SuiteAES256GCM` | AES-256-GCM | Symmetric 32-byte CEK, generated or caller-provided. |
| `AeadSuite::ChaCha20Poly1305` / `stream.SuiteChaCha20Poly1305` | ChaCha20-Poly1305 | Symmetric 32-byte CEK, generated or caller-provided. |
| `MlKemSuite::MlKem512` / `stream.SuiteMLKEM512` | AES-256-GCM | Fresh CEK wrapped once to an ML-KEM-512 public encapsulation key. |
| `MlKemSuite::MlKem768` / `stream.SuiteMLKEM768` | AES-256-GCM | Fresh CEK wrapped once to an ML-KEM-768 public encapsulation key. |
| `MlKemSuite::MlKem1024` / `stream.SuiteMLKEM1024` | AES-256-GCM | Fresh CEK wrapped once to an ML-KEM-1024 public encapsulation key. |

The ML-KEM suites need only the recipient's public encapsulation key to encrypt. Decryption recovers
the once-wrapped CEK through a `CekRecovery` / `CEKRecovery` seam: production uses the broker's
`UnwrapEnvelope` RPC (`BrokerCekRecovery` / `NewBrokerCEKRecovery`), while tests and tools can use a
raw seed (`LocalSeedCekRecovery` / `NewLocalSeedCEKRecovery`).

## Container format

Every stream starts with a fixed 61-byte header:

| Field | Meaning |
| --- | --- |
| `magic` | ASCII `BSLSTR`. |
| `version` | `1`. |
| `suite_id` | The selected suite. |
| `flags` | Reserved; must be zero. |
| `chunk_size` | Plaintext chunk size, `1..=1048576`. |
| `stream_id` | Random 16-byte stream id. |
| `stream_salt` | Random 32-byte HKDF salt. |

ML-KEM streams then carry one KEM header containing the ML-KEM encapsulated key, CEK-wrap nonce, and
wrapped CEK. The CEK wrap is byte-compatible with `basil-core`'s `ml_kem_envelope`, so the broker can
recover it through `UnwrapEnvelope`; clients send `key_version = 0` for software custody and the broker
uses the latest custody record.

The body is a sequence of length-prefixed AEAD records. Each chunk uses a counter nonce under a
per-stream message key derived by HKDF-SHA256 from the CEK, `stream_salt`, suite id, and `stream_id`.
Per-chunk AAD binds the version, suite, `stream_id`, chunk index, final marker, plaintext length, and
declared chunk size. Decryption fails closed on malformed headers, bad chunk order, truncation,
downgrade, or AEAD authentication failure.

## Rust

```rust
use basil::{
    AeadSuite, CekSource, DEFAULT_CHUNK_SIZE, MlKemSuite,
    decrypt_aead, decrypt_ml_kem, encrypt_aead, encrypt_ml_kem,
};

# async fn run<R, W>(plain: R, encrypted: W, recipient_pub: &[u8]) -> basil::stream::StreamResult<()>
# where
#     R: tokio::io::AsyncRead + Unpin,
#     W: tokio::io::AsyncWrite + Unpin,
# {
let cek = encrypt_aead(
    plain,
    encrypted,
    AeadSuite::Aes256Gcm,
    CekSource::Generate,
    DEFAULT_CHUNK_SIZE,
)
.await?;

// Store `cek` wherever your application stores file-encryption metadata.

// ML-KEM encryption needs only the public encapsulation key.
// let recovery = basil::BrokerCekRecovery::new(client, "app.kem_key", MlKemSuite::MlKem768);
// encrypt_ml_kem(src, dst, MlKemSuite::MlKem768, recipient_pub, DEFAULT_CHUNK_SIZE).await?;
# let _ = (cek, recipient_pub, MlKemSuite::MlKem768);
# Ok(())
# }
```

The Rust reference CLI is useful for interop tests:

```sh
cargo build -p basil --example stream_cli
target/debug/examples/stream_cli encrypt --suite aes256gcm --key <hex32> < plain > encrypted.bsl
target/debug/examples/stream_cli decrypt --key <hex32> < encrypted.bsl > plain.out
```

## Go

```go
import "github.com/openbasil/basil-go/stream"

cek, err := stream.EncryptAEAD(dst, src, stream.SuiteAES256GCM,
    stream.GenerateCEK(), stream.DefaultChunkSize)
if err != nil {
    return err
}
if err := stream.DecryptAEAD(out, encrypted, cek); err != nil {
    return err
}

if err := stream.EncryptMLKEM(dst, src, stream.SuiteMLKEM768,
    recipientPublicKey, stream.DefaultChunkSize); err != nil {
    return err
}
rec := stream.NewBrokerCEKRecovery(client, "app.kem_key", stream.SuiteMLKEM768)
if err := stream.DecryptMLKEM(ctx, out, encrypted, rec); err != nil {
    return err
}
```

The Go `stream` package is isolated from the lean root package, so the post-quantum dependencies are
linked only by callers that import it.

## Interop

Rust and Go prove the format both directions for AES-256-GCM, ChaCha20-Poly1305, and ML-KEM-768. The
Go test drives the Rust reference CLI:

```sh
cargo build -p basil --example stream_cli
BASIL_STREAM_RUST_CLI="$PWD/target/debug/examples/stream_cli" \
  go test -tags interop -run Interop ./stream/...
```

The published Rust client keeps only pure-Rust RustCrypto dependencies for this feature
(`aes-gcm`, `chacha20poly1305`, `ml-kem`, `hkdf`, `sha2`, `rand`, `zeroize`). It does not pull
OpenBao, tonic server code, `age`, or `argon2` into client applications.

## Where to go next

- [Rust client](/clients/rust/) and [Go client](/clients/go/): the language-specific surfaces.
- [Crypto operations](/operations/crypto/): broker-side key custody and envelope operations.
- [Feature matrix](/reference/feature-matrix/): implemented vs. roadmap.
