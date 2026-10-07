#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
PTAU_DIR="$ROOT_DIR/ptau"
PTAU_FILE="$PTAU_DIR/powersOfTau28_hez_final_12.ptau"
PTAU_BLAKE2B="ded2694169b7b08e898f736d5de95af87c3f1a64594013351b1a796dbee393bd825f88f9468c84505ddd11eb0b1465ac9b43b9064aa8ec97f2b73e04758b8a4a"
# The original Hermez bucket currently denies anonymous downloads. This mirror
# is accepted only after matching iden3's published BLAKE2b digest above.
PTAU_URL="https://raw.githubusercontent.com/advaita-saha/create-circom-project/master/powersOfTau28_hez_final_12.ptau"

mkdir -p "$BUILD_DIR" "$PTAU_DIR"

if ! command -v circom >/dev/null 2>&1; then
  echo "circom 2.2.3 is required. Install it from https://github.com/iden3/circom/releases/tag/v2.2.3" >&2
  exit 1
fi

ACTUAL_VERSION="$(circom --version | awk '{print $NF}')"
if [[ "$ACTUAL_VERSION" != "2.2.3" ]]; then
  echo "Expected circom 2.2.3, found $ACTUAL_VERSION" >&2
  exit 1
fi

if [[ ! -f "$PTAU_FILE" ]]; then
  curl --fail --location "$PTAU_URL" --output "$PTAU_FILE"
fi
ACTUAL_BLAKE2B="$(node -e 'const fs=require("fs"),crypto=require("crypto");const h=crypto.createHash("blake2b512");fs.createReadStream(process.argv[1]).on("data",d=>h.update(d)).on("end",()=>process.stdout.write(h.digest("hex")))' "$PTAU_FILE")"
if [[ "$ACTUAL_BLAKE2B" != "$PTAU_BLAKE2B" ]]; then
  echo "Powers of Tau BLAKE2b checksum mismatch" >&2
  exit 1
fi

circom "$ROOT_DIR/circuits/evidence_membership.circom" \
  --r1cs --wasm --sym \
  --output "$BUILD_DIR" \
  -l "$ROOT_DIR/node_modules"

"$ROOT_DIR/node_modules/.bin/snarkjs" groth16 setup \
  "$BUILD_DIR/evidence_membership.r1cs" \
  "$PTAU_FILE" \
  "$BUILD_DIR/evidence_membership_0000.zkey"

# The contribution is intentionally non-interactive and uses fresh entropy.
# Production deployments should repeat phase two with independent contributors.
PHASE2_ENTROPY="${ZKRAG_PHASE2_ENTROPY:-$(openssl rand -hex 64)}"
"$ROOT_DIR/node_modules/.bin/snarkjs" zkey contribute \
  "$BUILD_DIR/evidence_membership_0000.zkey" \
  "$BUILD_DIR/evidence_membership_final.zkey" \
  --name="zkRAG-BChain build contribution v1" \
  --entropy="$PHASE2_ENTROPY"
unset PHASE2_ENTROPY

"$ROOT_DIR/node_modules/.bin/snarkjs" zkey verify \
  "$BUILD_DIR/evidence_membership.r1cs" \
  "$PTAU_FILE" \
  "$BUILD_DIR/evidence_membership_final.zkey"
"$ROOT_DIR/node_modules/.bin/snarkjs" zkey export verificationkey \
  "$BUILD_DIR/evidence_membership_final.zkey" \
  "$BUILD_DIR/verification_key.json"

(cd "$BUILD_DIR" && shasum -a 256 \
  evidence_membership.r1cs \
  evidence_membership_js/evidence_membership.wasm \
  evidence_membership_final.zkey \
  verification_key.json \
  manifest.json > SHA256SUMS)

echo "ZK artifacts created in $BUILD_DIR"
