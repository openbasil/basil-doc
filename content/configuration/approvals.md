+++
title = "Approvals & change control"
weight = 70
+++

# Approvals & change control

Basil does not have a built-in multi-party approval / dual-control gate
<span class="pill gap">roadmap</span>. What it gives you today are the primitives to build change
control around:

- **The `writable` cap.** A catalog key with `writable: false` rejects every broker-mediated write
  regardless of policy, a hard ceiling above the allow-list. Use it to make a key read/use-only until a
  deliberate config change flips it.
- **Permission separation.** Reading, writing, and rotating are distinct ops in distinct roles. Grant
  the narrowest that works; high-impact ops (`rotate`, `import`, `set`) live in `operator`, which you
  hand out sparingly.
- **Out-of-band provisioning.** Materialize-to-use private keys are provisioned outside the broker, so
  creating one is already a separate, reviewable act in your secret-provisioning pipeline.
- **Break-glass.** The BIP39 slot is your audited last resort for operations that should require a human
  and a stored phrase.

{% best() %}
Drive catalog and policy from version control (the NixOS config), so every authority change is a
reviewed, diffable commit. That's your approval gate today: the change to *who can do what* goes through
code review before it reaches the broker.
{% end %}

## Where to go next

- [The policy](/configuration/policy/): roles and least-privilege grants.
- [The catalog](/configuration/catalog/): the `writable` field.
- [Unlock & the sealed bundle](/configuration/unlock-and-bundle/): the BIP39 break-glass slot.
