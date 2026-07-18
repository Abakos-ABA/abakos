// Package params holds the consensus / economic constants for the Abakos
// (ABA) chain. These mirror the assumptions in /docs/03-tokenomics.md and
// /model/model.py. They are NOT final; calibrate before testnet genesis.
package params

import "fmt"

const (
	// Identity
	Symbol = "ABA"
	Name   = "Abakos"

	// Smallest unit: 1 ABA = 1e8 base units (like Bitcoin's satoshi).
	CoinDecimals  = 8
	BaseUnitPerABA = 100_000_000

	// Supply
	MaxSupplyABA = 2_100_000_000 // 2.1B ABA hard cap

	// Block production
	TargetBlockSeconds = 120 // ~2 min target

	// Emission: Bitcoin-style halving. First-epoch annual emission is fit so
	// cumulative emission converges to the mining allocation (70% of supply).
	HalvingYears = 4

	// Reward split (see docs/02 + spec-marketplace.md). Empty/random mining
	// earns RewardFloor of the block reward; fully paid+verified work earns
	// 100%. Values in basis points (1bp = 0.01%).
	RewardFloorBps = 2500 // 25%

	// Protocol fees on each marketplace settlement.
	MarketplaceFeeBps = 200 // 2% total
	FeeTreasuryBps    = 100 // 1% -> treasury
	FeeBurnBps        = 100 // 1% -> burn
)

// Allocation of the max supply (basis points; must sum to 10000).
var Allocation = map[string]int{
	"mining":            7000,
	"treasury":          1000,
	"team":              800,
	"liquidity_listing": 700,
	"ecosystem":         500,
}

// MiningSupplyABA returns the number of ABA emitted via mining over time.
func MiningSupplyABA() int64 {
	return int64(MaxSupplyABA) * int64(Allocation["mining"]) / 10000
}

// FirstYearEmissionABA fits the halving series so the infinite sum equals the
// mining allocation: total = firstAnnual * HalvingYears * 2.
func FirstYearEmissionABA() float64 {
	return float64(MiningSupplyABA()) / (float64(HalvingYears) * 2.0)
}

// RewardForUsefulRatio returns the block-reward multiplier in [floor,1] for a
// given useful_ratio in [0,1].
func RewardForUsefulRatio(usefulRatio float64) float64 {
	floor := float64(RewardFloorBps) / 10000.0
	if usefulRatio < 0 {
		usefulRatio = 0
	}
	if usefulRatio > 1 {
		usefulRatio = 1
	}
	return floor + (1.0-floor)*usefulRatio
}

// Summary returns a human-readable snapshot of the parameters.
func Summary() string {
	return fmt.Sprintf(
		"%s (%s)\n"+
			"  max supply        : %d ABA (decimals %d)\n"+
			"  block target      : %ds\n"+
			"  halving           : every %dy\n"+
			"  reward floor      : %.0f%% (empty mining)\n"+
			"  marketplace fee   : %.2f%% (%.2f%% treasury / %.2f%% burn)\n"+
			"  mining supply     : %d ABA\n"+
			"  yr1 emission (fit): %.0f ABA (~%.0f ABA/h)\n",
		Name, Symbol,
		MaxSupplyABA, CoinDecimals,
		TargetBlockSeconds,
		HalvingYears,
		float64(RewardFloorBps)/100.0,
		float64(MarketplaceFeeBps)/100.0, float64(FeeTreasuryBps)/100.0, float64(FeeBurnBps)/100.0,
		MiningSupplyABA(),
		FirstYearEmissionABA(), FirstYearEmissionABA()/365.0/24.0,
	)
}
