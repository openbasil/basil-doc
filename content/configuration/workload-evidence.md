+++
title = "Workload evidence & OCI signers"
weight = 35
+++

# Workload evidence & OCI signers

Schema 3 can bind authority to a pinned Linux process and, for containers, to the signer of the
exact image that is running. These checks prevent PID reuse, namespace confusion, mutable tags, and
an unrelated signature from satisfying a policy subject.

This page describes the protected evidence contracts and the `ociSignerPolicies` configuration.
The [policy reference](/configuration/policy/) covers domains, predicates, and grant evaluation.

{% note(title="Current provider availability") %}
The bounded process-pinning, domain-resolution, signer-policy, Cosign, and OCI digest-chain
foundations are implemented and tested. The current broker transport still supplies the
`SO_PEERCRED` host-process compatibility evidence. Realm listeners, live systemd/container runtime
providers, registry collection, and per-request transport revalidation remain
<span class="pill gap">roadmap</span>. Predicates that depend on those providers evaluate to
`unavailable`, cannot grant authority, and cannot fall back to a less-specific domain.
{% end %}

## A PID is pinned to one process lifetime

At connection admission, the process-evidence foundation combines kernel peer credentials with a
bounded `/proc/<pid>` observation:

- the peer PID, effective UID, and effective GID from `SO_PEERCRED`;
- field 22 from `/proc/<pid>/stat`, the process start time in clock ticks;
- the user, PID, mount, network, IPC, and UTS namespace inode numbers;
- normalized cgroup membership;
- the UID and GID maps for the caller's user namespace;
- real, effective, saved-set, and filesystem UID/GID slots, plus supplementary groups; and
- the SHA-256 digest and stable metadata identity of the opened `/proc/<pid>/exe` object.

The PID locates the process. The pinned start time prevents a later process that reuses that number
from inheriting its authority. Namespace and cgroup identities are also part of the connection pin;
movement after admission is an evidence mismatch.

Executable measurement follows the opened object. The diagnostic pathname has no authority. Basil
accepts a regular executable of at most 256 MiB, hashes its bytes, and compares device, inode, size,
ctime, and mtime metadata before and after the read. A concurrent replacement or mutation makes
the measurement unavailable.

## Account predicates use the caller's view

Linux user namespaces give one process two relevant account views. The host observes the peer UID
and GID through `SO_PEERCRED`; the workload sees the IDs mapped into its own user namespace.
`process.uid` and `process.gid` predicates use the caller-visible values.

Basil translates each host-visible credential through `/proc/<pid>/uid_map` or `gid_map`, then
checks that the result maps back to the same host value. Empty maps, too many ranges, overflow, or
an unmapped ID are unsupported. Overlapping, ambiguous, or non-round-tripping maps are mismatches.
Either outcome fails closed.

The aggregate predicates cover every primary slot:

| Predicate | Required caller-visible evidence |
| --- | --- |
| `process.uid` | Real, effective, saved-set, and filesystem UIDs all equal the configured value |
| `process.uid.real`, `.effective`, `.saved`, `.filesystem` | The named UID slot equals the configured value |
| `process.gid` | Real, effective, saved-set, and filesystem GIDs all equal the configured value |
| `process.gid.real`, `.effective`, `.saved`, `.filesystem` | The named primary GID slot equals the configured value |
| `process.gid.supplementary` | The configured GID is in the supplementary group set |

This caller-visible policy is portable across hosts with different subordinate-ID allocations while
the host-to-caller translation still checks the kernel observation.

## Point-of-use evidence is refreshed

The revalidation contract refreshes mutable credential slots, supplementary groups, systemd
correlation, and executable content before authorization. A legitimate `execve` may replace the
executable digest only after the new opened object passes the stable-read checks.

Revalidation also requires the following pinned facts to remain unchanged:

- process start time;
- all six namespace identities;
- normalized cgroup membership; and
- the caller ↔ host mapping of the peer UID and GID.

PID reuse, namespace/cgroup movement, and mapping conflict are typed mismatches. A malformed,
vanished, or concurrently changing procfs object is unavailable. A conclusive mapping or object
shape that Basil does not support is unsupported. None of these outcomes preserves authority from
the earlier observation.

## Domain resolution fails closed

Evidence providers report one of five states for each candidate domain:

| Provider state | Meaning |
| --- | --- |
| `verified` | Trusted evidence established this domain and its correlated identity |
| `absent` | Trusted evidence conclusively excluded this domain |
| `unsupported` | Isolation exists, but Basil has no supported provider for it |
| `unavailable` | A required kernel fact or configured provider could not be established safely |
| `mismatch` | Trusted evidence sources conflict |

