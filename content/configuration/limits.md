+++
title = "Limits & resource controls"
weight = 80
+++

# Limits & resource controls

A few settings bound request sizes and key-version lifetime so a runaway caller or an ever-growing key
history can't surprise you.

## Request-size caps

`max-encrypt-size` and `max-payload-size` (each default 1 MiB) bound request sizes:

| Setting | Bounds |
| --- | --- |
| `max-encrypt-size` | `encrypt` plaintext / `decrypt` ciphertext. |
| `max-payload-size` | `set` value / `import` material. |

An over-cap request returns `PAYLOAD_TOO_LARGE` (gRPC `ResourceExhausted`). Raise the limit or chunk
the data. See the [error reference](/troubleshooting/error-reference/).

```toml
max-encrypt-size = 1048576   # 1 MiB
max-payload-size = 1048576   # 1 MiB
```

## Key-version lifetime

`grace-versions` and the retention sweep bound how long old key versions stick around:

| Setting | Bounds |
| --- | --- |
| `grace-versions` | How many recent versions still `verify`/`decrypt` after a rotation. Default 1; `0` = newest only. |
| `retain-versions` | Retention floor; the sweep prunes archived versions below it. Omit to retain all. |
| `retention-sweep-secs` | Sweep interval (seconds). Default 3600; `0` disables. |

These are covered in depth under [Rotating keys](/operations/rotating-keys/).

## Roadmap

Per-uid/key/op rate limits, key-usage quotas, and emergency freeze by key/uid/operation are
<span class="pill gap">roadmap</span>. See the [feature matrix](/reference/feature-matrix/).

## Where to go next

- [Rotating keys](/operations/rotating-keys/): grace windows and retention in depth.
- [Error reference](/troubleshooting/error-reference/): what an over-cap request returns and how to recover.
- [Feature matrix](/reference/feature-matrix/): what's shipped versus roadmap.
