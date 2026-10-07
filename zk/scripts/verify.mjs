#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import * as snarkjs from "snarkjs";
import { buildPoseidon } from "circomlibjs";

const FIELD_MODULUS = BigInt("21888242871839275222246405745257275088548364400416034343698204186575808495617");
const TRANSCRIPT_DOMAIN = Buffer.from("zkrag:transcript:v2\0", "utf8");
const TEMPLATE_REGISTRY_VERSION = "zkrag-template-registry-v2";
const TEMPLATES = {
  "query-en-v2": "Generate exactly three newline-separated search queries for fact-checking the claim. Cover the main event, named people or organisations, and relevant place or time. Return queries only.",
  "summary-en-v2": "Extract concise factual evidence relevant to the claim. Use only the supplied fresh evidence, identify support or contradiction, and retain source/date references when available.",
  "summary-bn-v2": "সরবরাহ করা নতুন প্রমাণ থেকেই দাবির সঙ্গে সম্পর্কিত ঘটনামূলক তথ্য সংক্ষেপে বের করো। সম্ভব হলে উৎস ও তারিখ উল্লেখ করো।",
  "judge-en-v2": "Classify the claim using only the supplied evidence summary. Respond exactly with Classification: REAL or FAKE or MISINFORMATION or UNSURE, Credibility Score: 0-100 (or N/A for UNSURE), and Explanation.",
  "judge-bn-v2": "শুধু সরবরাহ করা প্রমাণের সারসংক্ষেপ ব্যবহার করে দাবিকে REAL, FAKE, MISINFORMATION অথবা UNSURE হিসেবে শ্রেণিবদ্ধ করো। ঠিক এই বিন্যাসে উত্তর দাও: Classification, Credibility Score, Explanation। ব্যাখ্যা বাংলায় লিখবে।",
};

function usage() { return "Usage: verify.mjs <proof-package.json> <verification_key.json> OR pipe a package to verify.mjs <verification_key.json>"; }
async function readStdin() { let data = ""; for await (const chunk of process.stdin) data += chunk; return JSON.parse(data || "{}"); }
function normalized(value) {
  if (typeof value === "string") return value.normalize("NFC");
  if (Array.isArray(value)) return value.map(normalized);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map(key => [key, normalized(value[key])]));
  return value;
}
function canonical(value) { return Buffer.from(JSON.stringify(normalized(value)), "utf8"); }
function sha(data) { return crypto.createHash("sha256").update(data).digest("hex"); }
function domain(label) { return BigInt(`0x${sha(Buffer.from(label, "utf8"))}`) % FIELD_MODULUS; }
function field(name, value) {
  const body = Buffer.isBuffer(value) ? value : Buffer.from(value, "utf8");
  return Buffer.concat([Buffer.from(`${name}:${body.length}\n`, "ascii"), body, Buffer.from("\n")]);
}
function promptBuild({ stage, claim, evidence, history, template, upstream = "" }) {
  if (!TEMPLATES[template]) throw new Error(`Unsupported template ${template}`);
  const fresh = evidence.map(canonical);
  const historical = history.map(canonical);
  const parts = [
    Buffer.from("ZKRAG-PROMPT-BUILD/2\n"), field("prompt_build_version", "zkrag-prompt-build-v2"),
    field("stage", stage), field("template_version", template), field("instruction", TEMPLATES[template]),
    field("normalized_claim", claim.normalize("NFC")), field("fresh_evidence_count", String(fresh.length)),
  ];
  fresh.forEach((item, i) => parts.push(field(`fresh_evidence_${i}`, item)));
  parts.push(field("historical_context_count", String(historical.length)));
  historical.forEach((item, i) => parts.push(field(`historical_context_${i}`, item)));
  parts.push(field("upstream_output", upstream.normalize("NFC")));
  return Buffer.concat(parts);
}
function without(object, key) { return Object.fromEntries(Object.entries(object).filter(([name]) => name !== key)); }
function expectedGeneration(stage) { return { temperature: "0", top_p: "1", stream: "false", max_completion_tokens: stage === "query" ? "256" : "1024" }; }
function transcriptHash(calls) {
  let cursor = crypto.createHash("sha256").update(TRANSCRIPT_DOMAIN).digest();
  calls.forEach((call, position) => {
    const link = { call_request_body_hash: call.call_request_body_hash, call_response_hash: call.call_response_hash,
      position: String(position), previous: cursor.toString("hex"), stage: call.stage, stage_prompt_hash: call.stage_prompt_hash };
    cursor = crypto.createHash("sha256").update(TRANSCRIPT_DOMAIN).update(canonical(link)).digest();
  });
  return cursor.toString("hex");
}
function limbs(hex) {
  const data = Buffer.from(hex.replace(/^sha256:/, ""), "hex");
  if (data.length !== 32) throw new Error("Invalid SHA-256 digest");
  return [BigInt(`0x${data.subarray(0, 16).toString("hex")}`).toString(), BigInt(`0x${data.subarray(16).toString("hex")}`).toString()];
}
function asString(poseidon, value) { return poseidon.F.toObject(value).toString(); }

