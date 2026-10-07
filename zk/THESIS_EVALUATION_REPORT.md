# Evaluation of Bangla-First Aggregate ZK Model-Input Binding for zkRAG-BChain

**Evaluation date:** 15 September 2026  
**System:** zkRAG-BChain evidence layer, circuits `evidence-membership-16-v1` and `evidence-input-binding-16-v2`  
**Repository revision at evaluation:** `177bb02f96fe9acd30add1e5d09909a691a88487` with uncommitted ZK implementation files  
**Evaluation type:** implementation validation, adversarial mutation testing, local performance benchmarking, and security-boundary analysis

## Abstract

This report evaluates two compatible zero-knowledge layers integrated into a Bengali-first retrieval-augmented fact-checking system. Version 1 proves membership of one evidence leaf. Version 2 additionally captures the exact Groq request and response bodies, constructs prompts deterministically, commits the complete ordered evidence set and call transcript, and proves in one Groth16 proof that all active evidence leaves reconstruct the root bound to the prompt and request digests. Both circuits use Groth16 over BN254 and retain inference outside the circuit.

The original v1 benchmark remains a baseline: median proof generation was 2.811–2.825 s and verification was 0.724–0.732 s. The new 11,075-constraint aggregate circuit was evaluated after one warm-up and five measured runs for 1, 5, and 10 documents. Median v2 proof generation was 5.362 s, 5.329 s, and 5.407 s; verification was 3.015 s, 3.044 s, and 3.038 s; self-contained JSON packages were 14.7 kB, 18.8 kB, and 24.1 kB. Positive proofs and adversarial evidence, order, prompt, model, parameter, nonce, transcript, response-pairing, public-input, proof, and verification-key mutations were evaluated.

The results support the narrow claim that the system proves complete ordered evidence-root reconstruction and binds that root to independently reconstructed model-input commitments. The standalone verifier now recomputes canonical evidence, SHA-256 identifiers and limbs, Poseidon leaves/root, PromptBuild output, transport hashes, request/transcript/record commitments, public signals, and the Groth16 proof. This still does not prove source truth, retrieval completeness, remote provider execution, model reasoning, or verdict correctness. The phase-two setup has one repository contribution, so the implementation remains a research prototype rather than a production trust anchor.

**Keywords:** zero-knowledge proof, Groth16, Circom, Poseidon, Merkle tree, retrieval-augmented generation, Bengali fact checking, evidence provenance, zkRAG

## 1. Introduction

Retrieval-augmented fact checking combines external evidence retrieval with a language model that produces a verdict and explanation. Although this can improve grounding, an ordinary RAG response does not provide a cryptographic guarantee that a cited document belonged to the evidence set used by the system. Evidence may be changed after inference, omitted from an audit record, or confused with evidence collected in a later run.

The evaluated ZK layer addresses a narrow but useful integrity question:

> Given a public Merkle root, public evidence leaf, and public leaf position, can a prover demonstrate knowledge of a valid private Merkle authentication path?

Groth16 is a pairing-based succinct non-interactive argument system designed for small proofs and efficient verification [1]. Poseidon is used for Merkle hashing because it is designed to be efficient in arithmetic circuits [2]. Circom expresses the arithmetic constraints, while snarkjs provides witness generation, Groth16 proving, verification, and trusted-setup tooling [3], [4].

The design is deliberately Bangla-first. Bengali claims use at most 10 deduplicated documents in the model context, while English claims use at most 5. The Merkle tree has 16 leaves, leaving six padding positions at the planned Bengali maximum.

## 2. Research Questions

The evaluation is organized around six research questions.

- **RQ1 — Commitment correctness:** Does the same canonical evidence produce the same digest and Merkle root, and does changed evidence change the commitment?
- **RQ2 — Proof soundness in implementation:** Does a valid proof verify, and are modified evidence, roots, leaves, positions, paths, proof coordinates, and verification-key identities rejected?
- **RQ3 — Practical performance:** What are the commitment, tree-construction, proof-generation, verification, package-size, and observed parent-process memory costs for 1, 5, and 10 evidence documents?
- **RQ4 — Trust boundary:** Which properties are actually established by the proof, and which properties remain dependent on the application, retrieval service, model, trusted setup, and optional blockchain bridge?
- **RQ5 — Input binding:** Does one aggregate proof and standalone verification detect changes to any selected evidence item, its order, exact prompt, request configuration, or response chain?
- **RQ6 — Anchoring:** Does the optional local EVM bridge anchor the versioned record commitment without changing the legacy reputation integration or claiming success before transaction confirmation?

