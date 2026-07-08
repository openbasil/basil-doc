+++
title = "The five-minute demo"
weight = 15
+++

# The five-minute demo

`basil demo` is the fastest way to watch Basil's whole security model run. One command, zero
dependencies: no backend server, no config authoring, nothing on your machine but the `basil`
binary. It scaffolds a throwaway broker on the built-in db-keystore backend, starts it, and drives
a scripted tour that ends with copy-paste commands so you can keep going yourself.

```sh
basil demo
```

With Nix you do not even need a checkout or an install:

```sh
nix run github:openbasil/basil -- demo
```

Unpaced, the whole tour runs in about three seconds. Everything it creates lives in one throwaway
workdir (default `$TMPDIR/basil-demo`), so there is nothing to clean up and re-running recreates it.

## The four gates

The demo is a compressed pass through the four gates every real Basil deployment enforces. Each
operation you watch goes through all of them:

1. **Attest.** The broker reads your uid straight from the kernel (`SO_PEERCRED`). You present no
   token and no password, so there is nothing to steal or leak.
2. **Authorize.** A default-deny policy resolves that uid to the subject `current-user` and grants
   it exactly one role, `demo-user` (`list`, `get_public_key`, `sign`, `verify`, `encrypt`,
   `decrypt`, `mint`), over the demo keys. Everything unlisted is denied.
3. **Operate in place.** Signing and encryption happen inside the encrypted keystore. Only
   signatures, ciphertext, and minted tokens cross the socket; private key bytes never do.
4. **Audit.** Every decision, allow *and* deny, lands as one structured JSON event in the workdir's
   `audit.jsonl`.

Concretely, the script writes a catalog with two keys (`demo.signing_key`, Ed25519, and
`demo.aead_key`, `AES-256-GCM`), seals the keystore's data-encryption key into a bundle, starts
`basil agent` on a temp socket, then drives: `status` → `list` → `sign 'release v1.0.0'` →
`verify` → a **denied** read → `explain` → `encrypt` → `mint-jwt` → the audit tail.

## The step that fails on purpose

The heart of the demo is a denial. After signing with `demo.signing_key`, the script tries to read
the private key out:

```text
$ basil --socket $DIR/basil.sock get --key-id demo.signing_key
Error: agent status [PermissionDenied/UNAUTHORIZED]: not authorized
```

That is not a bug in the tour; it is the model. The policy grants *use* of the key (`sign`,
`verify`, `mint`), never *possession* (`get`). The same uid that just produced a valid signature
cannot extract the material it signed with.

Then the demo asks the policy engine why, with `basil explain`, offline, against the same files
enforcement reads:

```text
DENY   subject current-user  get  demo.signing_key  (not_permitted)
  no policy grant matches this (subject, op, key): default-deny

ALLOW  subject current-user  sign  demo.signing_key  (via subject:current-user)
  matched subject `current-user` (rule `current-user-can-use-demo-keys`): action `role:demo-user` over target `demo.*`
```

{% note(title="explain is the real matcher") %}
`basil explain` runs the exact matcher enforcement uses, on the same catalog and policy files, with
no socket, no backend, and no secrets. What it predicts is what the broker does. See
[Policy explain](/operations/policy-explain/).
{% end %}

Both decisions, the allow and the deny, appear in the audit tail the demo prints last: one JSON
event per decision, carrying the kernel-attested presenter, the resolved subject, the op, the
target key, and the reason. See [Audit logs](/operations/audit-logs/) for the event schema.

## Try it yourself

The broker keeps running after the tour, and the demo ends with commands to drive it directly:
sign your own message, and ask `explain` about an op the policy never granted (like `rotate`).
Edit the workdir's `policy.json` to grant yourself more; the broker default-denies anything not
listed, so every new capability is a line you added on purpose.

## Flags

| Flag | Meaning |
| --- | --- |
| `--dir <DIR>` | Workdir for the keystore DB, sealed bundle, socket, and audit log. Kept short by default: Unix socket paths are limited to roughly 100 bytes. |
| `--paced` | Human pacing: types commands out and pauses between steps. Use it when watching with someone or recording; the default is full speed. |
| `--force` | Wipe an existing `--dir` even if a previous demo run did not create it. Without it, only directories holding the demo marker file are reused. |

{% note(title="If anything failed") %}
Run `basil doctor --keys -c <workdir>/basil-agent.toml` for an authenticated preflight of the demo
config and keys, and see [Troubleshooting](/troubleshooting/) for the error reference.
{% end %}

## Where to go next

- [Quickstart](/getting-started/quickstart/): the same loop against a real OpenBao or Vault backend.
- [First run: basil init](/getting-started/first-run/): scaffold a least-privilege starter set of
  your own instead of a throwaway.
- [The policy](/configuration/policy/): subjects, roles, and the default-deny matcher you just watched.
- [Audit logs](/operations/audit-logs/): the event schema behind `audit.jsonl`.
