package app

import (
	"context"

	"cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"
	stakingtypes "github.com/cosmos/cosmos-sdk/x/staking/types"
	evmante "github.com/cosmos/evm/ante"
)

// SupplyKeeper reads the total supply of a denom (a subset of the bank keeper).
type SupplyKeeper interface {
	GetSupply(ctx context.Context, denom string) sdk.Coin
}

// minSelfDelegationDivisor: total supply / 10000 = 0.01% (1 basis point).
var minSelfDelegationDivisor = math.NewInt(10000)

// MinSelfDelegationDecorator rejects a MsgCreateValidator whose self-delegation
// or declared min_self_delegation is below 0.01% of the current total supply of
// the bond denom. Because ABA is deflationary, the bar is expressed relative to
// live supply so it scales down proportionally as supply is burned. Genesis
// gentx transactions are executed through the ante handler during InitGenesis,
// so genesis validators must also meet this floor (the genesis script funds them
// accordingly).
type MinSelfDelegationDecorator struct {
	supply    SupplyKeeper
	bondDenom string
}

// NewMinSelfDelegationDecorator creates the decorator.
func NewMinSelfDelegationDecorator(supply SupplyKeeper, bondDenom string) MinSelfDelegationDecorator {
	return MinSelfDelegationDecorator{supply: supply, bondDenom: bondDenom}
}

// AnteHandle enforces the dynamic minimum validator self-delegation. It is a
// no-op for any transaction that does not contain a MsgCreateValidator (e.g.
// Ethereum transactions), so it is safe to run ahead of the EVM ante chain.
func (d MinSelfDelegationDecorator) AnteHandle(ctx sdk.Context, tx sdk.Tx, simulate bool, next sdk.AnteHandler) (sdk.Context, error) {
	for _, msg := range tx.GetMsgs() {
		cv, ok := msg.(*stakingtypes.MsgCreateValidator)
		if !ok {
			continue
		}
		minStake := d.supply.GetSupply(ctx, d.bondDenom).Amount.Quo(minSelfDelegationDivisor)
		if cv.Value.Denom != d.bondDenom {
			return ctx, sdkerrors.ErrInvalidRequest.Wrapf("validator self-delegation must be denominated in %s", d.bondDenom)
		}
		if cv.Value.Amount.LT(minStake) {
			return ctx, sdkerrors.ErrInsufficientFunds.Wrapf(
				"validator self-delegation %s%s is below the required minimum %s%s (0.01%% of total supply)",
				cv.Value.Amount.String(), d.bondDenom, minStake.String(), d.bondDenom)
		}
		if cv.MinSelfDelegation.LT(minStake) {
			return ctx, sdkerrors.ErrInvalidRequest.Wrapf(
				"min_self_delegation %s is below the required minimum %s (0.01%% of total supply)",
				cv.MinSelfDelegation.String(), minStake.String())
		}
	}
	return next(ctx, tx, simulate)
}

// NewAnteHandler wraps the Cosmos EVM ante handler (which routes Ethereum vs
// Cosmos-SDK transactions to their respective decorator chains) with the Abakos
// dynamic minimum validator self-delegation check. The self-delegation check
// runs first; it only acts on MsgCreateValidator, so ordinary Cosmos txs and all
// Ethereum txs pass straight through to the standard EVM/Cosmos ante chain.
func NewAnteHandler(evmOptions evmante.HandlerOptions, supplyKeeper SupplyKeeper, bondDenom string) (sdk.AnteHandler, error) {
	if err := evmOptions.Validate(); err != nil {
		return nil, err
	}
	if supplyKeeper == nil {
		return nil, sdkerrors.ErrLogic.Wrap("supply keeper is required for ante builder")
	}
	if bondDenom == "" {
		return nil, sdkerrors.ErrLogic.Wrap("bond denom is required for ante builder")
	}

	evmAnteHandler := evmante.NewAnteHandler(evmOptions)
	minSelfDelegation := NewMinSelfDelegationDecorator(supplyKeeper, bondDenom)

	return func(ctx sdk.Context, tx sdk.Tx, sim bool) (sdk.Context, error) {
		return minSelfDelegation.AnteHandle(ctx, tx, sim, evmAnteHandler)
	}, nil
}
