const fs = require("fs");
const path = require("path");
const express = require("express");
const cors = require("cors");
const { ethers } = require("ethers");
const { asBytes32, canonical, sha, validateVerificationRecord } = require("./protocol.cjs");

try {
  require("dotenv").config({
    path: process.env.DOTENV_CONFIG_PATH || path.resolve(__dirname, "../.env"),
    override: true,
  });
} catch (_) {}

const rpcUrl = process.env.ZKRAG_EVM_RPC_URL || "http://127.0.0.1:8545";
let contractAddress = process.env.ZKRAG_ANCHOR_CONTRACT_ADDRESS;
let privateKey = process.env.ZKRAG_ANCHOR_PRIVATE_KEY;

if (!contractAddress || !privateKey) {
  const envFilePath = process.env.DOTENV_CONFIG_PATH || path.resolve(__dirname, "../.env");
  if (fs.existsSync(envFilePath)) {
    const lines = fs.readFileSync(envFilePath, "utf8").split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx !== -1) {
        const k = trimmed.slice(0, idx).trim();
        const v = trimmed.slice(idx + 1).trim();
        if (k === "ZKRAG_ANCHOR_CONTRACT_ADDRESS" && (!contractAddress || contractAddress.trim() === "")) contractAddress = v;
        if (k === "ZKRAG_ANCHOR_PRIVATE_KEY" && (!privateKey || privateKey.trim() === "")) privateKey = v;
      }
    }
  }
}

if (!contractAddress || !privateKey) throw new Error("ZKRAG_ANCHOR_CONTRACT_ADDRESS and ZKRAG_ANCHOR_PRIVATE_KEY are required");
const artifactPath = process.env.ZKRAG_ANCHOR_ARTIFACT || "artifacts/contracts/VerificationRecordAnchor.sol/VerificationRecordAnchor.json";
const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
const provider = new ethers.JsonRpcProvider(rpcUrl);
const signer = new ethers.Wallet(privateKey, provider);
const contract = new ethers.Contract(contractAddress, artifact.abi, signer);
const app = express();
app.use(cors());
app.use(express.json({ limit: "25mb" }));

function validateAnchorEvent(anchorEvent, recordBytes, claimBytes) {
  if (!anchorEvent) throw new Error("Confirmed receipt is missing VerificationAnchored event");
  if (
    anchorEvent.args.recordCommitment.toLowerCase() !== recordBytes.toLowerCase()
    || anchorEvent.args.claimHash.toLowerCase() !== claimBytes.toLowerCase()
    || anchorEvent.args.schemaVersion !== 1n
  ) throw new Error("Confirmed anchor event does not match the submitted commitments");
  return {
    name: "VerificationAnchored",
    schema_version: String(anchorEvent.args.schemaVersion),
    verification_record_commitment: anchorEvent.args.recordCommitment.slice(2),
    claim_hash: anchorEvent.args.claimHash.slice(2),
    anchored_at: String(anchorEvent.args.anchoredAt),
    submitter: anchorEvent.args.submitter,
  };
}

app.get("/health", async (_req, res) => {
  try { res.json({ ok: true, chain_id: String((await provider.getNetwork()).chainId), contract_address: contractAddress }); }
  catch (error) { res.status(503).json({ ok: false, error: error.message }); }
});

app.post("/v1/anchors", async (req, res) => {
  try {
    const body = req.body || {};
    if (body.schema_version !== "zkrag-anchor-record-v1") throw new Error("Unsupported anchor schema version");
    const verificationRecord = body.verification_record || {};
    validateVerificationRecord(verificationRecord);
    const recomputed = sha(canonical(verificationRecord));
    if (recomputed !== body.record_commitment) throw new Error("Verification-record commitment mismatch");
    if (sha(Buffer.from(verificationRecord.claim_id, "utf8")) !== body.claim_hash) throw new Error("Claim hash does not match verification_record.claim_id");
    const recordBytes = asBytes32(body.record_commitment, "record_commitment");
    const claimBytes = asBytes32(body.claim_hash, "claim_hash");
    const existing = await contract.records(recordBytes);
    let receipt;
    let transactionHash = null;
    let blockNumber = null;
    let eventData = null;
    if (existing.anchoredAt === 0n) {
      const tx = await contract.anchor(recordBytes, claimBytes);
      receipt = await tx.wait(Number(process.env.ZKRAG_ANCHOR_CONFIRMATIONS || "1"));
      const anchorEvent = receipt.logs
        .map(log => {
          try { return contract.interface.parseLog(log); }
          catch (_error) { return null; }
        })
        .find(parsed => parsed && parsed.name === "VerificationAnchored");
      eventData = validateAnchorEvent(anchorEvent, recordBytes, claimBytes);
      transactionHash = receipt.hash;
      blockNumber = receipt.blockNumber;
    } else if (existing.claimHash.toLowerCase() !== claimBytes.toLowerCase()) {
      throw new Error("Existing anchor has a different claim hash");
    } else {
      const events = await contract.queryFilter(contract.filters.VerificationAnchored(recordBytes), 0, "latest");
      const existingEvent = events.at(-1);
      eventData = validateAnchorEvent(existingEvent, recordBytes, claimBytes);
      transactionHash = existingEvent.transactionHash;
      blockNumber = existingEvent.blockNumber;
    }
    const anchored = await contract.records(recordBytes);
    res.json({
      status: "anchored", record_commitment: body.record_commitment, claim_hash: body.claim_hash,
      chain_id: String((await provider.getNetwork()).chainId), contract_address: contractAddress,
      transaction_hash: transactionHash, block_number: blockNumber,
      anchored_at: String(anchored.anchoredAt), submitter: anchored.submitter,
      event: eventData,
    });
  } catch (error) { res.status(422).json({ status: "rejected", error: error.message }); }
});

app.get("/v1/anchors/:commitment", async (req, res) => {
  try {
    const digest = req.params.commitment.replace(/^0x/, "");
    const record = await contract.records(asBytes32(digest, "commitment"));
    if (record.anchoredAt === 0n) return res.status(404).json({ status: "not_found" });
    res.json({ status: "anchored", record_commitment: digest, claim_hash: record.claimHash.slice(2), anchored_at: String(record.anchoredAt), submitter: record.submitter });
  } catch (error) { res.status(422).json({ status: "rejected", error: error.message }); }
});

const bridgePort = Number(process.env.ZKRAG_ANCHOR_BRIDGE_PORT || "8787");
const bridgeHost = process.env.ZKRAG_ANCHOR_BRIDGE_HOST || "0.0.0.0";
app.listen(bridgePort, bridgeHost, () => {
  console.log(`zkRAG anchor bridge listening on http://${bridgeHost}:${bridgePort}`);
});
