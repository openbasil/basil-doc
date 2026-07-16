+++
title = "Hot reload & admin reload"
weight = 50
+++

# Hot reload & admin reload

Basil reloads its **catalog** and **policy** in place, without requiring another unseal, on a
`SIGHUP` signal or through a permission-gated admin RPC (and the `basil reload` CLI). Both paths call
the *identical* fail-closed reload engine.

## SIGHUP hot reload

Basil reloads in place when it receives `SIGHUP`. The keystore stays unlocked and every in-flight
request keeps serving throughout. Each reload that succeeds advances a monotonic **generation id**; an
operation pins one generation at request entry and uses it end to end, so a reload mid-request can
never mix an old catalog with a new policy.

### Trigger

Send `SIGHUP` to the broker's main PID. The agent re-reads the *same* catalog/policy paths it was
started with. For safety, basil never accepts configuration over the wire.

```sh
# Under systemd (the Nix module wires ExecReload to this):
systemctl reload basil-agent
# Or directly:
kill -HUP "$(systemctl show -p MainPID --value basil-agent)"
```

On NixOS, a `nixos-rebuild switch` that changes *only* the catalog or policy repoints the
`/etc/basil/{catalog,policy}.json` symlinks and sends `SIGHUP` for you; any other setting change goes
through `ExecStart` (a full restart). Edit the source-of-truth files, not `/etc` directly.

### What a reload validates (fail closed)

Before swapping, the candidate runs the *full* startup/`check` validation: catalog + policy parse,
every hard error, the JWT-SVID issuer-algorithm guardrail, and the `publicPath` enforcement for
materialize-to-use keys. The reload is **non-mutating**: it performs no backend I/O and never
generates missing key material on the signal path. If *anything* fails to validate, Basil does not
swap; the previous generation keeps serving unchanged.

After a successful real reload, Basil also refreshes the JWT-SVID deny-list backing store. This read
is monotonic: newly loaded revocations are unioned into the live set, local in-memory revocations are
preserved, and a refresh failure leaves the prior set serving while emitting a
`revocation_refresh_failed` record.

### Reloadable vs. restart-only

Only the *content* the policy engine and audit trail consume is reloadable. Changing backends or the
socket path requires a restart.

| Dimension | Reloadable on SIGHUP? |
| --- | --- |
| Policy rules / roles / name & membership tables | ✅ Yes |
| A key's `writable`, `labels`, `description`, `missing` | ✅ Yes |
| Adding / removing a **backend**, or any backend's `kind`/`addr`/`engines`/`capabilities`/`requires` | ⛔ Restart-only |
| Adding / removing a **key**, or any key's `backend`/`path`/`engine`/`keyType`/`publicPath` | ⛔ Restart-only |
| Unlock / sealed bundle, socket bind, backend credentials, broker limits | ⛔ Restart-only |

A backend's `mintKeyTypes` set is not part of the routing shape: a change to it is re-validated by the
load-time capability check and swapped in on reload, so it is not restart-only.

{% note(title="Adding a key needs a restart") %}
Because a new key changes the routing shape, you cannot introduce a key (or backend) by hot reload;
that is a restart. A reload only ever re-authorizes *existing* keys, so there is no missing-material
question to answer on the signal path beyond what startup reconcile already settled.
{% end %}

### Rollback

Rollback is automatic: a rejected reload never replaced the prior generation, so there is nothing to
roll back. To revert a *successful* reload, restore the previous catalog/policy files and SIGHUP
again. Nothing is ever left in a half-swapped state.

### Observability

A reload emits a `basil.audit.reload` JSONL line carrying the actor (`SIGHUP`), the
`previous_generation` and `generation` ids, the `outcome` (`applied` / `rejected`), and a stable
`reason` token. The active generation id also tags every authorization record.

