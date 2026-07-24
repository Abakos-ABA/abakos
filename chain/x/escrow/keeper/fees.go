package keeper

import (
	sdk "github.com/cosmos/cosmos-sdk/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"

	"pkg.akt.dev/go/node/escrow/module"
)

// Marketplace settlement fee, per docs/fee-model.md: every provider payout is
// taxed 3% — 1% stakers, 1% treasury, 1% burn — and the provider receives the
// remaining 97% plus any rounding dust. Deposit refunds (bid collateral,
// unused tenant deposits) are exempt and never route through here.
//
// The staker share goes to the fee_collector module account; the standard
// distribution begin-blocker pays it out to validators and delegators on the
// next block. Burn uses the same keyless 0x…dEaD account as the idle-mining
// split, so all burn accounting is visible at one address (a real
// supply-reducing burn stays a mainnet TODO, see docs/fee-model.md).
//
// Sandbox: destination addresses are constants; on mainnet these move to
// governance params.
const (
	settlementFeeSharePct = 1 // per beneficiary: stakers, treasury, burn

	settlementBurnAddr     = "abakos1qqqqqqqqqqqqqqqqqqqqqqqqqqqqph4djeny4w" // bech32 of 0x…dEaD
	settlementTreasuryAddr = "abakos1stjyg77cxlp5k6fk09hf9yl8l58495wm5hltmc" // genesis treasury account
)

// settlementPayout transfers accrued lease earnings out of the escrow module:
// 97% to the provider, 1% each to stakers (via fee_collector), treasury and
// burn. Amounts below 100 base units pay the provider in full (each 1% share
// floors to zero).
func (k *keeper) settlementPayout(ctx sdk.Context, owner sdk.AccAddress, earnings sdk.Coin) error {
	share := earnings.Amount.QuoRaw(100).MulRaw(settlementFeeSharePct)
	if share.IsZero() {
		return k.bkeeper.SendCoinsFromModuleToAccount(ctx, module.ModuleName, owner, sdk.NewCoins(earnings))
	}

	feeCoins := sdk.NewCoins(sdk.NewCoin(earnings.Denom, share))
	providerCoin := sdk.NewCoin(earnings.Denom, earnings.Amount.Sub(share.MulRaw(3)))

	if err := k.bkeeper.SendCoinsFromModuleToModule(ctx, module.ModuleName, authtypes.FeeCollectorName, feeCoins); err != nil {
		return err
	}

	for _, bech := range []string{settlementTreasuryAddr, settlementBurnAddr} {
		dest, err := k.ac.StringToBytes(bech)
		if err != nil {
			return err
		}
		if err := k.bkeeper.SendCoinsFromModuleToAccount(ctx, module.ModuleName, dest, feeCoins); err != nil {
			return err
		}
	}

	return k.bkeeper.SendCoinsFromModuleToAccount(ctx, module.ModuleName, owner, sdk.NewCoins(providerCoin))
}
