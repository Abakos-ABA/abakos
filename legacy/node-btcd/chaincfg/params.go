// Package chaincfg holds Abakos network parameters derived from node/params and
// btcd's chaincfg.Params. Full fork wiring lands in T0 week 2+.
package chaincfg

import (
	"fmt"
	"time"

	btcchaincfg "github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/wire"
	"github.com/rexmarlon/abakos/node/params"
)

// TestNetName is the public incentivized testnet (T1).
const TestNetName = "abakos-testnet"

// SimNetName is the local developer network (T0).
const SimNetName = "abakos-simnet"

// TestNetGenesisTime is the planned testnet genesis timestamp (UTC).
// Update before T1 launch.
var TestNetGenesisTime = time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC)

// SimNetGenesisTime is used for local two-node simnet experiments.
var SimNetGenesisTime = time.Date(2026, 6, 30, 12, 0, 0, 0, time.UTC)

// SimNet returns btcd simnet params as the T0 baseline. Abakos-specific wire
// format (ProofCommitment, certificates) will use a replace-forked btcd later.
func SimNet() *btcchaincfg.Params {
	p := btcchaincfg.SimNetParams
	return &p
}

// TestNet returns a copy of simnet params with Abakos economic metadata applied.
// Network magic, seeds, and genesis block are finalized before T1.
func TestNet() *btcchaincfg.Params {
	p := btcchaincfg.SimNetParams
	p.Name = TestNetName
	p.Net = wire.TestNet3 // placeholder magic until custom network params land
	return &p
}

// TargetBlockTime returns the Abakos block target interval.
func TargetBlockTime() time.Duration {
	return time.Duration(params.TargetBlockSeconds) * time.Second
}

// SimNetEasyBits is the compact difficulty for local T0 mining (very easy).
const SimNetEasyBits uint32 = 0x1f00ffff

// GenesisCoinbaseTag is embedded in the genesis coinbase for identification.
const GenesisCoinbaseTag = "Abakos genesis: compute that pays for itself"

// GenesisHashPlaceholder is zero until the real genesis block is mined (T0).
var GenesisHashPlaceholder = chainhash.Hash{}

// Summary returns a short human-readable network snapshot.
func Summary() string {
	return fmt.Sprintf("%s · target %s · reward floor %.0f%% · symbol %s",
		TestNetName, TargetBlockTime(), float64(params.RewardFloorBps)/100.0, params.Symbol)
}
