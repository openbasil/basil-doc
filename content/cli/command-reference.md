+++
title = "Command reference"
weight = 20
+++

# Command reference

Every client command takes a global `--socket <path>`. Basil authenticates the caller from kernel
uid/gid evidence and resolves that evidence to a policy subject before authorization.
Daemon/offline commands operate on config files and don't need a running broker.

## Daemon & offline

| Command | Purpose |
| --- | --- |
| `basil agent -c <toml>` | Run the broker daemon from a TOML startup config. See [Configuration overview](/configuration/overview/). |
| `basil demo [--dir …] [--paced] [--force]` | Zero-dependency guided tour on the built-in db-keystore backend: scaffold a throwaway broker, start it, and drive sign → verify → denied read → explain → encrypt → mint, audit tail included. `--paced` adds human pacing for watching or recording. See [The five-minute demo](/getting-started/demo/). |
| `basil init --backend … --unlock … --dir … [--socket …] [--from-sops <file>]` | Scaffold a least-privilege starter catalog + policy + config. Generated `socket` follows `--socket` > `BASIL_SOCKET` > `<dir>/basil.sock`. `--from-sops` reads only the key **names** from a sops YAML/JSON file, adds one `value` stub per secret (`missing: warn`), grants a `sops-migrator` role, and prints the per-secret `sops -d`-to-`basil set` hand-off. See [Migrating from sops-nix](/getting-started/sops-nix-to-basil/). |
| `basil completions <shell>` | Print a completion script for `bash`, `zsh`, `fish`, `elvish`, or `powershell` to stdout, e.g. `basil completions bash > /etc/bash_completion.d/basil`. The deb, Arch, and Nix packages ship the bash/zsh/fish scripts pre-installed. |
| `basil bundle create <bundle> --slot …` | Create a sealed bundle with `--slot`/`--backend`. `--deposit-key <OUT>` adds a public deposit recipient; `--from <FILE>` loads a `[[slot]]`/`[[backend]]` TOML manifest. |
| `basil bundle add-slot <bundle> --slot … --open …` | Add an unlock slot to an existing bundle. |
| `basil bundle set-backend <bundle> --backend … --open …` | Replace one backend credential in the sealed payload. |
| `basil bundle deposit <bundle> --backend … -r <recipient> -i <identity>` | Append a signed credential deposit without opening the bundle. |
| `basil bundle allow <bundle> --contributor … --backend … --open …` | Allow a contributor signing key to deposit selected backend ids. |
| `basil bundle promote <bundle> [--dry-run] [--backend …] [--contributor …] --open …` | Review or fold authorized deposits into the sealed payload. |
| `basil bundle deposit-key <bundle> --out … --open …` | Export or create the bundle's public deposit recipient. |
| `basil bundle verify <bundle> --open …` / `show <bundle> [--open …]` | Verify unlock or inspect non-secret bundle metadata. |
| `basil explain --subject … (--op … --key … \| --effective) [--catalog … --policy …] [--live] [--json]` | Policy dry-run; offline against the files by default, `--live` against the running broker. `--effective` previews every grant (offline-only). See [Policy explain](/operations/policy-explain/). |
| `basil doctor -c <toml> [--json] [--keys] [--strict]` | Preflight diagnostics: validate catalog + policy, enforce capability + invocation bindings; `--keys` adds the authenticated per-key probe; `--strict` fails on warnings. See [Doctor](/operations/doctor/). |
| `basil cache --check [--age 30d] [-q\|--json]` | Inspect and integrity-check the private OCI evidence cache. `--age` selects entries whose last use is at least the supplied duration ago. |
| `basil cache prune [--force] <id-or-reference>…` | Preview exact-ID or exact observed-reference removal. `--force` executes the displayed plan. |

## OCI evidence cache

`basil cache` is an offline operator command. It reads the `[oci]` cache path and bounds from the
same startup config as the agent, including `-c`/`--config` and the normal config overrides. It does
not contact the broker or require a policy grant.

### Inspect entries

```sh
basil cache -c /etc/basil/agent.toml --check
basil cache -c /etc/basil/agent.toml --check --age 30d
basil cache -c /etc/basil/agent.toml --check --json
basil cache -c /etc/basil/agent.toml --check -q
```

The human output prints one deterministic ID-sorted row per entry: cache ID, OCI subject digest,
encoded bytes, last-use timestamp, age since the last successful online refresh, the fixed refresh
threshold, current degradation duration, source repository, and observed references. The final line
reports selected entries, selected encoded bytes, and corrupt entries removed.

