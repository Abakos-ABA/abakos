// Package usdcmeta fixes the bank denom metadata of the canonical Noble USDC
// IBC voucher. ibc-go auto-generates metadata on first receipt (display
// "transfer/channel-0/uusdc", symbol "UUSDC", a single denom unit with
// exponent 0), which makes the erc20 dynamic precompile report symbol "UUSDC"
// and 0 decimals. The precompile reads name/symbol/decimals live from bank
// metadata on every call, so overwriting the record is the complete fix; the
// ERC20 address (derived from the denom hash) does not change. ibc-go only
// writes metadata when none exists yet (transfer/keeper/relay.go), so the
// corrected record is never clobbered afterwards.
package usdcmeta

import (
	sdk "github.com/cosmos/cosmos-sdk/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"

	apptypes "pkg.akt.dev/node/v2/app/types"
	utypes "pkg.akt.dev/node/v2/upgrades/types"
)

// PatchHeight must be reached only after the patched binary is running on the
// validator; the swap is a manual binary replacement, not a gov upgrade.
const PatchHeight = 185_000

const usdcIBCDenom = "ibc/8E27BA2D5493AF5636760E354E46004562C46AB7EC0CC4C1CA14E9E20E2545B5"

func init() {
	utypes.RegisterHeightPatch(PatchHeight, patch{})
}

type patch struct{}

func (patch) Name() string {
	return "usdc-denom-metadata"
}

func (patch) Begin(ctx sdk.Context, keepers *apptypes.AppKeepers) {
	// The erc20 precompile resolves decimals by matching the last "/" segment
	// of Display against the denom units, so Display "usdc" + unit
	// {usdc, exponent 6} yields decimals()==6, Symbol "USDC", Name "USD Coin".
	keepers.Cosmos.Bank.SetDenomMetaData(ctx, banktypes.Metadata{
		Description: "Circle USDC issued on Noble, received over IBC (transfer/channel-0/uusdc).",
		DenomUnits: []*banktypes.DenomUnit{
			{Denom: usdcIBCDenom, Exponent: 0, Aliases: []string{"uusdc"}},
			{Denom: "usdc", Exponent: 6},
		},
		Base:    usdcIBCDenom,
		Display: "usdc",
		Name:    "USD Coin",
		Symbol:  "USDC",
	})
}
