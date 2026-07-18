package p2p

import (
	"bytes"
	"path/filepath"
	"testing"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/database"
	"github.com/btcsuite/btcd/wire"
	"github.com/rexmarlon/abakos/node/chain"
	"github.com/rexmarlon/abakos/node/fork"
	"github.com/rexmarlon/abakos/node/pouw"
)

func TestMinedBlockDBRoundTripMerkle(t *testing.T) {
	chain.ResetAbakosSimNetBtcdParamsForTest()
	fork.SetVerifier(pouw.CPUGEMMVerifier{})
	chain.SetSimNetVerifier(pouw.CPUGEMMVerifier{})

	srv, err := NewServer(Config{
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

	best := srv.chain.BestSnapshot()
	var blockBytes []byte
	err = srv.db.View(func(tx database.Tx) error {
		var err error
		blockBytes, err = tx.FetchBlock(&best.Hash)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}

	var msg wire.MsgBlock
	if err := msg.Deserialize(bytes.NewReader(blockBytes)); err != nil {
		t.Fatal(err)
	}
	block := btcutil.NewBlock(&msg)
	calc := blockchain.CalcMerkleRoot(block.Transactions(), false)
	if !msg.Header.MerkleRoot.IsEqual(&calc) {
		t.Fatalf("db merkle mismatch header=%s calc=%s", msg.Header.MerkleRoot, calc)
	}

	// NewBlockFromBlockAndBytes must not be used for Abakos blocks on the wire path.
	fromBytes := btcutil.NewBlockFromBlockAndBytes(&msg, blockBytes)
	wrong := blockchain.CalcMerkleRoot(fromBytes.Transactions(), false)
	if msg.Header.MerkleRoot.IsEqual(&wrong) {
		t.Fatal("expected NewBlockFromBlockAndBytes to break Abakos merkle calc")
	}
}