## 3. System Under Evaluation

### 3.1 Canonical evidence

For each model-used document, the application constructs a versioned object with:

- schema version;
- source type;
- normalized source URL or identifier;
- title;
- exact document content supplied to the model;
- publication date when available; and
- language.

String values are normalized to Unicode NFC. This is particularly relevant for Bengali text because visually equivalent Unicode sequences must not produce different evidence identifiers. The object is serialized using a string-only, fixed-key subset of the JSON Canonicalization Scheme. RFC 8785 defines deterministic JSON serialization for cryptographic operations [5]. The implementation avoids floating-point and arbitrary-key complications by restricting the evidence schema to strings and fixed ASCII property names.

URL normalization lowercases the scheme and hostname, removes fragments and common tracking parameters, removes default ports, sorts query parameters, applies IDNA hostname processing, and normalizes trailing slashes. Deduplication preserves the first occurrence of a normalized source, thereby retaining deterministic retrieval order.

### 3.2 Evidence identifiers and leaves

Let $E_i$ be the canonical UTF-8 byte representation of evidence document $i$. The system computes:

$$
d_i = \mathrm{SHA256}(E_i)
$$

SHA-256 is standardized by NIST in FIPS 180-4 [6]. The 256-bit digest is split without truncation:

$$
h_i = d_i[0:128], \qquad l_i = d_i[128:256]
$$

Both limbs are safely below the BN254 scalar-field modulus. The evidence identifier is the complete hexadecimal SHA-256 digest prefixed with `sha256:`. The Merkle leaf is:

$$
L_i = \operatorname{Poseidon}(D_{leaf}, h_i, l_i)
$$

where $D_{leaf}$ is the BN254 reduction of `SHA256("zkrag:leaf:v1")`.

### 3.3 Fixed-capacity Merkle commitment

The tree has 16 leaves and height 4. Unused positions contain a deterministic domain-separated padding leaf:

$$
L_{pad} = \operatorname{Poseidon}(D_{padding}, 0, 0)
$$

Internal nodes are computed as:

$$
N = \operatorname{Poseidon}(D_{node}, N_{left}, N_{right})
$$

Separate leaf, node, and padding domains prevent structural ambiguity between the three hash uses. Because tree capacity and height are fixed, every membership witness contains exactly four siblings.

### 3.4 Circuit statement

The Circom circuit exposes three public inputs:

- Merkle root $R$;
- selected evidence leaf $L_i$; and
- selected position $i$.

Its private witness is the four-element sibling path. Circom treats inputs omitted from the `public` list as private [3]. A four-bit decomposition constrains the position to the interval 0–15 and selects left/right ordering at each level. The circuit applies four domain-separated Poseidon parent hashes and asserts:

$$
R = \operatorname{MerkleRoot}(L_i, i, siblings_0,\ldots,siblings_3)
$$

The compiled circuit contains 2,433 constraints, 2,439 wires, 4 private inputs, and 3 public inputs.

### 3.5 Proof lifecycle

The initial claim record is saved as `committed_unproven`. A proof is generated only when the user selects an evidence identifier. Before proving, the Python application recomputes all canonical evidence digests, Poseidon leaves, and the root, rejecting a stale or modified record. The Node prover performs witness generation, Groth16 proving, and an internal verification. The Python layer then performs a second independent verification in another process before atomically saving a content-addressed package and changing only the selected item to `membership_verified`.

The original v1 package includes the proof, three public signals, structured public inputs, circuit version, evidence ID, claim ID, verification-key SHA-256, timestamp, and a package hash. Newly generated membership packages use `zkrag-membership-package-v2` and additionally disclose the selected canonical evidence and digest limbs, enabling independent evidence-to-leaf reconstruction. Verification remains compatible with stored `zkrag-proof-package-v1` packages.

### 3.6 Version 2 model-input-binding statement

Version 2 pre-allocates the claim ID and request nonce, then sends the exact bytes produced by one length-prefixed, NFC-normalized `PromptBuild` function to Groq. English records bind query generation, summarization, and judgment; Bangla records bind summarization and judgment. Each call retains Base64 request/response bodies, prompt and transport hashes, requested/returned model identifiers, generation parameters, and provider fingerprint. Authorization headers are excluded.

