+++
title = "Migrating from sops-nix to Basil"
weight = 50
+++

# Migrating from sops-nix to Basil

If you run services on NixOS and deliver secrets with `sops-nix` or `agenix`, you can move to Basil
one secret at a time. You do not have to migrate everything at once. `sops-nix` and Basil can
coexist while you move the secrets that benefit most from brokered access, live rotation, and
in-place custody.

The goal is not to turn every secret file into a different secret file. Start with a value that is
easy to move, then graduate keys to Basil's stronger model: the workload asks for an operation, and
the key stays in the backend.

## What changes

`sops-nix` decrypts secrets into files at activation time, typically under `/run/secrets/...`, and
hands each service a **value on disk**. That works well for static boot-time material, but it means:

- the decrypted secret is a file a compromised service, backup job, or accidental `cat` can read;
- rotation means editing the encrypted source and rebuilding or switching the system;
- the age or GPG host key that decrypts broad sets of secrets lives on the host;
- authorization is file ownership and mode, not a per-operation policy decision;
- there is no broker audit trail for who read or used a secret.

Basil gives you two migration levels:

| Level                        | What the workload gets                                               | Custody model                                                               | Best for                                                        |
| ---------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Tier 1: value access**     | A secret value fetched on demand                                     | Secret stays in the backend until Basil fetches it for an authorized caller | DB passwords, API tokens, existing apps that still need a value |
| **Tier 2: operation access** | A result from `sign`, `encrypt`, `decrypt`, `issue-cert`, or minting | Key is used *in place* by a transit, KMS, PKI, or NATS backend              | TLS keys, signing keys, encryption keys, workload identities    |

Tier 1 is the smallest change. It is still a value, but it is off the Nix store, policy-gated,
audited, and rotatable without a rebuild.

Tier 2 is the security win. For TLS keys, signing keys, encryption keys, certificates, and minted
identity credentials, Basil brokers the operation rather than handing out the private material.

## Side-by-side

|                        | `sops-nix` today                | Basil Tier 1: value                       | Basil Tier 2: operation                      |
| ---------------------- | ------------------------------- | ----------------------------------------- | -------------------------------------------- |
| Where the secret lives | Decrypted file on disk          | Backend value, fetched on demand          | Backend key, **never leaves**                |
| Rotation               | Edit encrypted source + rebuild | `basil rotate` or `basil set` live        | `basil rotate` live, with grace window       |
| Who can read it        | Anything running as the owner   | Only the granted subject, audited         | Nobody reads the key material                |
| Authorization          | File ownership and mode         | Default-deny policy per subject           | Default-deny policy per subject              |
| Audit                  | No broker audit                 | Every access logged                       | Every operation logged                       |
| App change needed      | None                            | Small: fetch from Basil instead of a file | App calls `sign`, `encrypt`, `decrypt`, etc. |

## Concept mapping

| `sops-nix`                                | Basil                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------ |
| `sops.secrets."app/db_password"`          | catalog key `app.db_password` with `class = "value"` and `engine = "kv2"`            |
| `owner = "app"` and file mode             | policy subject for the app uid plus a rule granting `op:get`                         |
| age or GPG host key                       | Basil's sealed bundle, unlocked once at boot                                         |
| edit encrypted file and rebuild to rotate | `basil rotate --key-id app.db_password`, or `basil set` for caller-supplied material |
| no read audit                             | audit log entry for every read or operation                                          |

## Generate the stubs: `basil init --from-sops`

You do not have to hand-author the Tier 1 catalog. Point `basil init` at your existing sops file
and it scaffolds the migration skeleton for you:

```sh
basil init --backend openbao --dir ./basil --from-sops secrets.yaml
```

`--from-sops` reads **only the key names** from a sops YAML or JSON file. The encrypted values are
never touched, and the `sops` metadata block is skipped. Decryption stays where it belongs, in
`sops -d` under your existing age or GPG key, until you migrate each value on purpose.

For every secret it finds, `init`:

