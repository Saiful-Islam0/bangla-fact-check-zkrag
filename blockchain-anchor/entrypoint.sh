#!/bin/bash
set -e

echo "=== Starting ZK-RAG Blockchain Anchor Service ==="

RPC_URL="${ZKRAG_EVM_RPC_URL:-http://127.0.0.1:8545}"
BRIDGE_PORT="${ZKRAG_ANCHOR_BRIDGE_PORT:-8787}"
export ZKRAG_ANCHOR_BRIDGE_HOST="${ZKRAG_ANCHOR_BRIDGE_HOST:-0.0.0.0}"

# If RPC_URL points to localhost/127.0.0.1, spin up local Hardhat node
if [[ "$RPC_URL" == *"127.0.0.1"* ]] || [[ "$RPC_URL" == *"localhost"* ]]; then
    echo "Starting local Hardhat node on port 8545..."
    mkdir -p /root/.config/hardhat-nodejs /root/Library/Preferences/hardhat-nodejs
    echo '{"telemetryEnabled":false}' > /root/.config/hardhat-nodejs/telemetry.json 2>/dev/null || true
    echo '{"telemetryEnabled":false}' > /root/Library/Preferences/hardhat-nodejs/telemetry.json 2>/dev/null || true

    npx hardhat node --hostname 0.0.0.0 --port 8545 > /tmp/hardhat.log 2>&1 &
    HARDHAT_PID=$!

    echo "Waiting for Hardhat node to accept connections..."
    for i in {1..30}; do
        if curl -s -X POST -H "Content-Type: application/json" --data '{"jsonrpc":"2.0","method":"net_version","params":[],"id":1}' http://127.0.0.1:8545 > /dev/null 2>&1; then
            echo "Hardhat node is ready (chain ID 31337)!"
            break
        fi
        sleep 1
    done

    # Deploy contract if address is not specified or newly booted node
    if [ -z "$ZKRAG_ANCHOR_CONTRACT_ADDRESS" ]; then
        echo "Deploying VerificationRecordAnchor contract..."
        npm run setup
        if [ -f .env ]; then
            set -a
            . .env
            set +a
        fi
    fi
else
    echo "Connecting to external EVM RPC: $RPC_URL"
    if [ -z "$ZKRAG_ANCHOR_CONTRACT_ADDRESS" ]; then
        echo "Deploying VerificationRecordAnchor to network..."
        npm run setup || true
        if [ -f .env ]; then
            set -a
            . .env
            set +a
        fi
    fi
fi

if [ -f .env ]; then
    set -a
    . .env
    set +a
fi

echo "Starting zkRAG Anchor Bridge on http://${ZKRAG_ANCHOR_BRIDGE_HOST}:${BRIDGE_PORT}..."
exec node src/bridge.cjs