The aggregate circuit has 16 private leaf inputs and seven public inputs: evidence root, document count, two 128-bit prompt-hash limbs, two request-hash limbs, and a domain-separated Poseidon input-binding commitment. It constrains a prefix of at most 10 active leaves, zeroes inactive witness positions, inserts the standard padding leaf, reconstructs all four tree levels, and binds the root/count to the prompt and request limbs. The standalone verifier discloses and reconstructs the full ordered set; therefore the practical privacy benefit is succinct integrity verification, not evidence secrecy.

The combined verification chain is:

```text
canonical evidence -> SHA-256 ID/limbs -> Poseidon leaves -> ordered Merkle root
-> exact PromptBuild bytes -> prompt hash -> canonical request hash
-> raw response/transcript hashes -> aggregate Groth16 proof -> record commitment
```

## 4. Threat Model

### 4.1 Adversary capabilities

The evaluation assumes an adversary may:

- modify stored canonical evidence;
- substitute an evidence ID, leaf, position, or root;
- alter public signals;
- alter a Groth16 proof coordinate;
- use a different verification key;
- supply an incorrect private sibling path;
- replay or modify a portable package; or
- request a proof for evidence not associated with a claim.

### 4.2 Trusted components

The current prototype trusts:

- the retrieval code to collect the intended source material;
- the application to supply exactly the retained documents to the model;
- SHA-256 and the selected Poseidon/circomlib instantiation;
- the Circom compiler and snarkjs implementation;
- the correctness and secrecy assumptions of the Groth16 setup;
- the local claim store before commitment construction; and
- the verification key distributed with the proof package.

### 4.3 Explicitly out of scope

The proof does not establish:

- factual truth of a source;
- source authorship or publication-date authenticity;
- retrieval completeness, neutrality, or freshness;
- logical correctness of the language-model verdict;
- correctness of model weights or inference;
- inclusion of ZK commitments in the unchanged legacy source-reputation contract; or
- confidentiality of the public leaf, root, position, evidence ID, or package metadata.

## 5. Experimental Methodology

### 5.1 Environment

Measurements were taken on a single local machine after stopping the development backend and frontend to reduce workload interference.

| Property | Value |
|---|---|
| Operating system | macOS 26.0, build 25A354 |
| Architecture | x86_64 |
| Processor | Intel Core i5-1038NG7, 2.00 GHz |
| CPU topology | 4 physical cores, 8 logical cores |
| System memory | 16 GiB |
| Python | 3.12.1 |
| Node.js | 25.2.1 |
| npm | 11.6.2 |
| Circom artifact version | 2.2.3 |
| circomlib | 2.0.5 |
| circomlibjs | 0.1.7 |
| snarkjs | 0.7.6 |
| Proof system / curve | Groth16 / BN254 (`bn128` in snarkjs) |

Node.js 25 is accepted by the repository's current `>=20 <26` engine range, but Node.js 20 LTS remains the target deployment environment. This difference is a threat to exact performance reproducibility.

### 5.2 Benchmark protocol

Three evidence-set sizes were evaluated: 1, 5, and 10 Bengali documents for both the v1 membership baseline and v2 aggregate protocol. For each size, each benchmark performed:

1. one unrecorded warm-up run;
2. five recorded runs;
3. selection of the first evidence leaf for v1, or reconstruction of the complete active set for v2;
4. successful verification as a precondition for recording the run; and
5. reporting of the median, minimum, and maximum.

The v1 baseline measured:

- canonicalization, SHA-256 hashing, and digest splitting;
- fixed 16-leaf Poseidon tree construction;
- `generate_proof`, including application revalidation, tree/path recomputation, witness generation, Groth16 proof generation, and the prover's internal verification;
- an additional independent `verify_proof_package` execution;
- compact JSON proof-package size; and
- Python parent-process maximum resident set size.

The v2 benchmark separately measured evidence canonicalization, fixed-tree construction, prompt/request commitment construction, aggregate proof generation, full standalone package verification, self-contained package size, and Python parent-process maximum resident set size.

All latency values are wall-clock measurements obtained with `time.perf_counter()`.

### 5.3 Correctness and mutation protocol

The automated suite generated real commitments and Groth16 proofs, then evaluated positive and negative cases. Negative tests altered one security-relevant property at a time where practical. When a public input was deliberately changed, the corresponding public signal and package hash were recomputed so rejection depended on the cryptographic proof rather than only a stale package checksum.

### 5.4 Artifact and setup verification

The evaluation:

- checked SHA-256 checksums for the R1CS, WASM, final zkey, verification key, and manifest;
- recomputed the Powers of Tau BLAKE2b-512 digest;
- ran `snarkjs zkey verify` against the R1CS and Powers of Tau file;
- inspected circuit statistics with `snarkjs r1cs info`; and
- verified all stored live proof packages using only the standalone Node verifier and verification key.

