// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract EncryptedUpdateRelay {
    address public owner;
    mapping(address => bool) public relayers;

    struct Query {
        address requester;
        bytes32 roundContextDigest;
        string targetChain;
        uint256 requestTimestampNs;
        bytes requestSignature;
        bool fulfilled;
        bytes responsePayload;
        bytes32 responseDigest;
        bytes responseSignature;
        uint256 responseTimestampNs;
    }

    mapping(bytes32 => Query) private queries;

    event EncryptedUpdateQueryRequested(
        bytes32 indexed requestId,
        bytes32 indexed roundContextDigest,
        address indexed requester,
        string targetChain
    );
    event EncryptedUpdateQueryFulfilled(
        bytes32 indexed requestId,
        bytes32 indexed responseDigest,
        address indexed relayer
    );

    constructor() {
        owner = msg.sender;
        relayers[msg.sender] = true;
    }

    function setRelayer(address relayer, bool allowed) external {
        require(msg.sender == owner, "owner only");
        relayers[relayer] = allowed;
    }

    function requestEncryptedLocalUpdates(
        bytes32 roundContextDigest,
        string calldata targetChain,
        bytes calldata requestSignature,
        uint256 timestampNs
    ) external returns (bytes32 requestId) {
        require(bytes(targetChain).length > 0, "empty target chain");
        requestId = keccak256(
            abi.encode(msg.sender, roundContextDigest, targetChain, timestampNs, requestSignature)
        );
        require(queries[requestId].requester == address(0), "duplicate request");
        queries[requestId] = Query(
            msg.sender, roundContextDigest, targetChain, timestampNs,
            requestSignature, false, "", bytes32(0), "", 0
        );
        emit EncryptedUpdateQueryRequested(requestId, roundContextDigest, msg.sender, targetChain);
    }

    function fulfillEncryptedLocalUpdates(
        bytes32 requestId,
        bytes calldata responsePayload,
        bytes32 responseDigest,
        bytes calldata responseSignature,
        uint256 timestampNs
    ) external {
        require(relayers[msg.sender], "unauthorized relayer");
        Query storage query = queries[requestId];
        require(query.requester != address(0), "unknown request");
        require(!query.fulfilled, "already fulfilled");
        require(sha256(responsePayload) == responseDigest, "response digest mismatch");
        query.fulfilled = true;
        query.responsePayload = responsePayload;
        query.responseDigest = responseDigest;
        query.responseSignature = responseSignature;
        query.responseTimestampNs = timestampNs;
        emit EncryptedUpdateQueryFulfilled(requestId, responseDigest, msg.sender);
    }

    function getEncryptedLocalUpdateResponse(bytes32 requestId)
        external view returns (Query memory)
    {
        require(queries[requestId].requester != address(0), "unknown request");
        return queries[requestId];
    }
}