Basil checks verified container evidence first, then a verified systemd service, then an
affirmatively ordinary host process. `unsupported`, `unavailable`, or `mismatch` at a more-specific
layer is terminal. Only `absent` allows resolution to continue to the next layer.

The stable external outcomes distinguish a permanent unsupported boundary from a retryable provider
failure:

- unsupported isolation maps to `WORKLOAD_DOMAIN_UNSUPPORTED`;
- temporary evidence or provider failure maps to `ATTESTATION_UNAVAILABLE`; and
- conflicting evidence maps to an attestation-mismatch denial.

## Declare named OCI signer policies

`ociSignerPolicies` is a top-level map in the schema-3 policy document. An `oci.signer` predicate
refers to one map key. Missing references, duplicate names, unknown fields, malformed repositories,
and mixed signer-mode fields reject the complete candidate policy.

### Pinned public key

Pinned-key mode scopes one protected public key to one repository:

```json
{
  "schema": "policy",
  "ociSignerPolicies": {
    "release-images": {
      "repository": "registry.example/team/app",
      "mode": "pinned-key",
      "publicKey": "/nix/store/4h3q-cosign.pub",
      "transparency": "required"
    }
  },
  "subjects": {
    "container.web": {
      "domain": "container",
      "match": { "oci.signer": "release-images" }
    }
  }
}
```

`publicKey` must be absolute and free of parent traversal. At verification time Basil checks that it
still names a regular file whose mode excludes group and world write bits.

`transparency` is mandatory in pinned-key mode:

| Value | Verification behavior |
| --- | --- |
| `required` | Cosign must verify transparency-log inclusion |
| `optional` | Policy deliberately permits verification with Cosign's transparency-log check disabled |

Use `required` when your deployment can meet the transparency dependency. Choosing `optional`
weakens the available auditability and must be an explicit policy decision.

### Exact keyless identity

Keyless mode binds one exact OIDC issuer and one exact certificate identity:

```json
{
  "schema": "policy",
  "ociSignerPolicies": {
    "ci-release": {
      "repository": "ghcr.io/example/app",
      "mode": "keyless",
      "issuer": "https://token.actions.githubusercontent.com",
      "identity": "https://github.com/example/app/.github/workflows/release.yml@refs/heads/main"
    }
  }
}
```

The issuer and identity are literal strings with no regular-expression interpretation. Keyless mode
has no `transparency` switch: Cosign's normal keyless verification, including its transparency
check, remains enabled. Basil also compares the issuer and subject reported in Cosign's bounded JSON
output with the configured strings.

Both modes require a lowercase repository without a tag or digest. A registry port is allowed in
the first path component. Scope is exact, so a signature for another repository cannot satisfy the
policy.

## Verification binds the complete running image chain

A successful Cosign exit is one input to the decision. Basil independently verifies the raw OCI
documents and the returned JSON before it produces `oci.signer` evidence:

1. The runtime-selected repository must equal the policy repository.
2. Every digest uses canonical lowercase `sha256:<64 hex>` syntax.
3. The supplied manifest bytes must hash to the registry-asserted manifest digest.
4. The manifest must be schema version 2, and its config digest must equal the running container's
   config digest.
5. When an index is present, its bytes must hash to the asserted index digest. Exactly one
   descriptor must match the selected OS, architecture, and optional variant, and that descriptor
   must name the selected manifest digest.
6. The signature subject is the index digest for an index signature or the selected manifest digest
   for a manifest signature.
7. Cosign output must repeat the expected repository/reference and signature-subject digest. A
   keyless result must also repeat the exact issuer and identity.

Raw index and manifest documents are limited to 4 MiB, an index to 256 descriptors, and Cosign JSON
to 16 records. Basil invokes Cosign through a protected absolute path with an empty environment, a
private mode-`0700` temporary directory, bounded output, and a deadline of at most five minutes.
Timeout or cancellation kills the complete verifier process group.

Registry collection, private-registry credentials, persistent evidence caching, and runtime-to-image
correlation are separate provider layers. Until those integrations supply a verified chain, an
`oci.signer` leaf remains unavailable in live authorization.

## Where to go next

- [The policy](/configuration/policy/): combine evidence into one unambiguous subject.
- [Threat model](/introduction/threat-model/): understand the host and process trust boundaries.
- [Feature matrix](/reference/feature-matrix/): distinguish implemented foundations from live providers.
- [Production hardening](/operations/production-hardening/): protect the broker and its local socket.
