const hre = require("hardhat");

async function main() {
  const factory = await hre.ethers.getContractFactory("VerificationRecordAnchor");
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  process.stdout.write(`${JSON.stringify({ address: await contract.getAddress(), chain_id: String((await hre.ethers.provider.getNetwork()).chainId) })}\n`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