async function reconstructEvidence(evidence) {
  const poseidon = await buildPoseidon();
  const leafDomain = domain("zkrag:leaf:v1");
  const nodeDomain = domain("zkrag:node:v1");
  const paddingDomain = domain("zkrag:padding:v1");
  const leaves = evidence.map(item => {
    const digest = sha(canonical(item));
    const [hi, lo] = limbs(digest);
    return { digest, hi, lo, leaf: asString(poseidon, poseidon([leafDomain, BigInt(hi), BigInt(lo)])) };
  });
  const padding = asString(poseidon, poseidon([paddingDomain, 0n, 0n]));
  let level = leaves.map(item => item.leaf);
  while (level.length < 16) level.push(padding);
  while (level.length > 1) {
    const next = [];
    for (let i = 0; i < level.length; i += 2) next.push(asString(poseidon, poseidon([nodeDomain, BigInt(level[i]), BigInt(level[i + 1])])));
    level = next;
  }
  return { poseidon, leaves, root: level[0] };
}
async function verifyMembershipData(pkg) {
  if (pkg.package_version !== "zkrag-membership-package-v2") return true;
  const rebuilt = await reconstructEvidence([pkg.canonical_evidence]);
  const item = rebuilt.leaves[0];
  return pkg.evidence_id === `sha256:${item.digest}` && pkg.evidence_digest?.sha256 === item.digest &&
    String(pkg.evidence_digest?.hi) === item.hi && String(pkg.evidence_digest?.lo) === item.lo && String(pkg.public_inputs?.leaf) === item.leaf;
}
async function verifyInputPackage(pkg, verificationKey, verificationKeyBytes) {
  const checks = { package: false, evidence: false, prompt: false, request: false, transcript: false, record: false, public_inputs: false, proof: false };
  if (pkg.package_version !== "zkrag-input-binding-package-v2" || pkg.circuit_version !== "evidence-input-binding-16-v2") return { verified: false, checks };
  if (sha(canonical(without(pkg, "package_hash"))) !== pkg.package_hash || sha(verificationKeyBytes) !== pkg.verification_key_sha256) return { verified: false, checks };
  checks.package = true;
  const bundle = pkg.audit_bundle || {};
  if (sha(canonical(without(bundle, "audit_bundle_hash"))) !== bundle.audit_bundle_hash) return { verified: false, checks };
  if (bundle.verification_record?.verification_key_sha256 !== pkg.verification_key_sha256) return { verified: false, checks };
  if (!["bn", "en"].includes(bundle.language) || JSON.stringify(bundle.historical_context) !== "[]") return { verified: false, checks };
  const evidence = bundle.fresh_evidence || [];
  const languageLimit = bundle.language === "bn" ? 10 : 5;
  const evidenceKeys = ["content", "language", "publication_date", "schema_version", "source", "source_type", "title"];
  if (!evidence.length || evidence.length > languageLimit || evidence.some(item =>
    !item || typeof item !== "object" || Array.isArray(item) ||
    JSON.stringify(Object.keys(item).sort()) !== JSON.stringify(evidenceKeys) ||
    Object.values(item).some(value => typeof value !== "string") ||
    item.schema_version !== "zkrag-evidence-v1" || item.language !== bundle.language
  )) return { verified: false, checks };
  const rebuilt = await reconstructEvidence(evidence);
  if (rebuilt.root !== String(bundle.request_object?.evidence_root)) return { verified: false, checks };
  checks.evidence = true;
  const expectedStages = bundle.language === "bn" ? ["summary", "judge"] : ["query", "summary", "judge"];
  const expectedTemplates = expectedStages.map(stage => `${stage}-${bundle.language === "bn" ? "bn" : "en"}-v2`);
  if (JSON.stringify((bundle.calls || []).map(call => call.stage)) !== JSON.stringify(expectedStages) ||
      JSON.stringify((bundle.calls || []).map(call => call.template_version)) !== JSON.stringify(expectedTemplates) ||
      bundle.template_registry_version !== TEMPLATE_REGISTRY_VERSION ||
      !canonical(bundle.templates || {}).equals(canonical(Object.fromEntries(expectedTemplates.map(version => [version, TEMPLATES[version]]))))) {
    return { verified: false, checks };
  }
  let summary = "";
  for (const call of bundle.calls || []) {
    const expected = promptBuild({ stage: call.stage, claim: bundle.normalized_claim,
      evidence: call.stage === "summary" ? evidence : [], history: bundle.historical_context || [],
      template: call.template_version, upstream: call.stage === "judge" ? summary : "" });
    const prompt = Buffer.from(call.prompt_bytes_b64, "base64");
    const request = Buffer.from(call.request_body_b64, "base64");
    const response = Buffer.from(call.response_body_b64, "base64");
    if (!expected.equals(prompt) || sha(prompt) !== call.stage_prompt_hash || sha(request) !== call.call_request_body_hash || sha(response) !== call.call_response_hash) return { verified: false, checks };
    let requestJson, responseJson;
    try { requestJson = JSON.parse(request); responseJson = JSON.parse(response); } catch { return { verified: false, checks }; }
    const sent = Buffer.from(requestJson.messages?.at(-1)?.content || "", "utf8");
    const assistant = (responseJson.choices?.[0]?.message?.content || "").normalize("NFC");
    const expectedParams = expectedGeneration(call.stage);
    const actualParams = Object.fromEntries(Object.keys(expectedParams).map(key => [key, String(requestJson[key]).toLowerCase()]));
    if (!sent.equals(expected) || requestJson.model !== call.requested_model || assistant !== call.assistant_content ||
        !canonical(call.generation_parameters).equals(canonical(expectedParams)) || !canonical(actualParams).equals(canonical(expectedParams)) ||
        String(responseJson.model || "") !== String(call.returned_model || "") || String(responseJson.system_fingerprint || "") !== String(call.system_fingerprint || "")) return { verified: false, checks };
    if (call.stage === "summary") summary = assistant;
  }
  checks.prompt = true;
  const pipeline = bundle.request_object?.model_pipeline || [];
  const versions = bundle.request_object?.versions || {};
  const versionsValid = canonical(versions).equals(canonical(bundle.versions || {})) &&
    versions.protocol_version === "zkrag-input-binding-v2" &&
    versions.prompt_build_version === "zkrag-prompt-build-v2" &&
    versions.template_registry_version === TEMPLATE_REGISTRY_VERSION &&
    versions.model_pipeline_version === "groq-evidence-pipeline-v2" &&
    versions.circuit_version === "evidence-input-binding-16-v2";
  const pipelineValid = pipeline.length === (bundle.calls || []).length && pipeline.every((declared, position) => {
    const call = bundle.calls[position];
    return declared.position === String(position) && declared.stage === call.stage && declared.model_id === call.requested_model && canonical(declared.generation_parameters).equals(canonical(call.generation_parameters));
  });
  const resolvedModels = (bundle.calls || []).map(call => ({ stage: call.stage, requested_model: call.requested_model,
    returned_model: call.returned_model || "", system_fingerprint: call.system_fingerprint || "" }));
  const resolvedModelsValid = canonical(bundle.request_object?.resolved_models || {}).equals(canonical(resolvedModels));
  checks.request = sha(canonical(bundle.request_object)) === bundle.request_hash && bundle.request_object?.prompt_hash === bundle.prompt_hash && bundle.request_object?.document_count === String(evidence.length) && pipelineValid && resolvedModelsValid && versionsValid;
  checks.transcript = transcriptHash(bundle.calls || []) === bundle.transcript_hash && bundle.response_hash === bundle.calls?.at(-1)?.call_response_hash;
  checks.record = sha(canonical(bundle.verification_record)) === bundle.verification_record_commitment && bundle.verification_record?.request_hash === bundle.request_hash && bundle.verification_record?.response_hash === bundle.response_hash && bundle.verification_record?.transcript_hash === bundle.transcript_hash && bundle.verification_record?.verdict_text === bundle.verdict_text && canonical(bundle.verification_record?.versions || {}).equals(canonical(versions)) && canonical(bundle.verification_record?.resolved_models || {}).equals(canonical(resolvedModels));
  if (!checks.request || !checks.transcript || !checks.record) return { verified: false, checks };
  const [promptHi, promptLo] = limbs(bundle.prompt_hash);
  const [requestHi, requestLo] = limbs(bundle.request_hash);
  const bindDomain = domain("zkrag:input-binding:v2");
  const first = asString(rebuilt.poseidon, rebuilt.poseidon([bindDomain, BigInt(rebuilt.root), BigInt(evidence.length)]));
  const second = asString(rebuilt.poseidon, rebuilt.poseidon([BigInt(first), BigInt(promptHi), BigInt(promptLo)]));
  const binding = asString(rebuilt.poseidon, rebuilt.poseidon([BigInt(second), BigInt(requestHi), BigInt(requestLo)]));
  const expectedSignals = [rebuilt.root, String(evidence.length), promptHi, promptLo, requestHi, requestLo, binding];
  const expectedInputs = { root: rebuilt.root, document_count: evidence.length, prompt_hash_hi: promptHi,
    prompt_hash_lo: promptLo, request_hash_hi: requestHi, request_hash_lo: requestLo, input_binding: binding };
  checks.public_inputs = JSON.stringify(expectedSignals) === JSON.stringify(pkg.public_signals) &&
    canonical(pkg.public_inputs || {}).equals(canonical(expectedInputs));
  if (!checks.public_inputs) return { verified: false, checks };
  checks.proof = await snarkjs.groth16.verify(verificationKey, pkg.public_signals, pkg.proof);
  return { verified: Object.values(checks).every(Boolean), checks };
}