## 6. Results

### 6.1 Functional correctness

All six original v1 automated test groups passed. The separate v2 suite also passed five groups covering bundle reconstruction, cross-language PromptBuild parity, raw Groq body capture without authorization-header persistence, adversarial transcript mutations, a real aggregate proof, atomic persistence, and the standalone verifier. Wall times vary substantially because both suites launch fresh Node/snarkjs processes.

| Evaluated property | Expected result | Observed result |
|---|---:|---:|
| Bengali context limit | first 10 documents retained | Pass |
| English context limit | first 5 documents retained | Pass |
| Retrieval ordering | selection preserves original order | Pass |
| Bengali composed/decomposed Unicode | identical canonical bytes and ID | Pass |
| URL normalization | stable canonical URL | Pass |
| Repeated commitment | identical root | Pass |
| Changed document content | different root | Pass |
| Empty retrieval | no commitment | Pass |
| 17 documents | capacity error | Pass |
| Real Groth16 proof | verifies | Pass |
| Content-addressed package | saved after verification | Pass |
| Standalone verification | verifies with package and vkey only | Pass |
| Status update | selected item only becomes verified | Pass |

These results answer RQ1 positively for the tested schema and application path: canonical commitments are deterministic, content-sensitive, and bounded by the language-specific selection limits.

### 6.2 Adversarial mutation results

| Mutation | Rejection layer | Observed result |
|---|---|---:|
| Canonical evidence content changed | application digest/ID revalidation | Rejected |
| Merkle root changed with self-consistent package metadata | Groth16 verification | Rejected |
| Public leaf changed with self-consistent package metadata | Groth16 verification | Rejected |
| Leaf position changed with self-consistent package metadata | Groth16 verification | Rejected |
| Groth16 proof coordinate changed | Groth16 verification | Rejected |
| Verification-key checksum changed | package verifier | Rejected |
| Private sibling path changed | witness constraint failure | Rejected |
| Evidence ID absent from claim | proof orchestration | Rejected |
| Record exceeds 16 leaves | commitment builder | Rejected |

The test therefore answers RQ2 positively within the stated circuit relation and tested implementation. It does not replace a formal proof of the circuit or an independent cryptographic audit.

### 6.3 Performance

#### 6.3.1 Median latency and size

| Documents | Canonicalization + SHA-256 (ms) | Poseidon tree (ms) | Proof generation (ms) | Independent verification (ms) | JSON package (bytes) |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.145 | 930.144 | 2,824.576 | 728.771 | 1,547 |
| 5 | 0.265 | 941.975 | 2,810.702 | 732.242 | 1,546 |
| 10 | 0.391 | 937.407 | 2,816.742 | 724.336 | 1,546 |

#### 6.3.2 Observed ranges

| Documents | Tree range (ms) | Proof range (ms) | Verification range (ms) | Package range (bytes) |
|---:|---:|---:|---:|---:|
| 1 | 918.166–952.187 | 2,791.879–2,897.639 | 720.347–754.808 | 1,546–1,548 |
| 5 | 934.295–966.237 | 2,805.189–2,825.030 | 720.452–733.833 | 1,543–1,547 |
| 10 | 930.271–986.229 | 2,806.536–3,206.022 | 720.378–742.742 | 1,544–1,546 |

#### 6.3.3 End-to-end ZK stage interpretation

The median initial commitment cost is the sum of canonicalization and the first tree construction:

- 1 document: 930.289 ms;
- 5 documents: 942.240 ms; and
- 10 documents: 937.797 ms.

The approximate on-demand proof endpoint's cryptographic compute path is the measured proof generation plus the required second independent verification:

- 1 document: 3,553.348 ms;
- 5 documents: 3,542.944 ms; and
- 10 documents: 3,541.078 ms.

Atomic persistence adds a small unmeasured filesystem cost. API transport, request queueing, RAG retrieval, and language-model inference are not included.

The difference between the 1-document and 10-document median proof-generation times is less than 0.3%. Verification and package size are similarly stable. This is expected because the circuit always hashes a four-level path and exposes the same three public inputs. The 10-document maximum of 3,206.022 ms indicates occasional runtime variation, but five observations are insufficient to characterize tail latency.

Canonicalization increases with document count, from 0.145 ms to 0.391 ms, but remains negligible compared with process startup and cryptographic operations. Poseidon tree construction remains near 0.94 s because it always pads to 16 leaves and launches a fresh Node.js process that initializes circomlibjs. The measurement therefore represents application-level latency, not just Poseidon primitive execution.

