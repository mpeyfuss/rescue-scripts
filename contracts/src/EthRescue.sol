// SPDX-License-Identifier: MIT
pragma solidity 0.8.31;

import {LibCall} from "solady-0.1.26/utils/LibCall.sol";
import {IERC165} from "@openzeppelin-contracts-5.6.1/utils/introspection/IERC165.sol";
import {IERC721Receiver} from "@openzeppelin-contracts-5.6.1/token/ERC721/IERC721Receiver.sol";
import {IERC1155Receiver} from "@openzeppelin-contracts-5.6.1/token/ERC1155/IERC1155Receiver.sol";

/// @title EthRescue
/// @notice Stateless rescue contract used as an EIP-7702 delegation for rescue operations.
/// @dev Uses immutables instead of storage to avoid conflicting with delegated account storage.
/// @author mpeyfuss
contract EthRescue is IERC165, IERC721Receiver, IERC1155Receiver {

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
        return interfaceId == type(IERC165).interfaceId || interfaceId == type(IERC721Receiver).interfaceId
            || interfaceId == type(IERC1155Receiver).interfaceId;
    }

    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return IERC721Receiver.onERC721Received.selector;
    }

    function onERC1155Received(address, address, uint256, uint256, bytes calldata) external pure returns (bytes4) {
        return IERC1155Receiver.onERC1155Received.selector;
    }

    function onERC1155BatchReceived(address, address, uint256[] calldata, uint256[] calldata, bytes calldata)
        external
        pure
        returns (bytes4)
    {
        return IERC1155Receiver.onERC1155BatchReceived.selector;
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
