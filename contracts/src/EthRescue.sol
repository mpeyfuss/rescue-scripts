// SPDX-License-Identifier: MIT
pragma solidity 0.8.31;

import {LibCall} from "solady-0.1.26/utils/LibCall.sol";

/// @title EthRescue
/// @notice Stateless rescue contract used as an EIP-7702 delegation for rescue operations.
/// @dev Uses immutables instead of storage to avoid conflicting with delegated account storage.
/// @author mpeyfuss
contract EthRescue {
    /////////////////////////////////////////////////////////////////////
    // CONSTANTS
    /////////////////////////////////////////////////////////////////////

    bytes4 private constant _ERC165_INTERFACE_ID = 0x01ffc9a7;
    bytes4 private constant _ERC721_RECEIVER_INTERFACE_ID = 0x150b7a02;
    bytes4 private constant _ERC1155_RECEIVER_INTERFACE_ID = 0x4e2312e0;
    bytes4 private constant _ERC1155_RECEIVED = 0xf23a6e61;
    bytes4 private constant _ERC1155_BATCH_RECEIVED = 0xbc197c81;

    /////////////////////////////////////////////////////////////////////
    // TYPES
    /////////////////////////////////////////////////////////////////////

    struct Action {
        bool required;
        address target;
        uint256 gasStipend;
        bytes data;
    }

    /////////////////////////////////////////////////////////////////////
    // STORAGE
    /////////////////////////////////////////////////////////////////////

    address public immutable RESCUER;
    address public immutable SAFE;

    /////////////////////////////////////////////////////////////////////
    // ERRORS
    /////////////////////////////////////////////////////////////////////

    error InvalidRescuer();
    error InvalidSafe();
    error InvalidAction(uint256 index);
    error NotAllowed();
    error RequiredActionFailed(uint256 index);
    error EthTransferFailed();

    /////////////////////////////////////////////////////////////////////
    // CONSTRUCTOR
    /////////////////////////////////////////////////////////////////////

    constructor(address rescuer, address safe) {
        if (rescuer == address(0)) revert InvalidRescuer();
        if (safe == address(0) || safe == rescuer) revert InvalidSafe();

        RESCUER = rescuer;
        SAFE = safe;
    }

    /////////////////////////////////////////////////////////////////////
    // FUNCTIONS
    /////////////////////////////////////////////////////////////////////

    receive() external payable {}

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == _ERC165_INTERFACE_ID || interfaceId == _ERC721_RECEIVER_INTERFACE_ID
            || interfaceId == _ERC1155_RECEIVER_INTERFACE_ID;
    }

    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return _ERC721_RECEIVER_INTERFACE_ID;
    }

    function onERC1155Received(address, address, uint256, uint256, bytes calldata) external pure returns (bytes4) {
        return _ERC1155_RECEIVED;
    }

    function onERC1155BatchReceived(address, address, uint256[] calldata, uint256[] calldata, bytes calldata)
        external
        pure
        returns (bytes4)
    {
        return _ERC1155_BATCH_RECEIVED;
    }

    function rescue(Action[] calldata actions) external {
        _verifyRescuer(msg.sender);

        uint256 numActions = actions.length;
        for (uint256 i; i < numActions; ++i) {
            Action calldata action = actions[i];
            if (action.target == address(0) || action.target == address(this) || action.gasStipend == 0) {
                revert InvalidAction(i);
            }

            (bool success,,) = LibCall.tryCall(action.target, 0, action.gasStipend, 0, action.data);
            if (!success && action.required) revert RequiredActionFailed(i);
        }

        _sweepEth();
    }

    /////////////////////////////////////////////////////////////////////
    // INTERNAL FUNCTIONS
    /////////////////////////////////////////////////////////////////////

    function _verifyRescuer(address sender) private view {
        if (sender != RESCUER) revert NotAllowed();
    }

    function _sweepEth() private {
        uint256 amount = address(this).balance;
        if (amount != 0) {
            (bool success,) = SAFE.call{value: amount}("");
            if (!success) revert EthTransferFailed();
        }
    }
}