- adds one `value` catalog stub with `missing: warn`, so the broker starts and `doctor` warns
  instead of failing while a value still lives in sops. Nested keys flatten to dotted names:
  `app.db_password` from a nested `app: db_password:` entry.
- grants a `sops-migrator` role (`get` + `set`) over the imported names to the uid that ran `init`,
  so the migration itself is policy-checked and audited like everything else.
- prints one hand-off command per secret, decrypting with sops and writing through the broker:

```sh
basil --socket ./basil/basil.sock set --key-id app.db_password \
  "$(sops -d --extract '["app"]["db_password"]' secrets.yaml)"
```

Each generated stub records its origin, and the value stays in sops until you run its `set`:

```json
"app.db_password": {
  "class": "value",
  "backend": "primary",
  "engine": "kv2",
  "path": "sops/app/db_password",
  "writable": true,
  "missing": "warn",
  "description": "Imported from sops key `app.db_password` by `basil init --from-sops`; value still lives in sops until migrated with `basil set`."
}
```

Migrate one secret, point its consumer at Basil, verify, then do the next. When the last value is
across, verify the set with `basil doctor --keys` and retire the sops entries.

{% best(title="Drop `set` when the migration is done") %}
The `sops-migrator` grant exists to move values in, not to stay. Once every secret is migrated,
remove `set` from the role (or delete the rule) so the migration uid keeps read access at most.
Least privilege applies to operators too.
{% end %}

{% note(title="Runnable companion: the NixOS migration VM") %}
The Basil repo ships `examples/nixos-vm/`, a before/after NixOS VM pair for this exact migration: a
host delivering a secret with `sops-nix`, and the same host after the move to a Basil catalog key
and policy grant. Use it to rehearse the cutover before touching a real machine.
{% end %}

## Before: `sops-nix`

A typical service reads its database password from a decrypted file:

```nix
sops.secrets."app/db_password" = {
  owner = "app";
  # Decrypted to /run/secrets/app/db_password at activation.
};

systemd.services.app = {
  serviceConfig = {
    User = "app";
    Environment = "DB_PASSWORD_FILE=/run/secrets/app/db_password";
  };
};
```

## After, Tier 1: broker the value

Give the service its own uid, declare the secret as a catalog value, grant that uid `op:get`, and
have the service fetch the value from Basil instead of reading a `sops-nix` file.

```nix
# Import the Basil NixOS module from a Basil checkout.
services.basil = {
  enable = true;

  catalog = {
    schemaVersion = 1;
    backends.bao = {
      implementation = (import ./nix/backend-capabilities.nix).OPENBAO_2_5;
      addr = "https://127.0.0.1:8200";
    };
    keys."app.db_password" = {
      class = "value";
      backend = "bao";
      engine = "kv2";
      path = "secret/data/app/db-password";
      writable = true;
      missing = "generate";
      generate = { format = "ascii-printable"; bytes = 24; };
      description = "Database password for app.service, generated in place.";
    };
  };

  policy = {
    unixSubjects.svc-app = { user = "app"; };

    rules = [
      {
        id = "app-can-read-its-password";
        subjects = [ "svc-app" ];
        action = [ "op:get" ];
        target = [ "app.db_password" ];
        comment = "The app service may fetch only its own database password.";
      }
    ];
  };

  bundle = "/var/lib/basil/bundle.sealed";
  settings = {
    socket = "/run/basil/basil.sock";
    socketMode = "0660";
    socketGroup = "basil";
    vaultAddr = "https://127.0.0.1:8200";
    auditLog = "/var/lib/basil/audit.jsonl";
  };
};

users.users.app = { isSystemUser = true; group = "app"; };
users.groups.app = {};

systemd.services.app = {
  serviceConfig = {
    User = "app";
    Group = "app";
    SupplementaryGroups = [ "basil" ];
    RuntimeDirectory = "app";
  };

  preStart = ''
    ${pkgs.basil}/bin/basil --socket /run/basil/basil.sock \
      get --key-id app.db_password \
      --out-file "$RUNTIME_DIRECTORY/db_password"
  '';
};
```