### 6.4 Memory result

The benchmark reported median parent-process RSS values of 15,286,272, 15,319,040, and 15,343,616 bytes for 1, 5, and 10 documents respectively (approximately 14.58–14.63 MiB). These values cover the Python parent only. Proof generation and Poseidon hashing execute in Node.js child processes, so this is not a valid measurement of total prover peak memory. The memory objective is therefore **not conclusively evaluated** by the present benchmark and must be remeasured with process-tree-aware tooling.

### 6.5 Artifact footprint and integrity

| Artifact | Size |
|---|---:|
| R1CS | 336,424 bytes |
| Witness-generation WASM | 1,848,117 bytes |
| Final proving key | 1,138,608 bytes |
| Verification key | 3,291 bytes |
| Powers of Tau file | 4,801,688 bytes |

All recorded artifact checksums passed. The verification key SHA-256 is:

`a1c8034647d368164e15a9a532843c320b9c26afeffd2b7decb7016911db7289`

The Powers of Tau BLAKE2b-512 digest was independently recomputed as:

`ded2694169b7b08e898f736d5de95af87c3f1a64594013351b1a796dbee393bd825f88f9468c84505ddd11eb0b1465ac9b43b9064aa8ec97f2b73e04758b8a4a`

`snarkjs zkey verify` reported matching circuit hashes, one phase-two contribution named `zkRAG-BChain build contribution v1`, and `ZKey Ok!`.

### 6.6 Live Bangla integration cases

Two stored claims produced through the real API and Bengali retrieval pipeline were inspected.

| Case | Retrieved/committed behavior | Final ZK status | Standalone proof |
|---|---|---|---:|
| `de4e431d-…` | 9 unique Bengali documents; all 9 committed | `membership_verified` | Pass |
| `c9b38448-…` | 26 unique Bengali documents retrieved; exactly 10 selected and committed | `membership_verified` | Pass |

Each record contains one verified selected item and retains the other items as unproven. Both explicitly contain `zk_onchain_anchor: false`. This provides integration evidence that the language limit, storage transition, proof endpoint, and standalone verifier operate together. With only two cases, it should be treated as a smoke test rather than a statistically representative RAG evaluation.

### 6.7 Aggregate input-binding evaluation

The v2 circuit compiled with Circom 2.2.3 to 11,075 constraints, 11,063 wires, 16 private inputs, and 7 public inputs. The checksum-pinned power-14 Hermez artifact matched iden3's published BLAKE2b-512 digest. A repository-specific phase-two contribution was created, `snarkjs zkey verify` returned `ZKey Ok!`, and the final verification-key SHA-256 is `93fb6922e3190d0de63d5b0dffe25a187f263e3e7183cad28195fe8a47c32e06`.

Median v2 measurements were:

| Documents | Evidence canonicalization (ms) | Poseidon tree (ms) | Prompt/request commitment (ms) | Aggregate proof (ms) | Full verification (ms) | Self-contained package (bytes) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.129 | 853.127 | 1.255 | 5,361.549 | 3,014.943 | 14,663 |
| 5 | 0.260 | 875.512 | 1.340 | 5,328.594 | 3,043.957 | 18,822 |
| 10 | 0.371 | 855.346 | 1.485 | 5,407.068 | 3,037.820 | 24,050 |

The circuit shape is fixed, but application-level timings vary because each operation launches Node, initializes Poseidon/snarkjs, reconstructs the disclosed bundle, and performs an internal plus independent proof verification. Package growth is expected because v2 intentionally contains every canonical evidence object, template, and exact model-call transcript. Parent Python RSS remained approximately 16.5–16.7 MB, but still excludes Node child processes and cannot be interpreted as full prover peak memory.

Automated v2 tests passed for deterministic Python/JavaScript PromptBuild parity, exact mocked Groq transport-body capture without stored authorization headers, a real aggregate Groth16 proof, standalone verification, atomic status persistence, and rejection of changed content, order, removals, fresh/history substitution, prompt bytes/templates, model IDs, generation parameters, request nonce, swapped response bodies, verification-key identity, named public inputs, public signals, and proof data. Contract tests passed for owner access control, anchoring, claim lookup, duplicate rejection, and unauthorized writes. A live local chain/bridge integration anchored a synthetic canonical record, returned and validated the matching versioned event, returned the original transaction/event idempotently on a duplicate request, and rejected a canonical-record mismatch with HTTP 422. The bridge's production dependency audit reported zero vulnerabilities; the pinned Hardhat 2 development toolchain retains audit findings and is not part of the deployed bridge runtime.

