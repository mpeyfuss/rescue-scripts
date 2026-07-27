// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

contract FixtureERC20 {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "insufficient balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract FixtureERC721 {
    mapping(uint256 => address) public ownerOf;
    mapping(uint256 => address) public getApproved;

    function mint(address to, uint256 tokenId) external {
        require(ownerOf[tokenId] == address(0), "already minted");
        ownerOf[tokenId] = to;
    }

    function approve(address spender, uint256 tokenId) external {
        require(ownerOf[tokenId] == msg.sender, "not owner");
        getApproved[tokenId] = spender;
    }

    function transferFrom(address from, address to, uint256 tokenId) external {
        require(ownerOf[tokenId] == from, "wrong owner");
        require(msg.sender == from || getApproved[tokenId] == msg.sender, "not approved");
        ownerOf[tokenId] = to;
        delete getApproved[tokenId];
    }
}

contract FixtureERC1155 {
    mapping(address => mapping(uint256 => uint256)) public balanceOf;

    function mint(address to, uint256 tokenId, uint256 amount) external {
        balanceOf[to][tokenId] += amount;
    }

    function safeTransferFrom(
        address from,
        address to,
        uint256 tokenId,
        uint256 amount,
        bytes calldata
    ) external {
        require(msg.sender == from, "not owner");
        require(balanceOf[from][tokenId] >= amount, "insufficient balance");
        balanceOf[from][tokenId] -= amount;
        balanceOf[to][tokenId] += amount;
    }
}

// Rejects senders that carry code, so it fails under an EIP-7702 delegation and
// only succeeds via a direct victim transaction (the legacy fallback).
contract FixtureCodeRejectingERC20 {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(msg.sender.code.length == 0, "no contracts");
        require(balanceOf[msg.sender] >= amount, "insufficient balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

// Returns false instead of reverting, so the low-level call "succeeds" while no
// tokens move. Proves outcome detection relies on state, not call success.
contract FixtureFalseReturningERC20 {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address, uint256) external pure returns (bool) {
        return false;
    }
}

contract FixtureOwnable {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function transferOwnership(address newOwner) external {
        require(msg.sender == owner, "not owner");
        owner = newOwner;
    }
}

interface IERC721Fixture {
    function transferFrom(address from, address to, uint256 tokenId) external;
}

contract FixtureAuctionHouse {
    mapping(address => mapping(uint256 => address)) public seller;

    function list(address token, uint256 tokenId) external {
        seller[token][tokenId] = msg.sender;
        IERC721Fixture(token).transferFrom(msg.sender, address(this), tokenId);
    }

    function delist(address token, uint256 tokenId) external {
        require(seller[token][tokenId] == msg.sender, "not seller");
        delete seller[token][tokenId];
        IERC721Fixture(token).transferFrom(address(this), msg.sender, tokenId);
    }
}

contract FixtureDelegateTarget {}
