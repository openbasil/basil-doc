+++
title = "Integration patterns"
weight = 50
+++

# Integration patterns

The happy path is that your services never touch a secret. Declare what each one needs in the
[catalog](/configuration/catalog/), set `missing: generate` so Basil mints anything absent at startup,
and let the broker do the signing and encryption in place. When a workload genuinely needs material in
hand, almost always an **mTLS identity**, use the lowest-friction option below. They're listed
best-first.

{% best(title="Design the secret out first") %}
Before wiring up a fetch, ask whether the service needs the *key* or just the *operation*. If it
signs or decrypts, route that through Basil's `sign`/`decrypt` and the key stays in the backend.
Nothing to materialize, nothing to leak. The options below are for when something outside Basil (a
TLS stack, a third-party SDK) insists on holding the bytes itself.
{% end %}

## Native client (modify source)

If you can change the service, talk to Basil directly over its socket: the tightest integration, no
extra process, rotation handled in-band.

- **Rust:** use the upstream [`spiffe`](/clients/rust/) crate, whose auto-rotating `X509Source`
  connects to the socket and keeps the SVID fresh on Basil's `svid-ttl-secs` cadence, or the in-tree
  generated Workload API client.
- **Any language:** generate a gRPC client from the
  [SPIFFE Workload API](/clients/other-languages/) protobufs (or Basil's broker protos) and call the
  broker over the socket.

{% note(title="The one required header") %}
Workload API RPCs must carry the `workload.spiffe.io: true` metadata header. The high-level `spiffe`
client sets it for you; a raw generated client must attach it itself, or every call fails closed with
`InvalidArgument`.
{% end %}

## spiffe-helper sidecar (no source changes)

When you can't (or don't want to) modify the service,
[spiffe-helper](https://github.com/spiffe/spiffe-helper) is a drop-in materializer for its mTLS
identity. Run it in daemon mode, as the service's uid, against the broker socket
(`/run/basil/basil.sock`):

- it fetches the X.509-SVID, its private key, and the trust bundle, and writes them as PEM files;
- unlike a one-shot fetch, it **re-fetches before expiry** and signals or relaunches the service on
  rotation.

A standard, maintained tool beats a bespoke cert shim here: it handles the hard part, reload and
rotation, and you don't need to write or own it.

{% tip(title="Rust services don't need the sidecar") %}
A Rust service gets the same auto-rotating SVID natively via the [Rust client](/clients/rust/). Save
the sidecar for the services you can't recompile.
{% end %}

{% caution(title="Run it as the right uid") %}
spiffe-helper must run under the *service's* uid: that uid is what Basil attests and what policy
grants the SVID to. Run it as the wrong user and it gets the wrong identity, or none.
{% end %}

## NATS auth callouts

For NATS auth callouts, keep the issuer seed and xkey in Basil. Use
[NATS integration](/clients/nats/) to mint or validate JWTs through `NatsService`, and to encrypt or
decrypt `xkv1` curve boxes without handing the xkey seed to the callout process.

## NATS bridge courier

When a NATS-connected workload needs to call a Basil operation over a bridged transport, use the
[NATS bridge](/clients/nats-bridge/) with sealed invocations. The bridge carries opaque tagged COSE
request/reply bytes; Basil authorizes the sealed actor and records the bridge only as the
Unix-socket presenter.

## CLI pre-fetch (last resort)

If neither a native client nor the sidecar fits, pre-fetch with the `basil` CLI under the service's
uid before the service starts, e.g. a systemd `ExecStartPre=`, and hand the result over via tmpfs
or the environment:

```ini
# systemd unit (sketch): fetch as the service user into a tmpfs path, then start
[Service]
User=svc-web
RuntimeDirectory=svc-web        # /run/svc-web: tmpfs, 0700, removed on stop
ExecStartPre=/usr/bin/basil --socket /run/basil/basil.sock \
  get --key-id app.db_password --out-file /run/svc-web/db-password
ExecStart=/usr/bin/the-service
```

The CLI can't impersonate: it authorizes by *its own* kernel uid/gid, so running it under
`User=svc-web` is exactly what scopes the fetch to that service's grants.

{% caution(title="This materializes a standing secret") %}
A pre-fetched value sits in `/run` (or an env var) for the life of the process: no rotation, no
per-use authorization, no audit of each read. Keep it on tmpfs (never disk), scope the
`RuntimeDirectory` to the one uid, and prefer a short-lived lease or a native client / sidecar
wherever you can. It's the fallback, not the goal.
{% end %}

## Where to go next

- [Rust client](/clients/rust/) and [Go client](/clients/go/): concrete native integrations.
- [NATS integration](/clients/nats/): NATS JWTs and auth-callout encryption.
- [NATS bridge](/clients/nats-bridge/): sealed invocation request/reply over NATS.
- [The catalog](/configuration/catalog/): declare `missing: generate` so the secret never leaves the backend.