## 7. Discussion

### 7.1 RQ1: commitment correctness

The combination of Unicode normalization, fixed schema, deterministic serialization, SHA-256 evidence IDs, and ordered URL deduplication produced stable commitments in the evaluated cases. The model context and commitment are derived from the same limited document list, reducing the risk that UI-only sources or excluded retrieval results are silently committed. The live 26-to-10 case confirms the Bengali cap in an actual retrieval run.

The conclusion is limited to the implemented code path. An external retrieval provider may change result ordering between runs, so identical claims made at different times are not expected to have identical roots unless their selected evidence objects are identical.

### 7.2 RQ2: soundness and tamper resistance

The circuit correctly enforces position-aware membership across all four tree levels. A changed path cannot satisfy the root constraint, and changed public inputs invalidate an existing proof. Domain separation distinguishes evidence leaves, padding leaves, and internal nodes. Application-side revalidation also prevents proof generation from a stored record whose retained canonical evidence no longer matches its evidence ID or Merkle root.

Package hashing and verification-key hashing provide useful accidental-corruption and substitution checks. They are not signatures: anyone can recompute an unkeyed package hash. Authenticity ultimately comes from successful Groth16 verification against a trusted verification key. The local anchor can timestamp a record commitment, but production deployment still requires authenticated verification-key distribution and explicit key/circuit governance.

### 7.3 RQ3: performance and scalability

The v1 results show that the fixed-height membership circuit supports the 10-document Bengali context with effectively constant proof latency and compact package size: approximately 0.94 s for commitment construction and 3.54 s for on-demand proof generation plus independent verification. The stronger v2 aggregate path is costlier: the measured median aggregate proof plus full verification ranged from approximately 8.37 s to 8.45 s, with 14.7–24.1 kB self-contained packages. Both remain suitable for an explicit audit action in this prototype, but not for synchronously proving every claim during ordinary verdict generation.

The major optimization opportunity is architectural: keep a Node worker alive or move Poseidon and snarkjs calls into a persistent proof service. The v1 0.94 s and v2 0.85–0.88 s tree measurements are dominated by launching Node and initializing Poseidon, not by hashing 16 leaves. The v1 1.55 kB result and v2 14.7–24.1 kB results are JSON packages rather than minimal binary proof encodings; v2 grows because it intentionally discloses the full audit chain.

### 7.4 RQ4–RQ6: trust, input binding, and anchoring

The v2 package deliberately discloses the complete canonical evidence and raw model transcript. The verifier independently rebuilds every evidence identifier, digest limb, Poseidon leaf, tree node, prompt, request, response hash, transcript link, record commitment, and public signal before verifying Groth16. A valid package therefore supports the statement that the disclosed ordered evidence set generated the public root and the exact evidence-bearing prompt/request commitments.

The ZK circuit treats SHA-256 prompt and request digests as public limbs; correctness of their textual preimages is established by deterministic disclosure and verifier recomputation rather than SHA-256 constraints inside Circom. The Groth16 relation binds those digests to the reconstructed full-set root. This composition is appropriate for a public audit package but does not provide evidence confidentiality.

The local EVM contract stores the SHA-256 commitment of the versioned verification record plus a claim lookup hash and emits a versioned event. The bridge recomputes the record commitment and waits for a matching receipt. The application reports `zk_onchain_anchor: true` only after confirmation. This establishes timestamped tamper evidence for the committed record, not the factual truth of its content. If the local bridge is not configured or a transaction fails, the status remains explicitly non-anchored and retryable.

## 8. Trusted Setup Assessment

The v1 circuit uses a checksum-pinned power-12 prepared Powers of Tau artifact. The 11,075-constraint v2 circuit uses the checksum-pinned power-14 artifact supporting 16,384 constraints. Both repository-specific zkeys verify successfully. snarkjs documents that Groth16 requires a circuit-specific ceremony and that an uncontributed initial zkey must not be used in production [4].

The final zkey contains one locally generated phase-two contribution. This is stronger than an uncontributed zkey, but it is not a production multi-party ceremony. If that contributor's toxic waste were retained or its entropy generation compromised, soundness could be undermined. Before production use, the project should:

- run multiple independent phase-two contributions on separate systems;
- publish each contribution hash and attestation;
- verify the final transcript publicly;
- publish the final R1CS, zkey, verification key, circuit source, and checksums; and
- define a reproducible verification procedure pinned to Node.js 20 LTS and exact dependencies.

