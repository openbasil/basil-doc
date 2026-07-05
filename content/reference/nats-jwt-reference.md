+++
title = "NATS JWT reference"
weight = 40
+++

# NATS JWT reference

This is the design reference for the NATS account and user JWT claims that Basil creates, signs, and
validates. It is the shared vocabulary behind [`sign-nats-jwt`](/cli/command-reference/) on the CLI,
[`sign_nats_jwt`](/clients/rust/) in the Rust client, and
[`SignNatsJwt`](/clients/go/) in the Go client: every claim these APIs accept or emit is described
here, along with the semantic defaults Basil applies so that "unset" never quietly means the wrong
thing. Read it when you build a claim document by hand, or when you need to know exactly what a field
means before you sign it.

Basil brokers the **operation**, not the key: the NATS NKey seed stays in the vault and signs in
place, while you supply the claim document. Getting the claim semantics right is therefore your
responsibility, and the point of this page.

{% note(title="Sources and versions") %}
This reference was developed on **2026-07-04** against:

- **[`github.com/nats-io/jwt/v2`][jwt-v2]** at **`v2.8.2`** (commit
  `82017236da50e4a0173091105d82d46228b8dccf`), the upstream Go library that defines the claim
  structures and their validation.
- **`nsc` `2.15.0`** help output, the reference NATS credential-management CLI, for the flag-to-claim
  mapping in the [`nsc` CLI coverage](#nsc-cli-coverage) section.

When you upgrade against a newer `jwt/v2` or `nsc`, re-check the claims and defaults below rather
than assuming they still hold.
{% end %}

## Encoding model

Both account and user JWTs have standard claim fields at the top level and a NATS payload under
`nats`.

`Encode` always sets:

- `iss`: public NKey of the signing key.
- `iat`: current UTC Unix seconds.
- `jti`: deterministic hash of top-level `ClaimsData` after clearing `jti`.
- `nats.type`: `account` or `user`.
- `nats.version`: the library version constant.

The library validates signatures against `iss`, but callers must decide whether that issuer is
trusted. Account JWTs may be signed by an operator or account key. User JWTs must be signed by an
account key. Account-signing keys are also account NKeys; when one signs a user JWT, the user claim
must carry `nats.issuer_account`.

All `omitempty` fields disappear when set to their Go zero value. For numeric limits, absence and
zero are not the same as unlimited. The NATS convention is `-1` (`NoLimit`) for unlimited. Use the
library constructors as the semantic defaults, not raw zero-valued structs.

## Top-level claims

- `aud` (`Audience`): Optional audience string. The JWT library does not enforce it for account or
  user claims.
- `exp` (`Expires`): Unix seconds. `0` means no expiry. Validation fails the time check when
  `now > exp`.
- `jti` (`ID`): JWT ID. Overwritten by `Encode`; derived from `ClaimsData`, not from the nested
  `nats` payload.
- `iat` (`IssuedAt`): Unix seconds. Overwritten by `Encode`; not otherwise time checked.
- `iss` (`Issuer`): Signing public key. Overwritten by `Encode`.
- `name` (`Name`): Human-readable name.
- `nbf` (`NotBefore`): Unix seconds. `0` means valid immediately. Validation fails the time check
  when `nbf > now`.
- `sub` (`Subject`): Public NKey identifying the account or user. Account claims require an account
  public key. User claims require a user public key.

## Shared NATS types

`nats.tags`: Unique lower-case tags when manipulated through `TagList`. Empty tags are ignored by the
helper.

`nats.type`: Claim type. `Encode` sets `account` or `user`.

`nats.version`: Library version. `Encode` sets it.

Subject strings must be non-empty, contain no spaces, not start or end with `.`, and not contain
consecutive `.`. Wildcards are detected as `>`, `.>`, `*`, `.*`, or `.*.` forms.

Permissions are embedded directly in user claims and under `account.nats.default_permissions`, with
shared validation rules from [`types.go`][types]:

- `pub.allow`, `pub.deny`: Publish subjects. Queue names are invalid here.
- `sub.allow`, `sub.deny`: Subscribe subjects. A value may be `"<subject> <queue>"` with exactly one
  separating space.
- `resp.max`: Response-permission message count. Present only when `resp` exists.
- `resp.ttl`: Response-permission TTL as a Go `time.Duration` JSON number (nanoseconds). Any value
  currently passes library validation.

User/import limits are embedded directly in user claims and activation claims:

- `src`: CIDR allow-list. Values must parse as CIDR. Empty means no source limit.
- `times`: List of `{start,end}` entries. Times are `hh:mm:ss`; both are required.
- `times_location`: IANA time-zone name used to interpret `times`.
- `subs`, `data`, `payload`: Max subscriptions, bytes, and message payload. `-1` is unlimited.

## User JWT

Constructor default from `NewUserClaims(subject)`:

- `sub` is the supplied user public key.
- `nats.subs`, `nats.data`, and `nats.payload` are `-1`.
- Source, time, permission, tag, bearer, proxy, and connection-type fields are absent.

User-specific claims:

- `nats.pub`, `nats.sub`, `nats.resp`: Per-user permissions, using the shared permission structure
  above. Empty permissions mean no claim-level restriction.
- `nats.src`, `nats.times`, `nats.times_location`: Per-user connection limits.
- `nats.subs`, `nats.data`, `nats.payload`: Per-user NATS limits. Use `-1` for unlimited.
- `nats.bearer_token`: If true, the server skips nonce-signing verification for this user.
- `nats.proxy_required`: Requires a proxy path when interpreted by servers that enforce it.
- `nats.allowed_connection_types`: Optional allow-list of connection types: `STANDARD`, `WEBSOCKET`,
  `LEAFNODE`, `LEAFNODE_WS`, `MQTT`, `MQTT_WS`, `IN_PROCESS`.
- `nats.issuer_account`: Account public key represented by the issuer. Required when an account
  signing key, rather than the account key itself, signs the user.
- `nats.tags`, `nats.type`, `nats.version`: Shared generic fields.

Scoped users are special. `SetScoped(true)` clears the whole `UserPermissionLimits` block. A scoped
signing key validates only user claims whose `iss` equals the scoped key and whose direct permissions
and limits are empty; the server applies the scope template from the account signing key entry.

## Account JWT

Constructor default from `NewAccountClaims(subject)`:

- `sub` is the supplied account public key.
- `nats.signing_keys` and `nats.mappings` are initialized empty.
- NATS and account limits are unlimited: `subs`, `data`, `payload`, `imports`, `exports`, `conn`,
  and `leaf` are `-1`; `wildcards` is true.
- `disallow_bearer` is false.
- JetStream is disabled by leaving `mem_storage` and `disk_storage` at `0`.
- `tiered_limits` is empty.

If an account JWT is self-signed by an account key and has non-empty operator limits, validation
emits a warning. Operator-issued account JWTs are where those limits normally belong.

### Account limits

`nats.limits` contains flattened NATS, account, JetStream, and tiered limits from
[`account_claims.go`][account-claims]:

- `subs`, `data`, `payload`: Max account subscriptions, bytes, and payload.
- `imports`, `exports`: Max numbers of imports and exports.
- `wildcards`: Whether wildcard export subjects are allowed. If false, any export with wildcards is
  invalid.
- `disallow_bearer`: If true, user JWTs in this account cannot be bearer tokens.
- `conn`, `leaf`: Max active client and leaf-node connections.
- `mem_storage`, `disk_storage`: JetStream memory/disk storage. `0` disables that storage class;
  `-1` enables it without a cap.
- `streams`, `consumer`: Max JetStream streams and consumers.
- `max_ack_pending`: Max pending acks for a consumer. Negative values are treated as unlimited by
  `IsUnlimited`.
- `mem_max_stream_bytes`, `disk_max_stream_bytes`: Max bytes for an individual memory or disk stream.
  The library treats `0` and negative values as unlimited for `IsUnlimited`.
- `max_bytes_required`: Requires streams to set max bytes.
- `tiered_limits`: Map from tier name to JetStream limits. A blank tier name is invalid. Tiered
  limits and non-tiered JetStream limits are mutually exclusive.

Validation checks that actual import/export counts do not exceed the configured limits unless the
relevant limit is `-1`.

### Imports

`nats.imports` is a list:

- `name`: Optional display name.
- `subject`: Subject from the initial publisher's perspective. For streams this is the exporter
  subject; for services this is the requester's subject.
- `account`: Exporting account public key. Required.
- `token`: Optional activation JWT. If present, it must decode, match `account`, be issued for the
  importing account, match the import type, pass time checks, and cover the import subject.
- `to`: Deprecated local subject. If non-empty, validation warns. It is mutually exclusive with
  `local_subject`.
- `local_subject`: Preferred local remap subject. If `subject` ends in `>`, `local_subject` must
  also end in `>`. `$<number>` references map to wildcard tokens in `subject`; references plus `*`
  tokens must match the wildcard count.
- `type`: `stream` or `service`.
- `share`: Valid only for service imports; used for latency sharing.
- `allow_trace`: Valid only for stream imports.

Service imports from the same account cannot overlap in local subject namespace.

### Exports

`nats.exports` is a list:

- `name`: Optional display name.
- `subject`: Exported subject. Required and subject-validated.
- `type`: `stream` or `service`.
- `token_req`: Whether activation tokens are required.
- `revocations`: Map of public key, or `*`, to Unix seconds.
- `response_type`: Service response mode: empty/`Singleton`, `Stream`, or `Chunked`. Invalid for
  stream exports.
- `response_threshold`: Duration in nanoseconds. Must be non-negative and valid only for service
  exports.
- `service_latency.sampling`: `headers` or `1..100`; `0` marshals as `headers`.
- `service_latency.results`: Publish subject for latency results. No wildcards.
- `account_token_position`: For wildcard exports only. It is 1-based and must point at a `*` token in
  `subject`.
- `advertise`: Advertise the export.
- `allow_trace`: Valid only for service exports.
- `description`, `info_url`: Shared info metadata.

Stream export subjects are checked against other stream exports for containment; service export
subjects are checked against other service exports.

### Signing keys

`nats.signing_keys` serializes as an array. Each entry is either:

- A string account public key for a regular account signing key.
- A scoped signer object:
  - `kind`: Currently only `user_scope`.
  - `key`: Account public key used as the scoped signer.
  - `role`: Role name.
  - `template`: A `UserPermissionLimits` template.
  - `description`: Human-readable description.

Scoped signer templates default `subs`, `data`, and `payload` to `-1` when built with `NewUserScope`.

### Other account claims

- `nats.revocations`: Map of public key, or `*`, to Unix seconds. A claim issued at or before the
  stored timestamp is revoked. A newer revocation is kept if an older timestamp is later added.
- `nats.default_permissions`: Shared permission structure applied as account defaults by NATS
  servers.
- `nats.mappings`: Map from source subject to weighted target mappings. A target has `subject`,
  optional `weight`, and optional `cluster`. Weight `0` means `100`; totals must not exceed `100`,
  globally or per cluster.
- `nats.authorization.auth_users`: User public keys allowed to bypass external authorization callout,
  normally the auth service users. Presence enables external authorization.
- `nats.authorization.allowed_accounts`: Accounts the authorization service may bind authorized users
  to. It may be a list of account public keys or the single value `*`, but not `*` mixed with other
  values. It is invalid without `auth_users`.
- `nats.authorization.xkey`: Optional public curve key. If set, the server encrypts auth requests to
  the holder of the private key.
- `nats.trace.dest`: Subject for W3C trace-context messages. Required if `trace` exists, and it must
  be a publish subject without wildcards.
- `nats.trace.sampling`: `1..100`; `0` is normalized to `100` during validation.
- `nats.cluster_traffic`: Empty, `system`, or `owner`.
- `nats.description`: Free-form description, max 8192 bytes.
- `nats.info_url`: URL with scheme and hostname, max 8192 bytes.
- `nats.tags`, `nats.type`, `nats.version`: Shared generic fields.

## `nsc` CLI coverage

This section covers only:

- `nsc add account --help`
- `nsc add user --help`
- `nsc edit account --help`
- `nsc edit user --help`

Common flags:

| Claim  | Account flags                         | User flags                            |
| ------ | ------------------------------------- | ------------------------------------- |
| `sub`  | `add account --public-key`            | `add user --public-key`               |
| `name` | `add/edit account --name`             | `add/edit user --name`                |
| `exp`  | `add/edit account --expiry`           | `add/edit user --expiry`              |
| `nbf`  | `add/edit account --start`            | `add/edit user --start`               |
| `iss`  | global `--private-key` selects signer | global `--private-key` selects signer |

User claims set by these commands:

| Claim                           | `nsc` flag                                                    |
| ------------------------------- | ------------------------------------------------------------- |
| `nats.pub.allow`                | `--allow-pub`, `--allow-pubsub`; remove with `--rm`           |
| `nats.pub.deny`                 | `--deny-pub`, `--deny-pubsub`; remove with `--rm`             |
| `nats.sub.allow`                | `--allow-sub`, `--allow-pubsub`; remove with `--rm`           |
| `nats.sub.deny`                 | `--deny-sub`, `--deny-pubsub`; remove with `--rm`             |
| `nats.resp.max`                 | `--allow-pub-response[=n]`; remove with `--rm-response-perms` |
| `nats.resp.ttl`                 | `--response-ttl` with `--allow-pub-response`                  |
| `nats.bearer_token`             | `add/edit user --bearer`                                      |
| `nats.src`                      | `--source-network`; remove with `--rm-source-network`         |
| `nats.tags`                     | `--tag`; remove with `--rm-tag`                               |
| `nats.subs`                     | `edit user --subs`                                            |
| `nats.data`                     | `edit user --data`                                            |
| `nats.payload`                  | `edit user --payload`                                         |
| `nats.allowed_connection_types` | `edit user --conn-type`; remove with `--rm-conn-type`         |
| `nats.times`                    | `edit user --time`; remove with `--rm-time`                   |
| `nats.times_location`           | `edit user --locale`                                          |

The requested user commands do not expose `proxy_required` or `issuer_account`. `issuer_account` may
still be required when signing with an account signing key.

Account claims set by these commands:

| Claim                                | `nsc` flag                                                    |
| ------------------------------------ | ------------------------------------------------------------- |
| `nats.default_permissions.pub.allow` | `--allow-pub`, `--allow-pubsub`; remove with `--rm`           |
| `nats.default_permissions.pub.deny`  | `--deny-pub`, `--deny-pubsub`; remove with `--rm`             |
| `nats.default_permissions.sub.allow` | `--allow-sub`, `--allow-pubsub`; remove with `--rm`           |
| `nats.default_permissions.sub.deny`  | `--deny-sub`, `--deny-pubsub`; remove with `--rm`             |
| `nats.default_permissions.resp.max`  | `--allow-pub-response[=n]`; remove with `--rm-response-perms` |
| `nats.default_permissions.resp.ttl`  | `--response-ttl`                                              |
| `nats.limits.conn`                   | `edit account --conns`                                        |
| `nats.limits.leaf`                   | `edit account --leaf-conns`                                   |
| `nats.limits.imports`                | `edit account --imports`                                      |
| `nats.limits.exports`                | `edit account --exports`                                      |
| `nats.limits.subs`                   | `edit account --subscriptions`                                |
| `nats.limits.data`                   | `edit account --data`                                         |
| `nats.limits.payload`                | `edit account --payload`                                      |
| `nats.limits.wildcards`              | `edit account --wildcard-exports`                             |
| `nats.limits.disallow_bearer`        | `edit account --disallow-bearer`                              |
| `nats.limits.mem_storage`            | `edit account --js-mem-storage`                               |
| `nats.limits.disk_storage`           | `edit account --js-disk-storage`                              |
| `nats.limits.streams`                | `edit account --js-streams`                                   |
| `nats.limits.consumer`               | `edit account --js-consumer`                                  |
| `nats.limits.max_ack_pending`        | `edit account --js-max-ack-pending`                           |
| `nats.limits.mem_max_stream_bytes`   | `edit account --js-max-mem-stream`                            |
| `nats.limits.disk_max_stream_bytes`  | `edit account --js-max-disk-stream`                           |
| `nats.limits.max_bytes_required`     | `edit account --js-max-bytes-required`                        |
| `nats.limits.tiered_limits`          | `edit account --js-enable`, `--js-tier`, `--rm-js-tier`       |
| `nats.signing_keys`                  | `edit account --sk`, `--rm-sk`                                |
| `nats.trace.dest`                    | `edit account --trace-context-subject`                        |
| `nats.trace.sampling`                | `edit account --trace-context-sampling`                       |
| `nats.description`                   | `edit account --description`                                  |
| `nats.info_url`                      | `edit account --info-url`                                     |
| `nats.tags`                          | `edit account --tag`, `--rm-tag`                              |

`edit account --js-enable` enables JetStream for the selected tier, `--js-tier` chooses the
replication tier for the JS limit flags, and `--js-disable` removes all JetStream limits from the
account. The four requested account commands do not expose imports, exports, revocations, mappings,
external authorization, cluster traffic, or scoped signer templates.

## Basil API design notes

- Default constructors should emit explicit `-1` for unlimited NATS/account limits. Do not rely on
  absent numeric limits to mean unlimited.
- Make `issuer_account` explicit for user JWTs signed by signing keys; it is a server-significant
  relationship, not cosmetic metadata.
- Keep account limit inputs separate from JetStream enablement. `0` disables JetStream storage; `-1`
  enables it without a storage cap.
- Treat scoped signing keys as account signing keys plus a template, not as a user claim field. A
  user JWT signed by a scoped signer must carry no direct permissions or limits.
- Prefer `local_subject` over deprecated import `to`, and reject both together.
- Preserve duration units at the API boundary. JWT JSON stores Go durations as nanoseconds, while
  `nsc` accepts human strings such as `5s`.

## Where to go next

- [`sign-nats-jwt` command](/cli/command-reference/): sign a caller-supplied claim document from the CLI.
- [Rust client](/clients/rust/): `sign_nats_jwt` and `sign_nats_jwt_json` over these claims.
- [NATS integration](/clients/nats/): minting, signing, validation, and curve xkey boxes end to end.
- [RFC compatibility](/reference/rfc-compatibility/): the JOSE and signature standards these tokens implement.

[jwt-v2]: https://github.com/nats-io/jwt/tree/v2.8.2/v2
[account-claims]: https://github.com/nats-io/jwt/blob/v2.8.2/v2/account_claims.go
[user-claims]: https://github.com/nats-io/jwt/blob/v2.8.2/v2/user_claims.go
[types]: https://github.com/nats-io/jwt/blob/v2.8.2/v2/types.go
