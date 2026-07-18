package chaincfg

import (
	"time"

	"github.com/rexmarlon/abakos/node/params"
)

// TestNetChainID is the planned public testnet identifier (T1).
const TestNetChainID = "abakos-testnet-1"

// GenesisParams holds values baked into the testnet genesis block (pre-audit).
type GenesisParams struct {
	ChainID     string
	NetworkName string
	Timestamp   time.Time
	Bits        uint32
	CoinbaseTag string
}

// TestNetGenesis returns draft genesis parameters for T1.
// Genesis hash is computed when the first abkd node mines block 0 with these params.
func TestNetGenesis() GenesisParams {
	return GenesisParams{
		ChainID:     TestNetChainID,
		NetworkName: TestNetName,
		Timestamp:   TestNetGenesisTime,
		Bits:        SimNetEasyBits, // raise before public T1
		CoinbaseTag: GenesisCoinbaseTag,
	}
}

// GenesisHeaderFields returns economic metadata embedded in genesis coinbase (T1).
func GenesisHeaderFields() map[string]any {
	return map[string]any{
		"chain_id":            TestNetChainID,
		"symbol":              params.Symbol,
		"max_supply_aba":      params.MaxSupplyABA,
		"target_block_sec":    params.TargetBlockSeconds,
		"reward_floor_bps":    params.RewardFloorBps,
		"marketplace_fee_bps": params.MarketplaceFeeBps,
		"halving_years":       params.HalvingYears,
	}
}
