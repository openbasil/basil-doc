+++
title = "Your first integrated service"
weight = 32
+++

# Your first integrated service

The pages around this one document the full client surfaces. This one answers the smaller, more
useful question: what does *my* code look like when a web service uses Basil? The answer is short.
Your service connects to the broker socket, asks for the operation it needs (here: minting a
short-lived JWT), and holds **no key material** at all: no signing key in the environment, in
config, in the image, or on disk. The broker attests your service's uid through the kernel, the
policy grants exactly one capability, and every mint is audited.

Both snippets below implement the same thing: a `POST /token` handler that returns a five-minute
JWT signed by a catalog key. The signing key lives in the backend and is used in place.

## The catalog key and the policy rule

One issuer key and one rule are the entire configuration surface. The service uid may mint with
this key; it may not read it, rotate it, or touch anything else:

```json
"svc.jwt_issuer": {
  "class": "asymmetric",
  "keyType": "ed25519",
  "backend": "bao",
  "engine": "transit",
  "path": "svc-jwt",
  "writable": true,
  "missing": "generate"
}
```

```json
{
  "id": "checkout-can-mint",
  "subjects": ["svc.checkout"],
  "action": ["op:mint"],
  "target": ["svc.jwt_issuer"]
}
```

With an Ed25519 issuer the minted JWT is `EdDSA`-signed; the JWS algorithm always follows the
issuer key's type (see the [command reference](/cli/command-reference/)). The subject
`svc.checkout` resolves from the uid your service runs under (systemd `User=`), so there is no
credential to configure in the service and nothing to rotate when it redeploys.

## Rust: an axum handler

The service reads the socket path from `BASIL_SOCKET` and mints on demand. Error mapping and
routing are the usual axum shapes; the Basil part is three lines.

```rust
use axum::{http::StatusCode, routing::post, Json, Router};
use basil::Client;

async fn issue_token() -> Result<Json<serde_json::Value>, StatusCode> {
    let socket =
        std::env::var("BASIL_SOCKET").unwrap_or_else(|_| "/run/basil/basil.sock".into());
    let mut basil = Client::connect(&socket)
        .await
        .map_err(|_| StatusCode::BAD_GATEWAY)?;
    let jwt = basil
        .mint_jwt("svc.jwt_issuer", "checkout", Some(300),
            serde_json::json!({"scope": "orders:read"}))
        .await
        .map_err(|_| StatusCode::BAD_GATEWAY)?;
    Ok(Json(serde_json::json!({ "token": jwt.token, "expires_at": jwt.expires_at })))
}

#[tokio::main]
async fn main() {
    let app = Router::new().route("/token", post(issue_token));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:8080").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

The runnable version, with a `run.sh` that provisions the catalog, policy, and broker around it, is
`examples/web-service-axum/` in the Basil repo.

## Go: a net/http handler

The Go client is safe for concurrent use, so dial once in `main` and share the client across
handlers:

```go
func main() {
    client, err := basil.Dial(os.Getenv("BASIL_SOCKET"))
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    http.HandleFunc("POST /token", func(w http.ResponseWriter, r *http.Request) {
        cred, err := client.MintJwt(r.Context(), basil.JwtRequest{
            KeyID:   "svc.jwt_issuer",
            Subject: "checkout",
            TTL:     5 * time.Minute,
            Claims:  map[string]any{"scope": "orders:read"},
        })
        if err != nil {
            http.Error(w, "mint failed", http.StatusBadGateway)
            return
        }
        json.NewEncoder(w).Encode(map[string]any{
            "token": cred.Token, "expires_at": cred.ExpiresAt.Unix(),
        })
    })
    log.Fatal(http.ListenAndServe("127.0.0.1:8080", nil))
}
```

The runnable version is `clients/go/examples/web-service/` in the Basil repo, following the same
`run.sh` pattern as the other Go examples.

{% note(title="Why there is no credential in either snippet") %}
Neither service presents a token, key, or certificate to Basil. The kernel reports the caller's
uid/gid over the Unix socket (`SO_PEERCRED`), the policy resolves it to `svc.checkout`, and the
grant above bounds what it may do. Run the service under its own uid; that uid is its identity.
{% end %}

Swap `mint_jwt`/`MintJwt` for `sign`/`Sign` and an `op:sign` grant, and the same shape covers
release signing, webhook signing, or any other operation surface: the service asks for the result,
never the key.

{% note(title="If anything failed") %}
Run `basil doctor --keys -c <config>` to validate the broker's catalog, policy, and backend key
probe, and see [Troubleshooting](/troubleshooting/) for the error reference. A `PermissionDenied`
in the handler usually means the service uid does not resolve to the granted subject; check with
`basil explain --subject svc.checkout --op mint --key svc.jwt_issuer`.
{% end %}

## Where to go next

- [Rust client](/clients/rust/) and [Go client](/clients/go/): the full method surfaces behind
  these snippets.
- [Integration patterns](/clients/integration-patterns/): native client, sidecar, or pre-fetch.
- [The policy](/configuration/policy/): subjects, roles, and scoping one uid to one capability.
