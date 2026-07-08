+++
title = "Basil"
insert_anchor_links = "right"
+++

<div class="hero">
  <div class="tagline">Broker for Attestation, Secrets, Identity &amp; Leases</div>
  <p class="lede">
  <strong>Basil is a host-local secrets broker: your app never touches the key.</strong> The kernel
  attests who's calling, a default-deny policy decides, the key is used where it lives
  (OpenBao/Vault, KMS, or a sealed local store), and every operation is audited.</p>

</div>

![Basil request flow: a workload calls Basil over a local Unix socket; Basil attests the caller from the kernel, checks a default-deny policy, and brokers the operation against a Vault-compatible backend where keys stay in place, recording every decision to an audit log.](/images/architecture.png)

## Why Basil

You don't want secrets on disk. Each one risks being read, leaked, or backed up by accident, and
you can't easily log who used it or when. Basil removes that risk: with the default in-place backend,
neither your app nor Basil ever touches the secret bytes. When a service needs to sign or decrypt,
Basil asks the backend to do it and the key never leaves. When a service needs to prove who it is,
Basil mints a credential that expires in minutes. And before Basil does anything, it confirms, via
the operating-system kernel, exactly which process is asking.

The result: fewer secrets that can be stolen, short-lived ones where you can't avoid them, and a
clear, auditable answer to *"who's asking for what, and are they allowed?"*

## What's in the name

<div class="cards">
  <div class="card">
    <h3>🛡️ Attestation</h3>
    <p>Basil reads the caller's identity straight from the kernel (<code>SO_PEERCRED</code>: uid, gid, pid).
    No shared password, no bearer token to steal; the OS itself vouches for who's on the line.</p>
  </div>
  <div class="card">
    <h3>🔑 Secrets</h3>
    <p>Sign, verify, encrypt, decrypt, fetch, store, rotate. Keys stay in the vault and are used in
    place; Basil owns AEAD nonces, so a caller can't reuse one by accident.</p>
  </div>
  <div class="card">
    <h3>🪪 Identity</h3>
    <p>Workload identity via the open <a href="https://spiffe.io">SPIFFE</a> standard (X.509 and
    JWT SVIDs), so services prove who they are without credentials baked into images or config.</p>
  </div>
  <div class="card">
    <h3>⏳ Leases</h3>
    <p>When a raw secret won't do, Basil mints short-lived, narrowly-scoped credentials (NATS JWTs,
    SPIFFE tokens) that expire on their own. Authority for exactly as long as you need it.</p>
  </div>
</div>

## Start here

<div class="cards">
  <div class="card">
    <h3>New to Basil?</h3>
    <p><a href="/introduction/what-is-basil/">What is Basil</a> explains the model and the threat it
    addresses. <a href="/introduction/how-it-works/">How it works</a> walks the request path.</p>
  </div>
  <div class="card">
    <h3>Want to try it?</h3>
    <p>The <a href="/getting-started/quickstart/">Quickstart</a> boots a throwaway backend and drives
    the broker end to end in under five minutes.</p>
  </div>
  <div class="card">
    <h3>Running it?</h3>
    <p>The <a href="/configuration/overview/">Configuration</a> reference and
    <a href="/operations/rotating-keys/">Operations</a> guides are the operator runbook.</p>
  </div>
  <div class="card">
    <h3>Building against it?</h3>
    <p>See the <a href="/clients/rust/">Rust client</a>, <a href="/clients/go/">Go client</a>, and
    <a href="/clients/integration-patterns/">integration patterns</a>.</p>
  </div>
</div>

> Basil is under active development. Pages mark deliberate gaps as
> <span class="pill gap">roadmap</span>; shipped capability as <span class="pill impl">implemented</span>.
> See the [feature matrix](/reference/feature-matrix/) for the full breakdown.
