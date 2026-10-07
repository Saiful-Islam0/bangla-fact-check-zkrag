# zkRAG evidence membership and model-input binding

This directory implements a versioned, fixed-height Groth16 Merkle membership proof. Each model-used evidence document is normalized to Unicode NFC and canonical JSON, hashed with SHA-256, split into two 128-bit limbs, and mapped to a BN254 Poseidon leaf. Up to 16 leaves are committed; unused positions use a domain-separated padding leaf.

Bangla requests supply and commit at most 10 documents. English requests supply and commit at most 5. The short `evidence_sources` snippets remain for display, while `zk_commitment.items[].canonical_evidence` retains the exact model-used document text.

Protocol v2 preserves that circuit and adds a full-set circuit and audit chain:

```text
retrieved evidence -> canonical evidence -> SHA-256 IDs -> Poseidon leaves
-> fixed 16-leaf root -> deterministic PromptBuild -> prompt hash
-> canonical request hash -> raw response/transcript hashes
-> aggregate Groth16 verification -> versioned record commitment -> optional EVM anchor
```

`PromptBuild` uses NFC, fixed ordering, explicit byte lengths, separate fresh/history sections, and versioned instructions. The exact output is the Groq user-message content. Raw HTTP request and response bodies are stored as Base64; authorization headers are never retained.

## Install and build

Requirements: Node.js 20 LTS, Circom 2.2.3, `curl`, and `openssl`.

```bash
cd zk
npm ci
./scripts/setup.sh
./scripts/setup_input_binding.sh
```

`setup.sh` checks iden3's published BLAKE2b-512 digest of the Hermez power-12 Powers of Tau file, compiles the 2,433-constraint circuit, creates a circuit-specific Groth16 phase-two contribution, verifies the resulting key, exports the verification key, and writes artifact SHA-256 checksums. Power 12 supports 4,096 constraints and is the smallest published ceremony artifact that safely fits this circuit. Set `ZKRAG_PHASE2_ENTROPY` to supply deployment entropy; otherwise a local random value is generated and discarded.

`setup_input_binding.sh` performs the equivalent process for the 11,075-constraint `evidence-input-binding-16-v2` circuit using the checksum-pinned Hermez power-14 artifact. It keeps all v1 keys untouched and writes v2 artifacts under `build/input_binding_v2/`.

For a production ceremony, repeat phase two with multiple independent contributors and publish the contribution transcript. A single local contribution is suitable for this implementation milestone but is not a multi-party production ceremony.

## API and standalone verification

Generate a proof after a fact check:

```text
POST /api/zk/proofs
{"claim_id":"...","evidence_id":"sha256:..."}
```

Generate one aggregate proof for every ordered model-used item:

```text
POST /api/zk/input-proofs
{"claim_id":"..."}
```

Verify a returned package through the API:

```text
POST /api/zk/verify
{"proof_package":{...}}
```

Or verify without Python, the database, or the proving key:

```bash
node zk/scripts/verify.mjs proof-package.json zk/build/verification_key.json
```

For v2, supply `zk/build/input_binding_v2/verification_key.json`. The CLI recomputes evidence canonical bytes, IDs, digest limbs, Poseidon leaves/root, every PromptBuild, raw-body hashes, request/transcript/record commitments, public signals, and finally the Groth16 proof. It needs no database or proving key.

## Security boundary

A v1 proof establishes that a disclosed evidence leaf and position belong to a root. A v2 proof establishes that the complete ordered leaf set creates the root and binds it to independently reconstructed prompt/request commitments. Neither proves source truth, retrieval completeness, metadata authenticity, provider-side execution of a declared model, correct reasoning, or a factually correct verdict. The optional local contract anchors only the finalized record commitment; it does not change those limitations. The legacy flagged-source blockchain payload remains unchanged.

## Version compatibility

- Existing `zkrag-proof-package-v1` records remain verifiable.
- Newly generated membership packages use `zkrag-membership-package-v2` and disclose the selected canonical evidence for portable evidence-to-leaf reconstruction.
- Aggregate packages use `zkrag-input-binding-package-v2` and `evidence-input-binding-16-v2`.
- Legacy claim records cannot retroactively produce an input-binding proof because their exact model transport bytes were not retained; the API returns `input_binding_unavailable_for_legacy_record`.

## Thesis evaluation

The complete evaluation methodology, benchmark interpretation, mutation-test matrix, trusted-setup assessment, limitations, and thesis-ready conclusions are documented in [THESIS_EVALUATION_REPORT.md](./THESIS_EVALUATION_REPORT.md). Raw v1 and v2 measurements and their precise stage definitions are stored in [benchmark_results.json](./benchmark_results.json) and [benchmark_results_v2.json](./benchmark_results_v2.json).
