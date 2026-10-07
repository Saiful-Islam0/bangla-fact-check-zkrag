const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VerificationRecordAnchor", function () {
  it("anchors once, supports lookup, and rejects unauthorized or duplicate writes", async function () {
    const [owner, stranger] = await ethers.getSigners();
    const contract = await (await ethers.getContractFactory("VerificationRecordAnchor")).deploy();
    const record = ethers.sha256(ethers.toUtf8Bytes("record"));
    const claim = ethers.sha256(ethers.toUtf8Bytes("claim"));
    await expect(contract.anchor(record, claim)).to.emit(contract, "VerificationAnchored");
    expect(await contract.latestByClaim(claim)).to.equal(record);
    await expect(contract.anchor(record, claim)).to.be.revertedWithCustomError(contract, "AlreadyAnchored");
    await expect(contract.connect(stranger).anchor(ethers.sha256(ethers.toUtf8Bytes("other")), claim)).to.be.revertedWithCustomError(contract, "NotOwner");
    expect(await contract.owner()).to.equal(owner.address);
  });
});
