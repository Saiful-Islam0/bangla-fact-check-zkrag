#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/input_binding_v2"
PTAU_DIR="$ROOT_DIR/ptau"
PTAU_FILE="$PTAU_DIR/powersOfTau28_hez_final_14.ptau"
PTAU_BLAKE2B="eeefbcf7c3803b523c94112023c7ff89558f9b8e0cf5d6cdcba3ade60f168af4a181c9c21774b94fbae6c90411995f7d854d02ebd93fb66043dbb06f17a831c1"
# Public mirror; accepted only after matching iden3's published BLAKE2b digest.
PTAU_URL="https://raw.githubusercontent.com/yoyoismee/trusted-setup/main/ptau/powersOfTau28_hez_final_14.ptau"

mkdir -p "$BUILD_DIR" "$PTAU_DIR"
if ! command -v circom >/dev/null 2>&1; then
  echo "circom 2.2.3 is required" >&2
  exit 1
fi
ACTUAL_VERSION="$(circom --version | awk '{print $NF}')"
[[ "$ACTUAL_VERSION" == "2.2.3" ]] || { echo "Expected circom 2.2.3, found $ACTUAL_VERSION" >&2; exit 1; }

if [[ ! -f "$PTAU_FILE" ]]; then
  curl --fail --location "$PTAU_URL" --output "$PTAU_FILE"
fi
ACTUAL_BLAKE2B="$(node -e 'const fs=require("fs"),crypto=require("crypto");const h=crypto.createHash("blake2b512");fs.createReadStream(process.argv[1]).on("data",d=>h.update(d)).on("end",()=>process.stdout.write(h.digest("hex")))' "$PTAU_FILE")"
[[ "$ACTUAL_BLAKE2B" == "$PTAU_BLAKE2B" ]] || { echo "Powers of Tau BLAKE2b checksum mismatch" >&2; exit 1; }

circom "$ROOT_DIR/circuits/evidence_input_binding.circom" \
  --r1cs --wasm --sym --output "$BUILD_DIR" -l "$ROOT_DIR/node_modules"

SNARKJS="$ROOT_DIR/node_modules/.bin/snarkjs"
if [[ ! -f "$BUILD_DIR/evidence_input_binding_final.zkey" || "${ZKRAG_FORCE_SETUP:-0}" == "1" ]]; then
  "$SNARKJS" groth16 setup "$BUILD_DIR/evidence_input_binding.r1cs" "$PTAU_FILE" "$BUILD_DIR/evidence_input_binding_0000.zkey"
  PHASE2_ENTROPY="${ZKRAG_PHASE2_ENTROPY:-$(openssl rand -hex 64)}"
  "$SNARKJS" zkey contribute \
    "$BUILD_DIR/evidence_input_binding_0000.zkey" \
    "$BUILD_DIR/evidence_input_binding_final.zkey" \
    --name="zkRAG-BChain aggregate input binding v2" --entropy="$PHASE2_ENTROPY"
  unset PHASE2_ENTROPY
else
  echo "Reusing existing v2 phase-two key; set ZKRAG_FORCE_SETUP=1 to replace it intentionally"
fi
"$SNARKJS" zkey verify "$BUILD_DIR/evidence_input_binding.r1cs" "$PTAU_FILE" "$BUILD_DIR/evidence_input_binding_final.zkey"
"$SNARKJS" zkey export verificationkey "$BUILD_DIR/evidence_input_binding_final.zkey" "$BUILD_DIR/verification_key.json"

node -e 'const fs=require("fs");const p=process.argv[1];const m={circuit_version:"evidence-input-binding-16-v2",circom:"2.2.3",snarkjs:"0.7.6",circomlib:"2.0.5",curve:"BN254",proof_system:"Groth16",tree_capacity:16,max_documents:10,powers_of_tau:"powersOfTau28_hez_final_14.ptau"};fs.writeFileSync(p,JSON.stringify(m,null,2)+"\n")' "$BUILD_DIR/manifest.json"
(cd "$BUILD_DIR" && shasum -a 256 \
  evidence_input_binding.r1cs \
  evidence_input_binding_js/evidence_input_binding.wasm \
  evidence_input_binding_final.zkey \
  verification_key.json \
  manifest.json > SHA256SUMS)

echo "Input-binding artifacts created in $BUILD_DIR"
