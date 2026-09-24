// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PartialUpdateRegistry {
    struct Record {
        address submitter;
        string signerId;
        string kind;
        uint256 schemaVersion;
        bytes32 roundContextDigest;
        bytes payload;
        bytes32 payloadDigest;
        bytes signature;
        uint256 timestampNs;
        bytes32 transactionHash;
    }

    mapping(bytes32 => mapping(address => Record)) private records;
    mapping(bytes32 => address[]) private submitters;

    event PartialGlobalUpdateSubmitted(
        bytes32 indexed roundContextDigest,
        address indexed submitter,
        bytes32 indexed transactionHash,
        bytes32 payloadDigest,
        uint256 timestampNs
    );

    function submitPartialGlobalUpdate(
        bytes32 roundContextDigest,
        string calldata signerId,
        bytes calldata payload,
        bytes32 payloadDigest,
        bytes calldata signature,
        uint256 timestampNs,
        bytes32 transactionHash,
        string calldata kind,
        uint256 schemaVersion
    ) external returns (bytes32) {
        require(payload.length > 0, "empty payload");
        require(sha256(payload) == payloadDigest, "payload digest mismatch");
        require(bytes(signerId).length > 0, "empty signer id");
        require(transactionHash != bytes32(0), "empty transaction hash");
        require(records[roundContextDigest][msg.sender].submitter == address(0), "duplicate submission");
        records[roundContextDigest][msg.sender] = Record(
            msg.sender,
            signerId,
            kind,
            schemaVersion,
            roundContextDigest,
            payload,
            payloadDigest,
            signature,
            timestampNs,
            transactionHash
        );
        submitters[roundContextDigest].push(msg.sender);
        emit PartialGlobalUpdateSubmitted(
            roundContextDigest, msg.sender, transactionHash, payloadDigest, timestampNs
        );
        return transactionHash;
    }

    function getPartialGlobalUpdates(bytes32 roundContextDigest)
        external
        view
        returns (Record[] memory result)
    {
        address[] storage identities = submitters[roundContextDigest];
        result = new Record[](identities.length);
        for (uint256 index = 0; index < identities.length; index++) {
            result[index] = records[roundContextDigest][identities[index]];
        }
    }
}
