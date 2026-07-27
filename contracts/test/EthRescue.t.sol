// SPDX-License-Identifier: MIT
pragma solidity 0.8.31;

import {Test} from "forge-std-1.16.2/Test.sol";
import {ERC20} from "solady-0.1.26/tokens/ERC20.sol";
import {ERC721} from "solady-0.1.26/tokens/ERC721.sol";
import {ERC1155} from "solady-0.1.26/tokens/ERC1155.sol";
import {EthRescue} from "src/EthRescue.sol";

contract CallRecorder {
    address public caller;
    uint256 public calls;

    function record() external {
        caller = msg.sender;
        ++calls;
    }
}

contract RevertingTarget {
    error Reverted();

    function fail() external pure {
        revert Reverted();
    }
}

contract FalseReturningTarget {
    function returnFalse() external pure returns (bool) {
        return false;
    }
}

contract NoReturnTarget {
    uint256 public calls;

    function run() external {
        ++calls;
    }
}

contract GasBurningTarget {
    function burn() external pure {
        assembly {
            for {} 1 {} {}
        }
    }
}

contract ReturnDataBomb {
    function explode() external pure {
        bytes memory data = new bytes(32_000);
        assembly {
            return(add(data, 0x20), mload(data))
        }
    }
}

contract RefundTarget {
    address public caller;

    function refund() external {
        caller = msg.sender;
        (bool success,) = msg.sender.call{value: address(this).balance}("");
        require(success);
    }

    receive() external payable {}
}

contract RejectingSafe {
    receive() external payable {
        revert();
    }
}

contract ReentrantTarget {
    bytes4 public revertSelector;

    function attemptRescue() external {
        EthRescue.Action[] memory actions = new EthRescue.Action[](0);
        try EthRescue(payable(msg.sender)).rescue(actions) {}
        catch (bytes memory reason) {
            if (reason.length >= 4) {
                bytes4 selector;
                assembly {
                    selector := mload(add(reason, 0x20))
                }
                revertSelector = selector;
            }
        }
    }
}

contract FixtureERC20 is ERC20 {
    function name() public pure override returns (string memory) {
        return "Fixture ERC20";
    }

    function symbol() public pure override returns (string memory) {
        return "F20";
    }

    function mint(address account, uint256 amount) external {
        _mint(account, amount);
    }
}

contract FixtureERC721 is ERC721 {
    function name() public pure override returns (string memory) {
        return "Fixture ERC721";
    }

    function symbol() public pure override returns (string memory) {
        return "F721";
    }

    function tokenURI(uint256) public pure override returns (string memory) {
        return "";
    }

    function mint(address account, uint256 tokenId) external {
        _mint(account, tokenId);
    }
}

contract FixtureERC1155 is ERC1155 {
    function uri(uint256) public pure override returns (string memory) {
        return "";
    }

    function mint(address account, uint256 tokenId, uint256 amount) external {
        _mint(account, tokenId, amount, "");
    }
}

contract FixtureOwnable {
    address public owner;

    constructor(address initialOwner) {
        owner = initialOwner;
    }

    function transferOwnership(address newOwner) external {
        require(msg.sender == owner);
        owner = newOwner;
    }
}