`--age` accepts a positive integer followed by `d`, `h`, `m`, or `s`. It filters on `lastUse`; it
does not remove anything. `-q` prints one strict lowercase SHA-256 cache ID per line. `--json` emits
an ID-sorted array with these stable fields:

| Field | Meaning |
| --- | --- |
| `id`, `subject` | Content-derived cache ID and immutable OCI subject digest. |
| `references`, `source` | Exact observed references and repository/source boundary. |
| `lastUse`, `collectedAt`, `lastSuccessfulRefresh` | Unix-second lifecycle timestamps. |
| `ageSeconds`, `refreshThresholdSeconds`, `refreshDue` | Refresh age, the 30-day threshold, and whether refresh is due. |
| `degradedSince`, `degradedDurationSeconds` | First continuously failed refresh and its duration; both are `null` when healthy. |
| `encodedSize` | Bytes charged to the aggregate cache limit. |

`--check` validates the bounded on-disk format, hashes, file identity, ownership, modes, and link
counts. Safely identified corrupt regular entries are removed and counted as cache misses. The
integrity inventory has no authorization effect. Cache admission separately repeats offline
verification with the current trust and denylist generation. Use `basil doctor` when inspection
must be strictly read-only.

### Preview and confirm pruning

```sh
# Preview every entry associated with this exact observed reference.
basil cache -c /etc/basil/agent.toml prune registry.example/team/app:stable

# Confirm removal by exact 64-character lowercase cache ID.
basil cache -c /etc/basil/agent.toml prune --force \
  0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

A strict 64-character lowercase hexadecimal selector is an exact cache ID. Every other selector is
matched as one complete previously observed reference. Multiple selectors form one deterministic
ID-sorted plan. The default command prints that plan and changes nothing; repeat it with `--force`
only after reviewing the candidates.

Execution rechecks each previewed file's identity and encoded hash. An entry that changed after the
preview is skipped and reported. Removal retires and clears only the already validated opened file,
so a concurrent pathname replacement is preserved. Basil reuses bounded private retirement slots;
repeated prune, restart, and re-store cycles do not grow metadata without bound.

## Status & probes

| Command | Purpose |
| --- | --- |
| `status [--json]` | Agent backend, version, protocol; `--json` prints a stable one-line JSON object for automation. Answered only for peers that resolve to a policy subject (the backend kind is deployment detail); needs no further grant. |
| `health [--json]` | Liveness probe (no backend I/O). Exit 0 = alive. |
| `ready [--json]` | Readiness probe (non-secret summary). Exit 0 = ready, 1 = not ready. |

See [Health & readiness probes](/operations/health-and-readiness/).

## Keys

| Command | Purpose |
| --- | --- |
| `new-key [--key-id …] [--key-type …]` | Create an asymmetric or KEM key. `--key-id` defaults to `example.signing_key`; `--key-type` defaults to `ed25519` (accepted values below). |
| `import --key-id … --key-type … [--seed-hex …\|--pkcs8-file …] [--check]` | BYOK a single key; raw seed Ed25519-only, PKCS#8 DER for Ed25519/RSA/P-256. `--check` validates locally. |
| `import-set --file … [--check]` | BYOK a batch, all-or-nothing. `--check` validates the manifest locally. |
| `rotate --key-id …` | Rotate a key; prints the new version. |
| `list [--prefix …]` | Value-free key inventory (visible to you); `--prefix` filters by key-id prefix. |

`--key-type` accepts the catalog `keyType` values: `ed25519`, `ed25519-nkey`, `rsa-2048`, `ecdsa-p256`,
`ecdsa-p384`, `ecdsa-p521`, `ml-dsa-44`/`ml-dsa-65`/`ml-dsa-87` (signing), and
`ml-kem-512`/`ml-kem-768`/`ml-kem-1024` (KEM). See [The catalog](/configuration/catalog/#key-types).

See [Importing (BYOK)](/operations/importing-byok/) and [Rotating keys](/operations/rotating-keys/).

## Crypto

| Command | Purpose |
| --- | --- |
| `sign --key-id … <payload>` | Sign a message (raw, not pre-hashed). |
| `verify --key-id … --signature … <payload>` | Verify a signature. |
| `encrypt --key-id … [--algorithm …] [--aad-hex …] <plaintext>` | AEAD encrypt; **Basil owns the nonce**. |
| `decrypt --key-id … --algorithm … --version … --nonce … --ciphertext … [--aad-hex …]` | AEAD decrypt an envelope. |

## Secrets / values

| Command | Purpose |
| --- | --- |
| `get --key-id … [--version …] [--raw\|--out-file …] [--format raw\|hex\|base64\|base64-url-no-pad]` | Read a value/public key. `--format base64` emits standard padded Base64 for consumers such as NetBird. |
| `set --key-id … [--hex] <value>` | Write a value key. |

## Minting & identity

| Command | Purpose |
| --- | --- |
| `mint-jwt` | Mint a generic JWT using the issuer key's JWS algorithm (EdDSA, ES256, ES384, or RS256). |
| `mint-nats-user` | Mint a NATS user JWT. Pass `--issuer-account` when `--key-id` is an account *signing* key. |
| `sign-nats-jwt` | Validate and sign a caller-supplied NATS JWT JSON claim document with the `ed25519-nkey` profile. |
| `issue-nats-creds` | Locally assemble a canonical `nsc`-style user `.creds` file from a signed user JWT and user seed. |
| `issue-cert` | Issue a DNS/IP-SAN TLS leaf from backend PKI. |

Flag signatures for the minting commands:

- `mint-jwt --key-id … --sub … [--ttl-secs …] [--claims-json …]`
- `mint-nats-user --key-id … --user-nkey … [--issuer-account …] [--name …] [--ttl-secs …] [--pub-allow …] [--pub-deny …] [--sub-allow …] [--sub-deny …]`
- `sign-nats-jwt --key-id … (--claims-json … | --claims-file …) [--expect-type …] [--ttl-secs … | --expires-at-unix …] [--issued-at-unix …] [--rewrite-jti]`
- `issue-nats-creds (--jwt … | --jwt-file …) (--seed … | --seed-file …) --out-file … [--mode 0600|0660]`
- `issue-cert --key-id … --common-name … [--dns-san …] [--ip-san …] --ttl-secs …`

`mint-jwt` derives the JWS algorithm from the issuer key: Ed25519 signs `EdDSA`, ECDSA P-256 signs
`ES256`, ECDSA P-384 signs `ES384`, and RSA-2048 signs `RS256`. Generic `mint-jwt` is at algorithm
parity with the JWT-SVID path. `ES512` (P-521) is not a JWT issuer at all (it is backend-native for
the generic `sign`/`verify` operations only), so a P-521 issuer key is rejected for `mint-jwt`. The
JWT header `kid` matches the key id Basil publishes in JWKS for the same issuer public key.

NATS minting, signing, validation, and curve xkey boxes live on the broker's `NatsService`. The CLI
exposes only `mint-nats-user` and `sign-nats-jwt`, plus the local `issue-nats-creds` assembler above.
Minting operator, account, signer, server, and curve identities, along with `ValidateNatsJwt`,
`EncryptNatsCurve`, and `DecryptNatsCurve`, are broker RPCs reached through the Rust, Go, or generated
gRPC clients, not the CLI. See [NATS integration](/clients/nats/).

`sign-nats-jwt` forwards the supplied JSON object as raw claim bytes to the broker. This preserves
large integer-valued NATS claims that would lose precision through protobuf's structured JSON number
encoding. The [NATS JWT reference](/reference/nats-jwt-reference/) documents every account and user
claim the JSON document may carry and the semantic defaults Basil applies.

## Admin (permission-gated)

These require dedicated policy grants. They are not implied by data-plane grants or root's `*`.

| Command | Purpose | Grant |
| --- | --- | --- |
| `reload [--check] [--json]` | Validate + atomically swap catalog/policy from disk. `--check` is a dry-run. | `op:reload` over `broker.reload`. See [Hot reload](/operations/hot-reload/). |
| `explain --live --subject … --op … --key … [--json]` | Live "would this be allowed, and why?" against the serving generation (`--live`; the default offline mode needs no grant). | `op:explain` over `broker.explain`. See [Policy explain](/operations/policy-explain/). |
| `revoke --trust-domain … --jti … --expires-at-unix … [--json]` | Persist and publish a JWT-SVID revocation. | `op:revoke` over `broker.revoke`. See [Revocation](/operations/revocation/). |

## Where to go next

- [CLI overview](/cli/overview/): the daemon-vs-client split and how attestation scopes a command.
- [The policy](/configuration/policy/): the grants that bound what any command may do.
- [Rotating keys](/operations/rotating-keys/): a common day-2 task driven from this CLI.