## 9. Blockchain and Provenance Assessment

Version 2 adds a separate local EVM anchor contract and Node bridge without modifying the legacy source-reputation registry. The full canonical verification record contains the claim ID, root, prompt/request/response/transcript hashes, model pipeline, circuit and verification-key versions, document count, verdict, and timestamp. To reduce on-chain storage, the contract stores its 32-byte record commitment, a claim lookup hash, timestamp, and submitter and emits a versioned event.

The bridge validates and recomputes the commitment before submission, handles existing identical records idempotently, and waits for confirmation. Status values distinguish `not_configured`, `failed_retryable`, and `anchored`; only the last sets `zk_onchain_anchor: true`. The contract test establishes local behavior, but no public testnet deployment or reorganization experiment was performed.

## 10. Threats to Validity

### 10.1 Internal validity

- Only five measured runs were collected per case; medians are useful descriptively, but no confidence intervals or tail percentiles are justified.
- The benchmark uses synthetic short Bengali documents and always proves the first leaf.
- The benchmark's `proof_ms` includes tree recomputation and internal verification; it is not a pure Groth16 proving microbenchmark.
- Python RSS excludes child-process memory.
- Process scheduling and filesystem cache state were not fully controlled.

### 10.2 External validity

- Results come from one Intel macOS laptop and may not generalize to Linux servers, ARM devices, browsers, or constrained deployments.
- Node.js 25 was used rather than the target Node.js 20 LTS.
- The tree is fixed at 16 leaves; a larger context requires a new versioned circuit and benchmark.
- The two live Bengali cases do not establish retrieval accuracy or language-model quality.

### 10.3 Construct validity

- “Proof size” measures a portable JSON package, not compressed group-element encoding.
- “Verification time” includes a fresh Node.js process and package-integrity checks.
- “ZK trust” could be misunderstood as proving factual truth; this evaluation measures only commitment, membership, and disclosed-input-binding properties.
- The aggregate relation binds public prompt/request digest limbs to the full evidence root, while SHA-256 preimage correctness and transcript linkage are checked by the disclosed package verifier outside Circom.

## 11. Overall Assessment

| Evaluation dimension | Assessment | Evidence |
|---|---|---|
| Deterministic evidence commitment | Strong prototype evidence | NFC, URL, determinism, and content-change tests pass |
| Position-aware Merkle membership | Strong prototype evidence | Real Groth16 proof and mutation rejection |
| Bangla-first context consistency | Strong prototype evidence | Unit tests plus 9- and 10-document live cases |
| Portable proof verification | Strong prototype evidence | CLI reconstructs evidence-to-leaf, prompts, transcript, public signals, and proof |
| Aggregate evidence-to-input binding | Strong prototype evidence | Real full-set proof plus adversarial mutation rejection |
| Selective privacy | Limited by design | v2 audit bundles disclose all evidence and model transport bodies |
| On-demand usability | Acceptable for explicit audit | Approximately 8.37–8.45 s median aggregate proof plus full verification |
| Memory characterization | Inconclusive | Node child-process RSS not measured |
| Trusted setup readiness | Research only | One phase-two contributor |
| Blockchain anchoring | Implemented locally | Owner-gated contract and confirmed-receipt bridge; no public deployment |
| Production security readiness | Not established | No formal verification, external audit, or production ceremony |

## 12. Recommendations

### 12.1 Thesis claim wording

State that the prototype proves the disclosed ordered evidence set reconstructs the committed root and binds it to independently rebuilt model-input commitments. Do not shorten this to “the ZK proof proves the verdict” or “the blockchain proves the news is true.”

### 12.2 Required before production deployment

1. Conduct and publish a multi-contributor circuit-specific phase-two ceremony.
2. Run an external circuit and protocol security review.
3. Pin and benchmark Node.js 20 LTS on the intended deployment OS.
4. Measure full process-tree peak memory and concurrency behavior.
5. Add rate limits, proof-queue limits, cancellation, and operational monitoring.
6. Authenticate verification-key distribution and define circuit-upgrade governance.

### 12.3 Performance improvements

1. Replace per-operation Node startup with a persistent local proof worker.
2. Separate pure proving, internal verification, package validation, and persistence timings.
3. Run at least 30 measured repetitions and report median, interquartile range, p95, and confidence intervals.
4. Benchmark multiple leaf positions and concurrent proof requests.
5. Compare Node.js 20 on macOS and Linux using identical artifacts.

### 12.4 Blockchain production work

