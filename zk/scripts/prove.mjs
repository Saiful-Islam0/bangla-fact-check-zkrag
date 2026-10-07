#!/usr/bin/env node
import fs from "node:fs";
import * as snarkjs from "snarkjs";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => { data += chunk; });
    process.stdin.on("end", () => {
      try { resolve(JSON.parse(data || "{}")); } catch (error) { reject(error); }
    });
    process.stdin.on("error", reject);
  });
}

const [wasmPath, zkeyPath, verificationKeyPath] = process.argv.slice(2);
if (![wasmPath, zkeyPath, verificationKeyPath].every(Boolean)) {
  throw new Error("Usage: prove.mjs <circuit.wasm> <circuit.zkey> <verification_key.json>");
}
for (const path of [wasmPath, zkeyPath, verificationKeyPath]) {
  if (!fs.existsSync(path)) throw new Error(`Missing ZK artifact: ${path}`);
}

const input = await readStdin();
const { proof, publicSignals } = await snarkjs.groth16.fullProve(
  input,
  wasmPath,
  zkeyPath,
  undefined,
  undefined,
  { singleThread: true },
);
const verificationKey = JSON.parse(fs.readFileSync(verificationKeyPath, "utf8"));
const verified = await snarkjs.groth16.verify(verificationKey, publicSignals, proof);
if (!verified) throw new Error("Generated proof failed independent verification");
process.stdout.write(`${JSON.stringify({ proof, publicSignals, verified })}\n`);
process.exit(0);
