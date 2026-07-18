// Package economics implements Abakos' core economic functions (emission,
// reward-split, fee-split) on top of the constants in package params. Kept
// pure (no chain deps) so the rules are easy to test and audit.
package economics

import (
	"fmt"

	"github.com/rexmarlon/abakos/node/params"
)

// AnnualEmissionABA returns the ABA emitted in the given 1-based year under
// the Bitcoin-style halving schedule.
func AnnualEmissionABA(year int) float64 {
	if year < 1 {
		return 0
	}
	epoch := (year - 1) / params.HalvingYears
	e := params.FirstYearEmissionABA()
	for i := 0; i < epoch; i++ {
		e /= 2
	}
	return e
}

// CumulativeEmissionABA returns total ABA emitted through the given year.
// As year -> infinity this converges exactly to params.MiningSupplyABA().
func CumulativeEmissionABA(year int) float64 {
	var sum float64
	for y := 1; y <= year; y++ {
		sum += AnnualEmissionABA(y)
	}
	return sum
}

// SplitFee splits the marketplace fee charged on `amount` (in base units)
// into the treasury and burn portions. By construction treasury+burn equals
// the total fee (no rounding dust is lost).
func SplitFee(amount int64) (treasury, burn int64) {
	if amount <= 0 {
		return 0, 0
	}
	total := amount * int64(params.MarketplaceFeeBps) / 10000
	burn = total * int64(params.FeeBurnBps) / int64(params.MarketplaceFeeBps)
	treasury = total - burn
	return treasury, burn
}

// BlockReward returns the ABA paid for a block given the base subsidy and the
// useful_ratio in [0,1] (see docs/spec-marketplace.md). The unrewarded
// remainder (base - reward) is burned.
func BlockReward(baseSubsidy, usefulRatio float64) float64 {
	return baseSubsidy * params.RewardForUsefulRatio(usefulRatio)
}

// CoinbaseSubsidy returns the consensus coinbase amount (base units / satoshis)
// for a block with the given base subsidy and useful_ratio in basis points.
// The unrewarded remainder is burned (not paid in the coinbase).
//
// Formula: base * (FLOOR + (1-FLOOR) * useful_bps/10000), integer floor.
func CoinbaseSubsidy(baseSubsidy int64, usefulBps uint16) int64 {
	if baseSubsidy <= 0 {
		return 0
	}
	if usefulBps > 10000 {
		usefulBps = 10000
	}
	// reward = base * (floor_bps + (10000-floor_bps)*useful_bps/10000) / 10000
	//       = base * (floor_bps*10000 + (10000-floor_bps)*useful_bps) / 10000 / 10000
	num := int64(params.RewardFloorBps)*10000 + int64(10000-params.RewardFloorBps)*int64(usefulBps)
	return baseSubsidy * num / 100_000_000
}

// ValidateCoinbaseSubsidy checks that paid equals the consensus reward for
// usefulBps. Returns an error if the miner over- or under-pays relative to
// the enforced split (fees are handled by the caller).
func ValidateCoinbaseSubsidy(paid, baseSubsidy int64, usefulBps uint16) error {
	want := CoinbaseSubsidy(baseSubsidy, usefulBps)
	if paid != want {
		return fmt.Errorf("economics: coinbase %d != expected %d (base=%d useful_bps=%d)",
			paid, want, baseSubsidy, usefulBps)
	}
	return nil
}
