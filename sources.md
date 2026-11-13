# Primary sources

Consulted while writing this pack (2026-11-13). The pack itself makes
no network calls; these sources were consulted at authoring time, and
the facts taken from each are listed so a reviewer can re-check them.

## Standards

- NIST FIPS 204, *Module-Lattice-Based Digital Signature Standard*
  (ML-DSA), final, 13 Aug 2024. ML-DSA derived from
  CRYSTALS-Dilithium; parameter sets ML-DSA-44/65/87 (categories
  2/3/5); public keys 1,312/1,952/2,592 bytes; private keys
  2,560/4,032/4,896 bytes; signatures 2,420/3,309/4,627 bytes
  (Tables 1–2); key generation from a 32-byte seed ξ
  (`ML-DSA.KeyGen_internal`, §6). Used for: ML-DSA sizes, the
  32-byte seed claim, and the general-purpose-default claim for
  ML-DSA-65.
- NIST FIPS 205, *Stateless Hash-Based Digital Signature Standard*
  (SLH-DSA), final, 13 Aug 2024. SLH-DSA derived from SPHINCS+;
  signatures 7,856–49,856 bytes; security rests only on hash-function
  properties. Used for: the SLH-DSA master-key note.
- RFC 8032 (IRTF, Jan 2017), *Edwards-Curve Digital Signature
  Algorithm (EdDSA)*: Ed25519 public keys 32 bytes, signatures
  64 bytes. Used for: the Ed25519 size comparison.
- OpenSSL 3.5 documentation, `EVP_PKEY-ML-DSA`: the ML-DSA seed
  parameter is 32 bytes; private keys may be stored in seed form.
  Corroborates the FIPS 204 §6 seed claim from an implementation.

## Quantum threat model

- P. W. Shor, "Polynomial-Time Algorithms for Prime Factorization and
  Discrete Logarithms on a Quantum Computer", *SIAM Journal on
  Computing* 26(5), 1997 (arXiv:quant-ph/9508027): factoring and
  discrete logarithms in polynomial time — breaks RSA, DH, ECDH, ECDSA
  and EdDSA.
- L. K. Grover, "A fast quantum mechanical algorithm for database
  search", 1996 (arXiv:quant-ph/9605043): unstructured search in ~√N
  steps — halves effective symmetric/hash strength.

## Upstream validator documentation

- xrpl.org, "Run xrpld as a Validator": `validator-keys create_keys`
  (offline), `validator-keys create_token`, `[validator_token]` in
  server configuration; generating more than one token from the same
  backup without updating it reuses the same `token_sequence` and the
  network ignores the later token.
- xrpl.org, `validation_create` method reference: the
  `validator-keys` tool is the recommended path for a robust
  validator; tokens are rotatable with an offline master key.

## Codebase facts (primary source: the pinned tree itself)

- postfiatd, commit `0085a1ff885d6a446369cf73a4430f75af22be55`
  ("Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9").
  All file:line citations in this pack come from this tree. The
  harness records the tree's `HEAD` commit in
  `results/simulation_summary.json`, so a wrong tree is detectable.
- Upstream comparison: postfiatd `doVoting` is byte-identical to
  upstream rippled 2.5.0 (commit
  `1e01cd34f7a216092ed779f291b43324c167167a`); the only divergence is
  the amendment-majority threshold, 67/100 in postfiatd
  (`include/xrpl/protocol/SystemParameters.h:85`) vs 80/100 upstream.
  Source: `~/workspace/postfiatd-amendment/RESEARCH.md`
  (amendment-vote regression-test research notes, Nov 2026).
- Sibling crypto-inventory pack (same pinned tree), published as
  https://github.com/araupooo/postfiat-ledger-crypto-inventory-quantum-exposure-audit
  — production validator signatures are Ed25519 + secp256k1/ECDSA;
  0 post-quantum mentions in the tree; TLS via pinned OpenSSL 1.1.1w;
  no key agreement in the ledger protocol itself. Cited, not
  re-derived.

## Live network snapshot

- PostFiat testnet explorer, https://explorer.testnet.postfiat.org/network/validators,
  fetched 2026-11-13 22:40 WIB: 66 validators listed, "UNL Count 25",
  ledger ~8,016,789, version 1.0.9 dominant. Used for: the default
  modelled set size N=66 and the N=25 sensitivity case. The meaning
  of "UNL Count" is unverified; see `assumptions.md` A2.