Each candidate source read also emits the `basil.configuration.source` tracing event described in
[Configuration overview](/configuration/overview/#configuration-source-traces/). On reload, the event
sets `active_generation_present = true` and records the generation that was serving when validation
started. A rejected reload sets `prior_generation_active = true`, so log consumers can distinguish a
failed candidate from the generation that remains live.

| `reason` on reject                           | Cause                                                                                              |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `validation_failed`                          | Catalog/policy failed to parse or violated a hard error / guardrail (issuer alg, `publicPath`).    |
| `routing_shape_changed`                      | The edit touched a restart-only dimension. Apply it via a restart.                                 |
| `catalog_read_failed` / `policy_read_failed` | A configured file could not be re-read (permissions / path).                                       |
| `no_reload_inputs`                           | The broker was started without configured catalog/policy paths; SIGHUP only reopens the audit log. |

## Admin reload (CLI + gRPC)

The same in-place reload is available as a **permission-gated admin RPC** over the broker's existing
peer-cred-attested Unix-socket admin surface, and through the `basil reload` CLI. Unlike a bare
`SIGHUP` (which a signal cannot acknowledge), the RPC returns a validated result: the old → new
generation id plus key/grant counts on success, or a structured rejection (with the previous
generation still serving) on failure.

{% note(title="Disk-only trust boundary: never config over the wire") %}
The reload RPC re-reads the catalog/policy from the broker's configured on-disk paths, the same
root-owned files the daemon loaded when it started. It never accepts catalog or policy content over the
wire. This is enforced *by construction*: the request message has no field for config bytes; its
only input is the dry-run flag. A client cannot inject or override policy.
{% end %}

### The permission grant (least privilege, default-deny)

Reload is gated by a **dedicated `reload` policy op** that is not implied by any data-plane grant:
not `sign`/`encrypt`/`get`/`set`/`rotate`/`mint`, and not even root's `*` wildcard. The only way to
grant it is an explicit `op:reload` action over the reserved broker-admin target `broker.reload`:

```json
{
	"schema": "policy",
	"subjects": {
		"svc.reload": {
			"domain": "host-process",
			"match": { "all": [{ "process.uid": 4242 }] }
		}
	},
	"rules": [
		{
			"id": "broker-admin-reload",
			"subjects": ["svc.reload"],
			"action": ["op:reload"],
			"target": ["broker.reload"]
		}
	]
}
```

On NixOS the same rule is written in the module's policy options:

```nix
services.basil.policy.subjects."svc.reload" = {
  domain = "host-process";
  match.all = [ { "process.uid" = 4242; } ];
};
services.basil.policy.rules = [
  { id = "broker-admin-reload";
    subjects = [ "svc.reload" ];
    action    = [ "op:reload" ];
    target    = [ "broker.reload" ]; }
];
```

`broker.reload` is a reserved admin *target*, not a catalog key. A caller lacking this grant is denied
fail-closed (`PermissionDenied`), and the denial is audited with the attested caller identity.

### CLI usage & the `--check` dry-run workflow

Run the CLI *under the granted identity*. Basil attests the caller by its kernel `SO_PEERCRED` uid,
so use systemd `User=`/`Group=` or `runuser -u <svc>`; the CLI cannot impersonate.

```sh
# Dry-run: validate the on-disk candidate WITHOUT swapping the serving generation.
# Runs the exact validation a real reload runs; exits nonzero if it would be rejected.
basil reload --check

# Real reload: validate, then atomically swap. Prints old->new generation id + counts.
basil reload

# Machine-readable (stable one-line JSON object) for automation:
basil reload --check --json
basil reload --json
```

Recommended flow: run `basil reload --check` first (or `basil doctor` in CI; both run the
identical validation), confirm it validates, then `basil reload` to apply. The dry-run leaves the
serving generation unchanged; the response reports the *would-be* new generation id.

### Exit codes & failure modes

| Condition | CLI exit | Surface |
| --- | --- | --- |
| Reload applied (or `--check` validated cleanly) | `0` | Prints the outcome (old→new generation id + key/grant counts). |
| Candidate **rejected** (validation / routing-shape), previous generation keeps serving | `1` | Prints the rejection `reason`; the RPC returns `OK` with a structured rejection, not a wire error. |
| **Permission denied** (caller lacks the `reload` grant) | nonzero | `PERMISSION_DENIED` gRPC status; the denial is audited with the attested caller. |
| Missing peer credentials / connect / RPC failure | nonzero | `UNAUTHENTICATED` or a transport error. |

The rejection `reason` tokens are the same as the SIGHUP path. Both an applied reload and a denial are
audited.

{% best() %}
Gate the same catalog/policy through `basil doctor` in CI before you deploy. It runs the
identical validation the reload runs, so a reload that would be rejected is caught pre-merge rather
than at the SIGHUP. After a reload, confirm the new `generation` id in the audit trail before
declaring the change live.
{% end %}

{% note() %}
Both the `SIGHUP` and admin-RPC paths are covered end to end by a cross-engine (OpenBao + Vault) live
test: a valid reload bumps the generation without re-unseal, an invalid candidate keeps the prior
generation serving, and both emit `basil.audit.reload` events of identical shape differing only in the
actor.
{% end %}

## Where to go next

- [The policy](/configuration/policy/): writing the `op:reload` grant.
- [Policy explain / dry-run](/operations/policy-explain/): preview authorization before you reload.
- [Error reference](/troubleshooting/error-reference/): the wire status codes a denial returns.
