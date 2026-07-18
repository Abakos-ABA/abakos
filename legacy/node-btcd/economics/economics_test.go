package economics

import (
	"math"
	"testing"

	"github.com/rexmarlon/abakos/node/params"
)

func TestRewardForUsefulRatio(t *testing.T) {
	cases := []struct {
		in, want float64
	}{
		{0, 0.25}, {0.5, 0.625}, {1, 1.0}, {-5, 0.25}, {5, 1.0},
	}
	for _, c := range cases {
		if got := params.RewardForUsefulRatio(c.in); math.Abs(got-c.want) > 1e-9 {
			t.Errorf("RewardForUsefulRatio(%v) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestHalving(t *testing.T) {
	first := params.FirstYearEmissionABA()
	for y := 1; y <= params.HalvingYears; y++ {
		if math.Abs(AnnualEmissionABA(y)-first) > 1e-6 {
			t.Fatalf("year %d: got %v, want first-epoch %v", y, AnnualEmissionABA(y), first)
		}
	}
	if got := AnnualEmissionABA(params.HalvingYears + 1); math.Abs(got-first/2) > 1e-6 {
		t.Fatalf("after first halving: got %v, want %v", got, first/2)
	}
}

func TestCumulativeConverges(t *testing.T) {
	mining := float64(params.MiningSupplyABA())
	cum := CumulativeEmissionABA(200)
	if cum > mining+1 {
		t.Fatalf("cumulative %.0f exceeds mining supply %.0f", cum, mining)
	}
	if (mining-cum)/mining > 0.005 {
		t.Fatalf("cumulative %.0f too far below mining supply %.0f", cum, mining)
	}
}

func TestAllocationSums(t *testing.T) {
	sum := 0
	for _, v := range params.Allocation {
		sum += v
	}
	if sum != 10000 {
		t.Fatalf("allocation sums to %d bps, want 10000", sum)
	}
}

func TestSplitFee(t *testing.T) {
	treasury, burn := SplitFee(1_000_000)
	if treasury+burn != 20_000 {
		t.Fatalf("treasury+burn = %d, want 20000 (2%% fee)", treasury+burn)
	}
	if treasury != 10_000 || burn != 10_000 {
		t.Fatalf("treasury=%d burn=%d, want 10000/10000", treasury, burn)
	}
	// no dust loss for an awkward amount
	tr, bn := SplitFee(1_234_567)
	total := int64(1_234_567) * int64(params.MarketplaceFeeBps) / 10000
	if tr+bn != total {
		t.Fatalf("dust lost: tr+bn=%d, total=%d", tr+bn, total)
	}
}

func TestBlockReward(t *testing.T) {
	if got := BlockReward(1000, 0); math.Abs(got-250) > 1e-9 {
		t.Fatalf("empty mining: got %v, want 250", got)
	}
	if got := BlockReward(1000, 1); math.Abs(got-1000) > 1e-9 {
		t.Fatalf("full useful: got %v, want 1000", got)
	}
}

func TestCoinbaseSubsidy(t *testing.T) {
	const base int64 = 5_000_000_000 // 50 ABA in satoshis
	if got := CoinbaseSubsidy(base, 0); got != base/4 {
		t.Fatalf("empty: got %d want %d", got, base/4)
	}
	if got := CoinbaseSubsidy(base, 10000); got != base {
		t.Fatalf("full: got %d want %d", got, base)
	}
	// 50% useful → 25% + 0.75*50% = 62.5%
	want := base * 6250 / 10000
	if got := CoinbaseSubsidy(base, 5000); got != want {
		t.Fatalf("half: got %d want %d", got, want)
	}
	if err := ValidateCoinbaseSubsidy(base, base, 0); err == nil {
		t.Fatal("full pay at useful=0 must fail")
	}
	if err := ValidateCoinbaseSubsidy(base/4, base, 0); err != nil {
		t.Fatal(err)
	}
	if err := ValidateCoinbaseSubsidy(base, base, 10000); err != nil {
		t.Fatal(err)
	}
}
