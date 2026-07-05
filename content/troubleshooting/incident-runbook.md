+++
title = "Incident runbook"
weight = 20
+++

# Incident runbook

When something's wrong, work the scenario top to bottom: detect → contain → eradicate → recover →
review. Basil's design buys you time here: keys never left the backend, credentials are
short-lived, and every decision is logged. Most incidents are therefore about cutting off *new*
authority fast.

## Key compromise (a private key may be exposed)

- **Contain:** for a transit key, [`rotate`](/operations/rotating-keys/) it, then restart with
  `grace-versions = 0` so the exposed version no longer verifies/decrypts. For a materialize-to-use
  key, re-provision the private out of band and update its `path`/`publicPath`.
- **Eradicate:** if the key was a JWT-SVID *issuer*, rotating it stops new valid SVIDs immediately;
  outstanding ones expire on their short TTL. Add specific live `jti`s to the
  [deny-list](/operations/revocation/) if you can't wait out expiry.
- **Recover:** confirm consumers re-fetched the new public/version (watch for `DECRYPT_FAILED`/verify
  failures dropping to zero).
- **Review:** audit-log sweep for every `allow` on the key during the exposure window.

{% tip() %}
Because the private key was used *in place* and never handed out, "compromise" usually means a
signature/decrypt was performed on an attacker's behalf, not that the key itself leaked. Rotating the
key and reading the [audit log](/operations/audit-logs/) tells you the blast radius precisely.
{% end %}

## Lost or last-remaining unlock secret

- **Primary slot lost (YubiKey unavailable):** unlock with the BIP39 break-glass phrase
  (`bip39-phrase-file`), then `basil bundle create` a fresh bundle with a new primary slot and migrate the
  credential.
- **Automated passphrase source failed:** run the fetcher manually, then
  `basil bundle verify <bundle> --open passphrase:file=<file>` before restarting.
  If the upstream token expired, rotate it there; Basil cannot distinguish a missing passphrase from a
  deliberately sealed bundle.
- **All slots lost:** the credential in the bundle is unrecoverable by design. Recovery = issue a new
  backend credential (new AppRole `secret_id`, or a new `SpiffeSigner` key) and `basil bundle create` from
  scratch. No secret material is exposed in the process.

{% danger() %}
Treat the BIP39 phrase as the keys to the kingdom: stored offline, access-logged, never on the same
host as the bundle. If it's the only slot left and it's gone, you re-bootstrap. There is no backdoor.
{% end %}

See [Unlock & the sealed bundle](/configuration/unlock-and-bundle/) for slot details.

## Backend (Vault / OpenBao) unreachable

- **Symptom:** ops return `BACKEND_UNAVAILABLE`; keys on that backend can't sign/encrypt/issue. The
  broker itself stays up and keeps serving any keys on healthy backends.
- **Contain / recover:** restore backend reachability; ops resume with no broker restart. If startup
  reconcile is what's failing, a missing-but-required key is the likely cause: fix the backend, or
  (recovery only) boot with `no-reconcile = true` / `capability-policy = "degraded"` to serve the
  healthy subset while you investigate.
- **Review:** once back, re-run `basil config check --require` to confirm every required key is
  present before clearing the incident.

See [Capability policy & reconcile](/configuration/capability-and-reconcile/).

## Sealed-bundle rollback / epoch-sidecar mismatch

- **Symptom:** startup refuses to unlock with an epoch/anti-rollback error after a restore.
- **Cause:** an older bundle was placed over a newer epoch. The rollback guard is doing its job,
  refusing a stale (possibly-rotated-out) credential.
- **Recover:** use the current bundle, or deliberately re-establish the epoch with a fresh
  `basil bundle create` / `basil bundle set-backend` if the rollback was intentional (e.g. a real restore).

## Broker process or socket exposed

- **Contain:** stop the broker (its socket is the only ingress; no socket, no requests). Confirm
  socket ownership/permissions and that only intended uids could connect.
- **Eradicate:** rotate the backend credential (`basil bundle set-backend`) on the assumption the in-memory
  token was reachable; rotate any keys the audit log shows were used during the window.
- **Review:** the audit log is your authority on what was actually requested and by whom while the
  process was exposed.

## Invalid key (missing seed / `publicPath`)

- **Symptom:** a materialize-to-use key fails reconcile (boot) or returns `INTERNAL`/`UNSUPPORTED` at
  request time; the loader rejects a catalog missing/extra `publicPath`.
- **Fix:** provision both halves out of band (the private at `path`, the public at `publicPath`),
  then re-run `basil config check`. Reconcile probes *both*, so a half-provisioned key fails closed
  rather than serving a key whose public can't resolve.

## Suspected unauthorized access

- **Detect:** audit-log spikes in `deny`, or `allow` records whose `actor_id` subject shouldn't have that
  grant.
- **Contain:** tighten the offending [policy rule](/configuration/policy/) (or set the key
  `writable: false`) and reload; confirm no two services resolve to the suspect subject.
- **Review:** reconstruct the full request history for the subject/key from the audit log: every
  gated decision is there, with what granted it.

## Where to go next

- [Error & status code reference](/troubleshooting/error-reference/): what each wire code means.
- [Rotating keys](/operations/rotating-keys/) · [Revocation](/operations/revocation/) ·
  [Audit logs](/operations/audit-logs/)
