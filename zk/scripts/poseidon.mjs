#!/usr/bin/env node
import crypto from "node:crypto";
import { buildPoseidon } from "circomlibjs";

const FIELD_MODULUS = BigInt("21888242871839275222246405745257275088548364400416034343698204186575808495617");
const TREE_CAPACITY = 16;

function domain(label) {
  return BigInt(`0x${crypto.createHash("sha256").update(label, "utf8").digest("hex")}`) % FIELD_MODULUS;
}

const LEAF_DOMAIN = domain("zkrag:leaf:v1");
const NODE_DOMAIN = domain("zkrag:node:v1");
const PADDING_DOMAIN = domain("zkrag:padding:v1");
const INPUT_BINDING_DOMAIN = domain("zkrag:input-binding:v2");

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

function asString(poseidon, value) {
  return poseidon.F.toObject(value).toString();
}

const request = await readStdin();
const poseidon = await buildPoseidon();

const hashLeaf = ({ hi, lo }) => asString(poseidon, poseidon([LEAF_DOMAIN, BigInt(hi), BigInt(lo)]));
const hashNode = (left, right) => asString(poseidon, poseidon([NODE_DOMAIN, BigInt(left), BigInt(right)]));
const paddingLeaf = asString(poseidon, poseidon([PADDING_DOMAIN, 0n, 0n]));

let leaves;
if (Array.isArray(request.digestParts)) {
  leaves = request.digestParts.map(hashLeaf);
} else if (Array.isArray(request.leaves)) {
  leaves = request.leaves.map(value => BigInt(value).toString());
} else {
  throw new Error("Expected digestParts or leaves array");
}

if (leaves.length > TREE_CAPACITY) {
  throw new Error(`Evidence count ${leaves.length} exceeds tree capacity ${TREE_CAPACITY}`);
}

const documentCount = leaves.length;
while (leaves.length < TREE_CAPACITY) leaves.push(paddingLeaf);

const levels = [leaves];
while (levels.at(-1).length > 1) {
  const previous = levels.at(-1);
  const next = [];
  for (let i = 0; i < previous.length; i += 2) next.push(hashNode(previous[i], previous[i + 1]));
  levels.push(next);
}

const result = {
  root: levels.at(-1)[0],
  leaves: leaves.slice(0, documentCount),
  padding_leaf: paddingLeaf,
  capacity: TREE_CAPACITY,
  height: 4,
  domains: {
    leaf: LEAF_DOMAIN.toString(),
    node: NODE_DOMAIN.toString(),
    padding: PADDING_DOMAIN.toString()
  }
};

if (request.promptHashHi !== undefined && request.promptHashLo !== undefined &&
    request.requestHashHi !== undefined && request.requestHashLo !== undefined) {
  const first = asString(poseidon, poseidon([
    INPUT_BINDING_DOMAIN,
    BigInt(result.root),
    BigInt(documentCount),
  ]));
  const second = asString(poseidon, poseidon([
    BigInt(first),
    BigInt(request.promptHashHi),
    BigInt(request.promptHashLo),
  ]));
  result.input_binding = asString(poseidon, poseidon([
    BigInt(second),
    BigInt(request.requestHashHi),
    BigInt(request.requestHashLo),
  ]));
  result.domains.input_binding = INPUT_BINDING_DOMAIN.toString();
}

if (request.index !== undefined) {
  const index = Number(request.index);
  if (!Number.isInteger(index) || index < 0 || index >= documentCount) throw new Error("Invalid evidence index");
  let cursor = index;
  result.siblings = [];
  for (let level = 0; level < 4; level++) {
    result.siblings.push(levels[level][cursor ^ 1]);
    cursor = Math.floor(cursor / 2);
  }
  result.index = index;
}

process.stdout.write(`${JSON.stringify(result)}\n`);
