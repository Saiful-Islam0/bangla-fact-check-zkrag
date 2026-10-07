const crypto = require("crypto");

function normalized(value) {
  if (typeof value === "string") return value.normalize("NFC");
  if (Array.isArray(value)) return value.map(normalized);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, normalized(value[key])]));
  }
  return value;
}

// Verification records intentionally use strings, arrays, objects, and booleans
// only, making this sorted UTF-8 encoding an RFC 8785-compatible subset.
function canonical(value) { return Buffer.from(JSON.stringify(normalized(value)), "utf8"); }
function sha(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
function asBytes32(hex, label) {
  if (!/^[0-9a-f]{64}$/i.test(hex || "")) throw new Error(`${label} must be a 32-byte hex digest`);
  return `0x${hex}`;
}

function validateVerificationRecord(record) {
  if (!record || typeof record !== "object" || Array.isArray(record)) throw new Error("verification_record must be an object");
  const requiredDigests = ["prompt_hash", "request_hash", "response_hash", "transcript_hash", "verification_key_sha256"];
  for (const field of requiredDigests) asBytes32(record[field], `verification_record.${field}`);
  if (!/^[0-9]+$/.test(record.evidence_root || "")) throw new Error("verification_record.evidence_root must be a decimal field value");
  if (!/^[1-9][0-9]*$/.test(record.document_count || "")) throw new Error("verification_record.document_count must be positive");
  if (!record.claim_id || typeof record.claim_id !== "string") throw new Error("verification_record.claim_id is required");
  if (record.versions?.protocol_version !== "zkrag-input-binding-v2") throw new Error("Unsupported verification-record protocol");
  if (record.versions?.circuit_version !== "evidence-input-binding-16-v2") throw new Error("Unsupported verification-record circuit");
  if (!Array.isArray(record.model_pipeline) || !record.model_pipeline.length || !Array.isArray(record.resolved_models) || !record.resolved_models.length) {
    throw new Error("Model provenance is required");
  }
  if (typeof record.classification !== "string" || typeof record.verdict_text !== "string" || typeof record.completed_at !== "string") {
    throw new Error("Verdict and completion metadata are required");
  }
}

module.exports = { asBytes32, canonical, normalized, sha, validateVerificationRecord };
