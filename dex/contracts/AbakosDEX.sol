// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function balanceOf(address) external view returns (uint256);
}

/// @title AbakosDEX - minimal constant-product AMM (native ABA <-> USDC)
/// @notice x*y=k pool between native ABA (18-dec on the EVM) and an ERC-20 USDC
///         (6-dec). 0.30% swap fee accrues to liquidity providers, tracked by LP
///         shares. Checks-effects-interactions ordering: reserves are updated
///         before any external transfer, so reserve accounting is reentrancy-safe.
///         Sandbox v1; upgrade to a full Uniswap-v2 fork for mainnet.
contract AbakosDEX {
    IERC20 public immutable usdc;

    uint256 public reserveABA;  // wei (1e18)
    uint256 public reserveUSDC; // 1e6
    uint256 public totalShares;
    mapping(address => uint256) public shares;

    event LiquidityAdded(address indexed provider, uint256 aba, uint256 usdc, uint256 sharesMinted);
    event LiquidityRemoved(address indexed provider, uint256 aba, uint256 usdc, uint256 sharesBurned);
    event Swap(address indexed user, bool abaIn, uint256 amountIn, uint256 amountOut);

    constructor(address _usdc) {
        usdc = IERC20(_usdc);
    }

    function _sqrt(uint256 y) internal pure returns (uint256 z) {
        if (y > 3) {
            z = y;
            uint256 x = y / 2 + 1;
            while (x < z) {
                z = x;
                x = (y / x + x) / 2;
            }
        } else if (y != 0) {
            z = 1;
        }
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }

    /// @notice Add liquidity: send ABA as msg.value + provide usdcAmount (approve first).
    function addLiquidity(uint256 usdcAmount) external payable returns (uint256 minted) {
        require(msg.value > 0 && usdcAmount > 0, "amounts");
        require(usdc.transferFrom(msg.sender, address(this), usdcAmount), "usdc in");
        if (totalShares == 0) {
            minted = _sqrt(msg.value * usdcAmount);
        } else {
            minted = _min(
                (msg.value * totalShares) / reserveABA,
                (usdcAmount * totalShares) / reserveUSDC
            );
        }
        require(minted > 0, "shares");
        shares[msg.sender] += minted;
        totalShares += minted;
        reserveABA += msg.value;
        reserveUSDC += usdcAmount;
        emit LiquidityAdded(msg.sender, msg.value, usdcAmount, minted);
    }

    /// @notice Burn `s` LP shares, receive proportional ABA + USDC.
    function removeLiquidity(uint256 s) external returns (uint256 abaOut, uint256 usdcOut) {
        require(s > 0 && shares[msg.sender] >= s, "shares");
        abaOut = (s * reserveABA) / totalShares;
        usdcOut = (s * reserveUSDC) / totalShares;
        shares[msg.sender] -= s;
        totalShares -= s;
        reserveABA -= abaOut;
        reserveUSDC -= usdcOut;
        require(usdc.transfer(msg.sender, usdcOut), "usdc out");
        (bool ok, ) = msg.sender.call{value: abaOut}("");
        require(ok, "aba out");
        emit LiquidityRemoved(msg.sender, abaOut, usdcOut, s);
    }

    function _out(uint256 amountIn, uint256 rIn, uint256 rOut) internal pure returns (uint256) {
        uint256 inWithFee = amountIn * 997;
        return (inWithFee * rOut) / (rIn * 1000 + inWithFee);
    }

    function getAmountOutABAtoUSDC(uint256 abaIn) external view returns (uint256) {
        return _out(abaIn, reserveABA, reserveUSDC);
    }

    function getAmountOutUSDCtoABA(uint256 usdcIn) external view returns (uint256) {
        return _out(usdcIn, reserveUSDC, reserveABA);
    }

    /// @notice Swap native ABA (msg.value) for USDC. `minOut` protects against slippage.
    function swapABAForUSDC(uint256 minOut) external payable returns (uint256 out) {
        require(msg.value > 0, "in");
        out = _out(msg.value, reserveABA, reserveUSDC);
        require(out >= minOut && out < reserveUSDC, "slippage");
        reserveABA += msg.value;
        reserveUSDC -= out;
        require(usdc.transfer(msg.sender, out), "usdc out");
        emit Swap(msg.sender, true, msg.value, out);
    }

    /// @notice Swap USDC (approve first) for native ABA. `minOut` protects against slippage.
    function swapUSDCForABA(uint256 usdcIn, uint256 minOut) external returns (uint256 out) {
        require(usdcIn > 0, "in");
        require(usdc.transferFrom(msg.sender, address(this), usdcIn), "usdc in");
        out = _out(usdcIn, reserveUSDC, reserveABA);
        require(out >= minOut && out < reserveABA, "slippage");
        reserveUSDC += usdcIn;
        reserveABA -= out;
        (bool ok, ) = msg.sender.call{value: out}("");
        require(ok, "aba out");
        emit Swap(msg.sender, false, usdcIn, out);
    }

    receive() external payable {}
}
