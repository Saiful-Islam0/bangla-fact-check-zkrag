// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract VerificationRecordAnchor {
    struct AnchorInfo {
        bytes32 claimHash;
        uint64 anchoredAt;
        address submitter;
    }

    address public immutable owner;
    mapping(bytes32 => AnchorInfo) public records;
    mapping(bytes32 => bytes32) public latestByClaim;

    event VerificationAnchored(
        bytes32 indexed recordCommitment,
        bytes32 indexed claimHash,
        uint64 anchoredAt,
        address indexed submitter,
        uint16 schemaVersion
    );

    error NotOwner();
    error AlreadyAnchored();
    error EmptyCommitment();

    constructor() { owner = msg.sender; }

    function anchor(bytes32 recordCommitment, bytes32 claimHash) external {
        if (msg.sender != owner) revert NotOwner();
        if (recordCommitment == bytes32(0) || claimHash == bytes32(0)) revert EmptyCommitment();
        if (records[recordCommitment].anchoredAt != 0) revert AlreadyAnchored();
        uint64 timestamp = uint64(block.timestamp);
        records[recordCommitment] = AnchorInfo(claimHash, timestamp, msg.sender);
        latestByClaim[claimHash] = recordCommitment;
        emit VerificationAnchored(recordCommitment, claimHash, timestamp, msg.sender, 1);
    }
}