let packageData;
let verificationKeyPath;
if (process.argv.length === 4) { packageData = JSON.parse(fs.readFileSync(process.argv[2], "utf8")); verificationKeyPath = process.argv[3]; }
else if (process.argv.length === 3) { packageData = await readStdin(); verificationKeyPath = process.argv[2]; }
else throw new Error(usage());

const verificationKeyBytes = fs.readFileSync(verificationKeyPath);
const verificationKey = JSON.parse(verificationKeyBytes);
let result;
if (packageData.package_version === "zkrag-input-binding-package-v2") result = await verifyInputPackage(packageData, verificationKey, verificationKeyBytes);
else {
  const publicSignals = packageData.public_signals ?? packageData.publicSignals;
  const integrity = sha(canonical(without(packageData, "package_hash"))) === packageData.package_hash && sha(verificationKeyBytes) === packageData.verification_key_sha256;
  const portable = integrity && await verifyMembershipData(packageData);
  const publicInputs = packageData.public_inputs || {};
  const signalsMatch = JSON.stringify(publicSignals) === JSON.stringify([String(publicInputs.root), String(publicInputs.leaf), String(publicInputs.position)]);
  const proof = Boolean(portable && signalsMatch && packageData.proof && Array.isArray(publicSignals) && await snarkjs.groth16.verify(verificationKey, publicSignals, packageData.proof));
  result = { verified: proof, checks: { package_integrity: integrity, evidence_to_leaf: portable, public_inputs: signalsMatch, membership_proof: proof } };
}
process.stdout.write(`${JSON.stringify(result)}\n`);
// A cryptographic rejection is a valid verifier result, not a process error.
// Syntax, file, and runtime failures still throw and exit non-zero.
process.exit(0);
