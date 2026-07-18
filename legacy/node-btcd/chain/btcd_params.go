package chain

import (
	"fmt"
	"sync"

	"github.com/btcsuite/btcd/blockchain"
	btcchaincfg "github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/pouw"
)

var (
	btcdSimNetOnce  sync.Once
	btcdSimNet      *btcchaincfg.Params
	btcdSimNetErr   error
	btcdSimVerifier pouw.WorkVerifier = pouw.CPUGEMMVerifier{}
)

// SetSimNetVerifier selects the verifier used to mine the cached simnet genesis.
func SetSimNetVerifier(v pouw.WorkVerifier) {
	btcdSimVerifier = v
}

// AbakosSimNetBtcdParams returns btcd simnet params with Abakos PoUW genesis.
func AbakosSimNetBtcdParams() (*btcchaincfg.Params, error) {
	btcdSimNetOnce.Do(func() {
		btcdSimNet, btcdSimNetErr = buildAbakosSimNetBtcdParams(btcdSimVerifier)
	})
	return btcdSimNet, btcdSimNetErr
}

func buildAbakosSimNetBtcdParams(verifier pouw.WorkVerifier) (*btcchaincfg.Params, error) {
	if verifier == nil {
		verifier = pouw.CPUGEMMVerifier{}
	}
	genesisHeader := pouw.Header{
		Version:        AbakosBlockVersion,
		Timestamp:      chaincfg.SimNetGenesisTime,
		Bits:           chaincfg.SimNetEasyBits,
		UsefulRatioBps: 0,
	}
	p := btcchaincfg.SimNetParams
	base0 := blockchain.CalcBlockSubsidy(0, &p)
	subsidy0 := AdjustedCoinbaseSubsidy(base0, 0)
	genesisHeader.MerkleRoot = CoinbaseMerkleRoot(0, subsidy0)
	mined, err := Mine(genesisHeader, verifier)
	if err != nil {
		return nil, fmt.Errorf("chain: mine simnet genesis: %w", err)
	}
	msg, err := BuildBtcdMsgBlock(chainhash.Hash{}, mined.Header, mined.Proof, 0, subsidy0)
	if err != nil {
		return nil, err
	}
	hash := msg.BlockHash()

	p.Name = chaincfg.SimNetName
	p.TargetTimePerBlock = chaincfg.TargetBlockTime()
	p.GenesisBlock = msg
	p.GenesisHash = &hash
	return &p, nil
}

// ResetAbakosSimNetBtcdParamsForTest clears cached btcd simnet params.
func ResetAbakosSimNetBtcdParamsForTest() {
	btcdSimNetOnce = sync.Once{}
	btcdSimNet = nil
	btcdSimNetErr = nil
}
