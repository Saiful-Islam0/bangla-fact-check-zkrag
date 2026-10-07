const { expect } = require("chai");
const { canonical, sha, validateVerificationRecord } = require("../src/protocol.cjs");

function record() {
  return {
    claim_id: "claim-1", classification: "UNSURE", completed_at: "2026-09-15T00:00:00Z",
    document_count: "1", evidence_root: "123", model_pipeline: [{ stage: "summary" }],
    resolved_models: [{ stage: "summary", requested_model: "m", returned_model: "m" }],
    prompt_hash: "0".repeat(64), request_hash: "1".repeat(64), response_hash: "2".repeat(64),
    transcript_hash: "3".repeat(64), verification_key_sha256: "4".repeat(64), verdict_text: "test",
    versions: { protocol_version: "zkrag-input-binding-v2", circuit_version: "evidence-input-binding-16-v2" },
  };
}

describe("Bridge canonical protocol", function () {
  it("validates a v2 record and canonicalizes key order and Bengali NFC", function () {
    const value = record();
    validateVerificationRecord(value);
    const reordered = Object.fromEntries(Object.entries(value).reverse());
    expect(sha(canonical(value))).to.equal(sha(canonical(reordered)));
    expect(sha(canonical({ text: "ড়" }))).to.equal(sha(canonical({ text: "ড়".normalize("NFD") })));
  });

  it("rejects unsupported and incomplete records", function () {
    const wrongProtocol = record();
    wrongProtocol.versions.protocol_version = "other";
    expect(() => validateVerificationRecord(wrongProtocol)).to.throw("Unsupported verification-record protocol");
    const missingDigest = record();
    delete missingDigest.transcript_hash;
    expect(() => validateVerificationRecord(missingDigest)).to.throw("32-byte hex digest");
  });
});
