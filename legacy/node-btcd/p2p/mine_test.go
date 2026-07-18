package p2p_test

import (
	"path/filepath"
	"testing"
	"time"

	"github.com/rexmarlon/abakos/node/chain"
	"github.com/rexmarlon/abakos/node/fork"
	"github.com/rexmarlon/abakos/node/p2p"
	"github.com/rexmarlon/abakos/node/pouw"
)

func TestBtcdP2PSingleNodeMines(t *testing.T) {
	chain.ResetAbakosSimNetBtcdParamsForTest()
	fork.SetVerifier(pouw.CPUGEMMVerifier{})
	chain.SetSimNetVerifier(pouw.CPUGEMMVerifier{})

	dir := filepath.Join(t.TempDir(), "solo")
	srv, err := p2p.NewServer(p2p.Config{
		DataDir:   dir,
		Mine:      true,
		MaxBlocks: 3,
		MaxPeers:  2,
		Verifier:  pouw.CPUGEMMVerifier{},
	})
	if err != nil {
		t.Fatalf("new: %v", err)
	}
	srv.Start()
	defer srv.Stop()

	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		if srv.BestHeight() >= 2 {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	t.Fatalf("height=%d want >=2", srv.BestHeight())
}
