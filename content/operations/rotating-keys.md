+++
title = "Rotating keys"
weight = 10
+++

# Rotating keys

Rotation gives a key fresh material while keeping recent versions usable, so in-flight ciphertexts
and signatures don't break the moment you rotate.

## Crypto (transit) keys

```sh
basil --socket /run/basil.sock rotate --key-id web.tls.signing_key
# -> version: 6
```

New `sign`/`encrypt` uses the newest version immediately. Older versions stay usable for
`verify`/`decrypt` within the **grace window** (`grace-versions`, default 1): versions below
`latest − grace` stop being honored. The retention sweep (`retain-versions` +
`retention-sweep-secs`) then prunes archived material below the retention floor, irreversibly, so
expired versions don't linger. These knobs live in [Limits & resource controls](/configuration/limits/).

{% best(title="Routine vs. compromise") %}
Routine rotation: keep `grace-versions` ≥ 1 so consumers re-fetch without a flag day.
Compromise: rotate, then run with `grace-versions = 0` so only the newest version
verifies/decrypts. The exposed version is dead immediately.
{% end %}

## Value keys

A `value` key with a `generate` recipe regenerates a fresh value as a new KV version on `rotate`.
Without a recipe there's nothing to generate. Basil returns
`value key … has no generate recipe; rotate via set instead`, so use `set` with your own material.

{% caution(title="What does not rotate through the broker") %}
Materialize-to-use keys (sealing X25519/ML-KEM, value-store Ed25519) and any `engine=kv2` crypto key
are re-provisioned out of band, never broker-rotated. `rotate` on them is refused on purpose.
Their private material is owned outside Basil; rotating it is a provisioning action, followed by
updating the key's `path` (and `publicPath`) material. See
[Backends & custody](/introduction/backends-and-custody/).
{% end %}

## Where to go next

- [Importing (BYOK) keys & sets](/operations/importing-byok/): bring your own material.
- [Limits & resource controls](/configuration/limits/): the grace window and retention sweep.
- [Incident runbook](/troubleshooting/incident-runbook/): key-compromise response.
