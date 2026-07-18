package chain_test

import (
	"testing"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/database"
	_ "github.com/btcsuite/btcd/database/ffldb"
	"github.com/btcsuite/btcd/wire"
	"github.com/rexmarlon/abakos/node/chain"
	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/fork"
	"github.com/rexmarlon/abakos/node/pouw"
)

func TestBtcdProcessMinedBlock(t *testing.T) {
	chain.ResetAbakosSimNetBtcdParamsForTest()
	fork.SetVerifier(pouw.CPUGEMMVerifier{})
	chain.SetSimNetVerifier(pouw.CPUGEMMVerifier{})

	params, err := chain.AbakosSimNetBtcdParams()
	if err != nil {
		t.Fatal(err)
	}
	db, err := database.Create("ffldb", t.TempDir(), wire.SimNet)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	bc, err := blockchain.New(&blockchain.Config{
		DB:          db,
		ChainParams: params,
		TimeSource:  blockchain.NewMedianTime(),
	})
	if err != nil {
		t.Fatal(err)
	}

	best := bc.BestSnapshot()
	var prev [32]byte
	copy(prev[:], best.Hash[:])
	height := best.Height + 1
	base := blockchain.CalcBlockSubsidy(height, params)
	subsidy := chain.AdjustedCoinbaseSubsidy(base, 0)
	header := pouw.Header{
		Version:    chain.AbakosBlockVersion,
		PrevBlock:  prev,
		Timestamp:  best.MedianTime.Add(chaincfg.TargetBlockTime()),
		Bits:       chaincfg.SimNetEasyBits,
		MerkleRoot: chain.CoinbaseMerkleRoot(height, subsidy),
	}
	v := pouw.CPUGEMMVerifier{}
	mined, err := chain.Mine(header, v)
	if err != nil {
		t.Fatal(err)
	}
	msg, err := chain.BuildBtcdMsgBlock(best.Hash, mined.Header, mined.Proof, height, subsidy)
	if err != nil {
		t.Fatal(err)
	}
	block := btcutil.NewBlock(msg)
	block.SetHeight(height)

	if err = blockchain.CheckProofOfUsefulWork(block, params.PowLimit); err != nil {
		t.Fatalf("CheckProofOfUsefulWork: %v", err)
	}
	_, _, err = bc.ProcessBlock(block, blockchain.BFNone)
	if err != nil {
		t.Fatalf("ProcessBlock: %v", err)
	}
	if bc.BestSnapshot().Height != height {
		t.Fatalf("height %d", bc.BestSnapshot().Height)
	}
}