1. Deploy and verify the anchor contract on the selected network.
2. Define signer rotation, upgrade, revocation, confirmation-depth, and reorganization rules.
3. Add authenticated bridge access, rate limits, monitoring, and transaction retry queues.
4. Publish the canonical record schema and a chain-independent event-verification tool.

## 13. Conclusion

The evaluated zkRAG-BChain layer now supports both selected-leaf membership and a real aggregate Groth16 proof over the full ordered evidence set. Deterministic Bengali-aware evidence normalization, exact PromptBuild bytes, raw Groq transport capture, request/response/transcript commitments, portable reconstruction, tamper rejection, atomic persistence, and optional local EVM anchoring operate as a versioned chain while retaining v1 verification.

The appropriate thesis conclusion remains narrow: the prototype provides cryptographic integrity linking disclosed RAG evidence to the exact recorded model-input construction and response transcript. It does not prove that sources are truthful, retrieval is complete, Groq executed the declared model internally, the model reasoned correctly, or the verdict is factually correct. The main remaining production gaps are a multi-contributor phase-two ceremony, independent protocol/circuit audit, process-tree memory and concurrency measurements, hardened bridge operations, and a public-network deployment policy.

## 14. Reproducibility Commands

Run from the repository root unless otherwise noted:

```bash
# Performance benchmark
python3 zk/benchmark.py
python3 zk/benchmark_input_binding.py

# Functional, mutation, real-proof, and standalone-verifier tests
cd code
python3 -m unittest -v test_zk_evidence.py
python3 -m unittest -v test_input_binding.py

# Circuit statistics
cd ..
zk/node_modules/.bin/snarkjs r1cs info zk/build/evidence_membership.r1cs
zk/node_modules/.bin/snarkjs r1cs info zk/build/input_binding_v2/evidence_input_binding.r1cs

# Artifact integrity
cd zk/build
shasum -a 256 -c SHA256SUMS
cd input_binding_v2
shasum -a 256 -c SHA256SUMS
cd ..

# Phase-two zkey verification
../node_modules/.bin/snarkjs zkey verify \
  evidence_membership.r1cs \
  ../ptau/powersOfTau28_hez_final_12.ptau \
  evidence_membership_final.zkey

../node_modules/.bin/snarkjs zkey verify \
  input_binding_v2/evidence_input_binding.r1cs \
  ../ptau/powersOfTau28_hez_final_14.ptau \
  input_binding_v2/evidence_input_binding_final.zkey

# Portable proof verification
cd ../..
node zk/scripts/verify.mjs \
  code/zk_proofs/<package-hash>.json \
  zk/build/verification_key.json

# Aggregate v2 package
node zk/scripts/verify.mjs \
  code/zk_proofs/<aggregate-package-hash>.json \
  zk/build/input_binding_v2/verification_key.json
```

The raw v1 and v2 benchmark data are stored in `zk/benchmark_results.json` and `zk/benchmark_results_v2.json`.

## References

[1] J. Groth, “On the Size of Pairing-Based Non-interactive Arguments,” *Advances in Cryptology—EUROCRYPT 2016*, pp. 305–326, 2016. DOI: [10.1007/978-3-662-49896-5_11](https://doi.org/10.1007/978-3-662-49896-5_11). Open-access manuscript: [IACR](https://iacr.org/archive/eurocrypt2016/96650272/96650272.pdf).

[2] L. Grassi, D. Khovratovich, C. Rechberger, A. Roy, and M. Schofnegger, “Poseidon: A New Hash Function for Zero-Knowledge Proof Systems,” *30th USENIX Security Symposium*, 2021. [IACR ePrint 2019/458](https://eprint.iacr.org/2019/458).

[3] iden3, “The Main Component,” *Circom 2 Documentation*. [https://docs.circom.io/circom-language/the-main-component/](https://docs.circom.io/circom-language/the-main-component/).

[4] iden3, “snarkjs: zkSNARK implementation in JavaScript and WASM,” GitHub repository and ceremony guide. [https://github.com/iden3/snarkjs](https://github.com/iden3/snarkjs).

[5] A. Rundgren, B. Jordan, and S. Erdtman, “JSON Canonicalization Scheme (JCS),” RFC 8785, June 2020. [https://www.rfc-editor.org/rfc/rfc8785](https://www.rfc-editor.org/rfc/rfc8785).

[6] National Institute of Standards and Technology, “Secure Hash Standard (SHS),” FIPS PUB 180-4, August 2015. DOI: [10.6028/NIST.FIPS.180-4](https://doi.org/10.6028/NIST.FIPS.180-4).