The application can keep reading `$RUNTIME_DIRECTORY/db_password`, but the value is no longer baked
into the system configuration. Only the granted uid can obtain it, and each read is audited.

{% best(title="Prefer fetching in process when you can") %}
Writing a runtime file is a compatibility step for applications that already expect one. If you own
the application code, call Basil from the Rust or Go client at the moment the value is needed, so the
secret lives only in process memory.
{% end %}

## After, Tier 2: broker the operation

If the secret is really a key, do not deliver it. Declare it as an in-place key and grant only the
operation the workload needs:

```nix
services.basil.catalog.keys."app.tls.signing_key" = {
  class = "asymmetric";
  keyType = "ed25519";
  backend = "bao";
  engine = "transit";
  path = "app-tls";
  writable = true;
  missing = "generate";
};

services.basil.policy.roles.signer = [ "sign" "verify" "get_public_key" ];

services.basil.policy.rules = [
  {
    id = "app-can-sign";
    subjects = [ "svc-app" ];
    action = [ "role:signer" ];
    target = [ "app.tls.signing_key" ];
  }
];
```

The service now calls Basil to sign, verify, or fetch the public key. The private key never touches
the app's disk, memory, environment, or systemd credential store.

The same pattern covers:

- `encrypt` and `decrypt` for AEAD keys;
- `issue-cert` for X.509 leaves from a backend PKI role;
- NATS identity minting and JWT signing;
- SPIFFE X.509-SVID and JWT-SVID issuance.

## Rotation without a rebuild

For generated values and in-place keys, rotation is a live broker operation:

```sh
basil --socket /run/basil/basil.sock rotate --key-id app.db_password
```

For value keys without a `generate` recipe, set new material explicitly:

```sh
basil --socket /run/basil/basil.sock set --key-id app.db_password "$NEW_PASSWORD"
```

Compare that with the `sops-nix` loop: edit the encrypted file, commit it, rebuild or switch the
host, then restart whatever needs the new value.

## Secret zero

With `sops-nix`, the host key that can decrypt the secret set sits on the host. With Basil, the
host-local credential is the **sealed bundle**, unlocked once at boot. The bundle holds the backend
credential Basil needs, encrypted to one or more unlock slots.

Choose the unlock method that fits the host:

- `passphrase` for unattended startup through a systemd credential or protected file;
- `tpm` for a TPM-sealed slot on hosts built with the `unlock-tpm` feature;
- `age-yubikey` for a hardware-backed operator unlock;
- `bip39` for break-glass recovery.

Create the bundle with `basil bundle create`, keep it mode `0600`, and keep it outside the Nix store.
See [Unlock & the sealed bundle](/configuration/unlock-and-bundle/) for the full model.

## Tradeoffs

- **You need a backend.** Basil fronts OpenBao, HashiCorp Vault, AWS KMS, Google Cloud KMS, 1Password,
  or `db-keystore`, depending on the custody model you choose. `sops-nix` needs no running broker.
- **Basil adds a local hop.** The agent brokers access over a Unix socket and authorizes by kernel
  peer credentials. That is the point, but it is still another service to run.
- **Tier 2 needs an app change.** The app calls the broker instead of reading a file. Tier 1 only
  changes where the value comes from.
- **One uid per workload matters.** The uid is usually the workload identity. Two services sharing a
  uid share every grant.

## Try it before changing a host

Run the dev fixture first. It boots a throwaway OpenBao or Vault, writes a catalog and policy, seals
a bundle, and prints the commands to drive the broker:

```sh
scripts/prefill-test-store.sh --engine openbao
```

That gives you the same control loop you will use on a real host: catalog, policy, sealed bundle,
broker, and CLI calls over the Basil socket.

## Where to go next

- [Quickstart](/getting-started/quickstart/): run Basil end to end with the dev fixture.
- [Make it your own](/getting-started/make-it-your-own/): adapt the self-contained Nix example.
- [The catalog](/configuration/catalog/): declare value keys, transit keys, and custody choices.
- [The policy](/configuration/policy/): grant `op:get`, roles, and per-workload authority.
