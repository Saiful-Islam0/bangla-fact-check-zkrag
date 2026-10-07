const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

async function main() {
  const envPath = path.resolve(__dirname, "../.env");
  const envExamplePath = path.resolve(__dirname, "../.env.example");

  console.log("Checking EVM RPC connection...");
  const network = await hre.ethers.provider.getNetwork();
  console.log(`Connected to EVM chain ID: ${network.chainId}`);

  const signers = await hre.ethers.getSigners();
  const deployer = signers[0];
  console.log(`Deploying VerificationRecordAnchor from ${deployer.address}...`);

  const factory = await hre.ethers.getContractFactory("VerificationRecordAnchor", deployer);
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  console.log(`VerificationRecordAnchor deployed at: ${address}`);

  // Hardhat default account #0 private key
  const defaultPrivateKey = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
  const rpcUrl = process.env.ZKRAG_EVM_RPC_URL || "http://127.0.0.1:8545";
  const bridgePort = process.env.ZKRAG_ANCHOR_BRIDGE_PORT || "8787";

  const envContent = [
    `# Auto-generated blockchain anchor configuration`,
    `ZKRAG_EVM_RPC_URL=${rpcUrl}`,
    `ZKRAG_ANCHOR_CONTRACT_ADDRESS=${address}`,
    `ZKRAG_ANCHOR_PRIVATE_KEY=${process.env.ZKRAG_ANCHOR_PRIVATE_KEY || defaultPrivateKey}`,
    `ZKRAG_ANCHOR_BRIDGE_PORT=${bridgePort}`,
    `ZKRAG_ANCHOR_BRIDGE_HOST=0.0.0.0`,
    `ZKRAG_ANCHOR_CONFIRMATIONS=1`,
    ``
  ].join("\n");

  fs.writeFileSync(envPath, envContent, "utf8");
  console.log(`Wrote configuration to ${envPath}`);

  return { address, chain_id: String(network.chainId) };
}

main().catch(error => {
  console.error("Auto setup failed:", error);
  process.exitCode = 1;
});
