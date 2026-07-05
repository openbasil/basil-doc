+++
title = "Importing (BYOK) keys & sets"
weight = 20
+++

# Importing (BYOK) keys & sets

When you must bring your own key, `import` provisions it from caller-supplied material. It's
**write-only**: the reply carries the public half, never the private bytes. Raw `--seed-hex` is an
Ed25519-only shortcut; RSA-2048 and ECDSA P-256/P-384/P-521 imports use PKCS#8 DER private keys.

```sh
# single key - material from a PKCS#8 DER file (or --seed-hex for a raw Ed25519 seed)
basil --socket /run/basil.sock import --key-id byok.rsa --key-type rsa-2048 --pkcs8-file /run/secrets/rsa.pkcs8.der
basil --socket /run/basil.sock import --key-id byok.ecdsa --key-type ecdsa-p256 --pkcs8-file /run/secrets/p256.pkcs8.der
basil --socket /run/basil.sock import --key-id byok.ecdsa384 --key-type ecdsa-p384 --pkcs8-file /run/secrets/p384.pkcs8.der
basil --socket /run/basil.sock import --key-id byok.imported --key-type ed25519 --seed-hex "$ED25519_SEED_HEX"

# batch (all-or-nothing) from a JSON manifest
basil --socket /run/basil.sock import-set --file /run/secrets/byok-manifest.json
```

Import requires the `import` op (the `operator` role; see [The policy](/configuration/policy/)).
Material is bounded by `max-payload-size` ([Limits](/configuration/limits/)).

{% caution(title="import-set is all-or-nothing") %}
A batch import authorizes and applies as a unit: if any one entry is unauthorized or malformed, the
whole set is rejected and no key is created. You never end up with a
half-applied trust change. Validate the manifest first.
{% end %}

{% note() %}
`import` is for transit keys. A value-store (`kv2`) crypto key or a sealing key is provisioned
out of band, not imported through the broker. Basil refuses it explicitly rather than letting a
transit import quietly fail on a KV path.
{% end %}

## Where to go next

- [Rotating keys](/operations/rotating-keys/): rotation and the grace window.
- [The policy](/configuration/policy/): the `operator` role that grants `import`.