contract EthRescueTest is Test {
    uint256 private constant VICTIM_KEY = 0xA11CE;

    address private victim;
    address private rescuer;
    address private safe;
    EthRescue private implementation;
    EthRescue private delegated;

    function setUp() public {
        victim = vm.addr(VICTIM_KEY);
        rescuer = makeAddr("rescuer");
        safe = makeAddr("safe");
        implementation = new EthRescue(rescuer, safe);
        delegated = EthRescue(payable(victim));
        _attachDelegation();
    }

    function testConstructorStoresImmutableConfiguration() public view {
        assertEq(implementation.RESCUER(), rescuer);
        assertEq(implementation.SAFE(), safe);
        assertEq(delegated.RESCUER(), rescuer);
        assertEq(delegated.SAFE(), safe);
    }

    function testConstructorRejectsInvalidAddresses() public {
        vm.expectRevert(EthRescue.InvalidRescuer.selector);
        new EthRescue(address(0), safe);

        vm.expectRevert(EthRescue.InvalidSafe.selector);
        new EthRescue(rescuer, address(0));

        vm.expectRevert(EthRescue.InvalidSafe.selector);
        new EthRescue(rescuer, rescuer);
    }

    function testSupportsTokenReceiverInterfaces() public view {
        assertTrue(delegated.supportsInterface(0x01ffc9a7)); // ERC165
        assertTrue(delegated.supportsInterface(0x150b7a02)); // ERC721Receiver
        assertTrue(delegated.supportsInterface(0x4e2312e0)); // ERC1155Receiver
        assertFalse(delegated.supportsInterface(0xffffffff)); 
    }

    function testDelegatedVictimReceivesSafeTransferredTokens() public {
        address holder = makeAddr("holder");
        FixtureERC721 erc721 = new FixtureERC721();
        FixtureERC1155 erc1155 = new FixtureERC1155();
        erc721.mint(holder, 1);
        erc1155.mint(holder, 1, 3);
        erc1155.mint(holder, 2, 4);
        erc1155.mint(holder, 3, 5);

        vm.prank(holder);
        erc721.safeTransferFrom(holder, victim, 1, "erc721");

        vm.prank(holder);
        erc1155.safeTransferFrom(holder, victim, 1, 3, "erc1155");

        uint256[] memory tokenIds = new uint256[](2);
        tokenIds[0] = 2;
        tokenIds[1] = 3;
        uint256[] memory amounts = new uint256[](2);
        amounts[0] = 4;
        amounts[1] = 5;
        vm.prank(holder);
        erc1155.safeBatchTransferFrom(holder, victim, tokenIds, amounts, "batch");

        assertEq(erc721.ownerOf(1), victim);
        assertEq(erc1155.balanceOf(victim, 1), 3);
        assertEq(erc1155.balanceOf(victim, 2), 4);
        assertEq(erc1155.balanceOf(victim, 3), 5);
    }

    function testOnlyRescuerCanExecute(address hacker) public {
        vm.assume(hacker != rescuer);

        vm.prank(hacker);
        vm.expectRevert(EthRescue.NotAllowed.selector);
        delegated.rescue(_emptyActions());
    }

    function testActionCallsOriginateFromVictim() public {
        CallRecorder target = new CallRecorder();

        _rescue(_singleAction(false, address(target), 100_000, abi.encodeCall(target.record, ())));

        assertEq(target.caller(), victim);
        assertEq(target.calls(), 1);
    }

    function testRescueTransfersCommonAssetTypesAndOwnership() public {
        FixtureERC20 erc20 = new FixtureERC20();
        FixtureERC721 erc721 = new FixtureERC721();
        FixtureERC1155 erc1155 = new FixtureERC1155();
        FixtureOwnable ownable = new FixtureOwnable(victim);
        erc20.mint(victim, 1_000);
        erc721.mint(victim, 1);
        erc1155.mint(victim, 1, 25);

        EthRescue.Action[] memory actions = new EthRescue.Action[](4);
        actions[0] = _action(false, address(erc20), 100_000, abi.encodeCall(erc20.transfer, (safe, 1_000)));
        actions[1] = _action(false, address(erc721), 100_000, abi.encodeCall(erc721.transferFrom, (victim, safe, 1)));
        actions[2] = _action(
            false, address(erc1155), 150_000, abi.encodeCall(erc1155.safeTransferFrom, (victim, safe, 1, 25, ""))
        );
        actions[3] = _action(false, address(ownable), 100_000, abi.encodeCall(ownable.transferOwnership, (safe)));

        _rescue(actions);

        assertEq(erc20.balanceOf(victim), 0);
        assertEq(erc20.balanceOf(safe), 1_000);
        assertEq(erc721.ownerOf(1), safe);
        assertEq(erc1155.balanceOf(victim, 1), 0);
        assertEq(erc1155.balanceOf(safe, 1), 25);
        assertEq(ownable.owner(), safe);
    }

    function testOptionalFailureContinues() public {
        RevertingTarget revertingTarget = new RevertingTarget();
        CallRecorder recorder = new CallRecorder();
        EthRescue.Action[] memory actions = new EthRescue.Action[](2);
        actions[0] = _action(false, address(revertingTarget), 100_000, abi.encodeCall(revertingTarget.fail, ()));
        actions[1] = _action(false, address(recorder), 100_000, abi.encodeCall(recorder.record, ()));

        _rescue(actions);

        assertEq(recorder.calls(), 1);
    }

    function testRequiredFailureRevertsActionsAndSweep() public {
        CallRecorder recorder = new CallRecorder();
        RevertingTarget revertingTarget = new RevertingTarget();
        EthRescue.Action[] memory actions = new EthRescue.Action[](2);
        actions[0] = _action(false, address(recorder), 100_000, abi.encodeCall(recorder.record, ()));
        actions[1] = _action(true, address(revertingTarget), 100_000, abi.encodeCall(revertingTarget.fail, ()));
        vm.deal(victim, 1 ether);

        vm.expectRevert(abi.encodeWithSelector(EthRescue.RequiredActionFailed.selector, 1));
        _rescue(actions);

        assertEq(recorder.calls(), 0);
        assertEq(victim.balance, 1 ether);
        assertEq(safe.balance, 0);
    }

    function testRequiredFalseReturnCountsAsEvmSuccess() public {
        FalseReturningTarget target = new FalseReturningTarget();

        _rescue(_singleAction(true, address(target), 100_000, abi.encodeCall(target.returnFalse, ())));
    }

    function testNoReturnCountsAsEvmSuccess() public {
        NoReturnTarget target = new NoReturnTarget();

        _rescue(_singleAction(true, address(target), 100_000, abi.encodeCall(target.run, ())));

        assertEq(target.calls(), 1);
    }

    function testGasBurningTargetCannotBlockLaterAction() public {
        GasBurningTarget burner = new GasBurningTarget();
        CallRecorder recorder = new CallRecorder();
        EthRescue.Action[] memory actions = new EthRescue.Action[](2);
        actions[0] = _action(false, address(burner), 30_000, abi.encodeCall(burner.burn, ()));
        actions[1] = _action(false, address(recorder), 100_000, abi.encodeCall(recorder.record, ()));

        vm.prank(rescuer);
        delegated.rescue{gas: 500_000}(actions);

        assertEq(recorder.calls(), 1); // first call fails
    }

    function testReturnDataBombCannotBlockLaterAction() public {
        ReturnDataBomb bomb = new ReturnDataBomb();
        CallRecorder recorder = new CallRecorder();
        EthRescue.Action[] memory actions = new EthRescue.Action[](2);
        actions[0] = _action(false, address(bomb), 1_000_000, abi.encodeCall(bomb.explode, ()));
        actions[1] = _action(false, address(recorder), 100_000, abi.encodeCall(recorder.record, ()));

        _rescue(actions);

        assertEq(recorder.calls(), 1); // first call fails
    }

    function testTargetCannotReenterRescue() public {
        ReentrantTarget target = new ReentrantTarget();

        _rescue(_singleAction(false, address(target), 200_000, abi.encodeCall(target.attemptRescue, ())));

        assertEq(target.revertSelector(), EthRescue.NotAllowed.selector);
    }

    function testInvalidActionShapesRevertBeforeExecution() public {
        CallRecorder recorder = new CallRecorder();
        EthRescue.Action[] memory actions = new EthRescue.Action[](2);
        actions[0] = _action(false, address(recorder), 100_000, abi.encodeCall(recorder.record, ()));
        actions[1] = _action(false, address(0), 100_000, "");

        vm.expectRevert(abi.encodeWithSelector(EthRescue.InvalidAction.selector, 1));
        _rescue(actions);

        actions[1].target = victim;
        vm.expectRevert(abi.encodeWithSelector(EthRescue.InvalidAction.selector, 1));
        _rescue(actions);

        actions[1].target = address(recorder);
        actions[1].gasStipend = 0;
        vm.expectRevert(abi.encodeWithSelector(EthRescue.InvalidAction.selector, 1));
        _rescue(actions);
    }

    function testVictimAcceptsRefundAndSweepsItAfterActions() public {
        RefundTarget target = new RefundTarget();
        vm.deal(address(target), 2 ether);

        _rescue(_singleAction(false, address(target), 200_000, abi.encodeCall(target.refund, ())));

        assertEq(target.caller(), victim);
        assertEq(victim.balance, 0);
        assertEq(safe.balance, 2 ether);
    }

    function testDelegatedVictimCanReceivePlainEthBeforeRescue() public {
        address sender = makeAddr("sender");
        vm.deal(sender, 1 ether);

        vm.prank(sender);
        (bool success,) = victim.call{value: 1 ether}("");

        assertTrue(success);
        assertEq(victim.balance, 1 ether);
        _rescue(_emptyActions());
        assertEq(safe.balance, 1 ether);
    }

    function testZeroBalanceDoesNotCallRejectingSafe() public {
        RejectingSafe rejectingSafe = new RejectingSafe();
        EthRescue rescue = new EthRescue(rescuer, address(rejectingSafe));

        vm.prank(rescuer);
        rescue.rescue(_emptyActions());
    }

    function testRejectingSafeRevertsPositiveSweep() public {
        RejectingSafe rejectingSafe = new RejectingSafe();
        EthRescue rescue = new EthRescue(rescuer, address(rejectingSafe));
        vm.deal(address(rescue), 1 ether);

        vm.expectRevert(EthRescue.EthTransferFailed.selector);
        vm.prank(rescuer);
        rescue.rescue(_emptyActions());

        assertEq(address(rescue).balance, 1 ether);
    }

    function testRepeatedBatchesSweepAfterEveryCall() public {
        vm.deal(victim, 1 ether);
        _rescue(_emptyActions());
        assertEq(safe.balance, 1 ether);

        vm.deal(victim, 2 ether);
        _rescue(_emptyActions());
        assertEq(safe.balance, 3 ether);
    }

    function testRuntimeCodeHashDependsOnImmutableConfiguration() public {
        EthRescue sameConfiguration = new EthRescue(rescuer, safe);
        EthRescue differentSafe = new EthRescue(rescuer, makeAddr("different-safe"));

        assertEq(address(implementation).codehash, address(sameConfiguration).codehash);
        assertNotEq(address(implementation).codehash, address(differentSafe).codehash);
    }

    function testFuzzSweepsFullBalance(uint96 amount) public {
        vm.deal(victim, amount);

        _rescue(_emptyActions());

        assertEq(victim.balance, 0);
        assertEq(safe.balance, amount);
    }

    function testFuzzExecutesEveryValidAction(uint8 rawCount) public {
        uint256 count = bound(rawCount, 1, 128);
        CallRecorder recorder = new CallRecorder();
        EthRescue.Action[] memory actions = new EthRescue.Action[](count);
        for (uint256 i; i < count; ++i) {
            actions[i] = _action(true, address(recorder), 100_000, abi.encodeCall(recorder.record, ()));
        }

        _rescue(actions);

        assertEq(recorder.calls(), count);
    }

    function _attachDelegation() private {
        vm.signAndAttachDelegation(address(implementation), VICTIM_KEY);
        _rescue(_emptyActions());
    }

    function _rescue(EthRescue.Action[] memory actions) private {
        vm.prank(rescuer);
        delegated.rescue(actions);
    }

    function _emptyActions() private pure returns (EthRescue.Action[] memory) {
        return new EthRescue.Action[](0);
    }

    function _singleAction(bool required, address target, uint256 gasStipend, bytes memory data)
        private
        pure
        returns (EthRescue.Action[] memory actions)
    {
        actions = new EthRescue.Action[](1);
        actions[0] = _action(required, target, gasStipend, data);
    }

    function _action(bool required, address target, uint256 gasStipend, bytes memory data)
        private
        pure
        returns (EthRescue.Action memory)
    {
        return EthRescue.Action({required: required, target: target, gasStipend: gasStipend, data: data});
    }
}
