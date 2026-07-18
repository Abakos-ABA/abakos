package chain_test

import (
	"path/filepath"
	"testing"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/database"
	_ "github.com/btcsuite/btcd/database/ffldb"
	"github.com/btcsuite/btcd/wire"
	"github.com/rexmarlon/abakos/node/chain"
	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/fork"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/p2p"
	"github.com/rexmarlon/abakos/node/pouw"
)

func TestBtcdViewExplorerAPI(t *testing.T) {
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
	const usefulBps uint16 = 5000
	jobID := jobs.Global.RegisterDemoFunded("btcd-view-test")
	base := blockchain.CalcBlockSubsidy(height, params)
	subsidy := chain.AdjustedCoinbaseSubsidy(base, usefulBps)
	header := pouw.Header{
		Version:         chain.AbakosBlockVersion,
		PrevBlock:       prev,
		Timestamp:       best.MedianTime.Add(chaincfg.TargetBlockTime()),
		Bits:            chaincfg.SimNetEasyBits,
		MerkleRoot:      chain.CoinbaseMerkleRoot(height, subsidy),
		UsefulRatioBps:  usefulBps,
		ProofCommitment: jobID,
	}
	mined, err := chain.Mine(header, pouw.CPUGEMMVerifier{})
	if err != nil {
		t.Fatal(err)
	}
	msg, err := chain.BuildBtcdMsgBlock(best.Hash, mined.Header, mined.Proof, height, subsidy)
	if err != nil {
		t.Fatal(err)
	}
	block := btcutil.NewBlock(msg)
	block.SetHeight(height)
	if _, _, err = bc.ProcessBlock(block, blockchain.BFNone); err != nil {
		t.Fatal(err)
	}

	view := chain.NewBtcdView(bc, "gemm")
	stats := view.ComputeStats()
	if stats.Height != uint64(height) {
		t.Fatalf("height %d want %d", stats.Height, height)
	}
	if stats.BlockCount != int(height)+1 {
		t.Fatalf("block_count %d", stats.BlockCount)
	}
	blocks := view.Blocks()
	if len(blocks) != int(height)+1 {
		t.Fatalf("blocks len %d", len(blocks))
	}
	tip := blocks[len(blocks)-1]
	if tip.Height != uint64(height) {
		t.Fatalf("tip height %d", tip.Height)
	}
	if tip.Header.UsefulRatioBps != 5000 {
		t.Fatalf("useful bps %d", tip.Header.UsefulRatioBps)
	}
}

func TestBtcdViewFromP2PServer(t *testing.T) {
	chain.ResetAbakosSimNetBtcdParamsForTest()
	fork.SetVerifier(pouw.CPUGEMMVerifier{})
	chain.SetSimNetVerifier(pouw.CPUGEMMVerifier{})

	srv, err := p2p.NewServer(p2p.Config{
		DataDir:  filepath.Join(t.TempDir(), "solo"),
		MaxPeers: 2,
		Verifier: pouw.CPUGEMMVerifier{},
	})
	if err != nil {
		t.Fatal(err)
	}
	srv.Start()
	defer srv.Stop()
	if err := srv.MineOne(); err != nil {
		t.Fatal(err)
	}

	view := chain.NewBtcdView(srv.Chain(), "gemm")
	if view.ComputeStats().Height != 1 {
		t.Fatalf("height %d", view.ComputeStats().Height)
	}
}
