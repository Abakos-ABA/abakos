package sdkutil

import (
	"cosmossdk.io/math"
	sdktypes "github.com/cosmos/cosmos-sdk/types"
)

// Abakos rebrand: identifiers are kept (so node code still compiles) but the
// string values are the Abakos brand: base denom uaba (display ABA) and bech32
// prefix abakos*.
const (
	DenomAkt  = "aba"  // 1 ABA
	DenomMakt = "maba" // 10^-3 ABA
	DenomUakt = "uaba" // 10^-6 ABA (base denom)

	DenomAct  = "act"  // 1act
	DenomMact = "mact" // 10^-3act
	DenomUact = "uact" // 10^-6act

	DenomUSD  = "usd"  // 1usd
	DenomMusd = "musd" // 10^-3usd
	DenomUusd = "uusd" // 10^-6usd

	BondDenom = DenomUakt

	DenomMExponent = 3
	DenomUExponent = 6

	Bech32PrefixAccAddr = "abakos"
	Bech32PrefixAccPub  = "abakospub"

	Bech32PrefixValAddr = "abakosvaloper"
	Bech32PrefixValPub  = "abakosvaloperpub"

	Bech32PrefixConsAddr = "abakosvalcons"
	Bech32PrefixConsPub  = "abakosvalconspub"
)

func init() {
	aktUnit := math.LegacyOneDec()                           // 1 (base denom unit)
	maktUnit := math.LegacyNewDecWithPrec(1, DenomMExponent) // 10^-6 (micro)
	uaktUnit := math.LegacyNewDecWithPrec(1, DenomUExponent) // 10^-6 (micro)

	actUnit := math.LegacyOneDec()                           // 1 (base denom unit)
	mactUnit := math.LegacyNewDecWithPrec(1, DenomMExponent) // 10^-6 (micro)
	uactUnit := math.LegacyNewDecWithPrec(1, DenomUExponent) // 10^-6 (micro)

	usdUnit := math.LegacyOneDec()                           // 1 (base denom unit)
	musdUnit := math.LegacyNewDecWithPrec(1, DenomMExponent) // 10^-6 (micro)
	uusdUnit := math.LegacyNewDecWithPrec(1, DenomUExponent) // 10^-6 (micro)

	err := sdktypes.RegisterDenom(DenomAkt, aktUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomMakt, maktUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomUakt, uaktUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomAct, actUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomMact, mactUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomUact, uactUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomUSD, usdUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomMusd, musdUnit)
	if err != nil {
		panic(err)
	}

	err = sdktypes.RegisterDenom(DenomUusd, uusdUnit)
	if err != nil {
		panic(err)
	}

}
