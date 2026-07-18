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

func TestBtcdP2PTwoNodeWireSync(t *testing.T) {
	chain.ResetAbakosSimNetBtcdParamsForTest()
	fork.SetVerifier(pouw.CPUGEMMVerifier{})
	chain.SetSimNetVerifier(pouw.CPUGEMMVerifier{})

	root := t.TempDir()
	seed, err := p2p.NewServer(p2p.Config{
		DataDir:  filepath.Join(root, "seed"),
		Listen:   "127.0.0.1:0",
		MaxPeers: 4,
		Verifier: pouw.CPUGEMMVerifier{},
	})
	if err != nil {
		t.Fatal(err)
	}
	seed.Start()
	defer seed.Stop()

	listenAddr := seed.ListenAddr()
	follower, err := p2p.NewServer(p2p.Config{
		DataDir:  filepath.Join(root, "follower"),
		Connect:  []string{listenAddr},
		MaxPeers: 4,
		Verifier: pouw.CPUGEMMVerifier{},
	})
	if err != nil {
		t.Fatal(err)
	}
	follower.Start()
	defer follower.Stop()

	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		if seed.PeerCount() >= 1 && follower.PeerCount() >= 1 {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if seed.PeerCount() < 1 || follower.PeerCount() < 1 {
		t.Fatalf("peers not connected: seed=%d follower=%d", seed.PeerCount(), follower.PeerCount())
	}

	for i := 0; i < 3; i++ {
		if err := seed.MineOne(); err != nil {
			t.Fatalf("mine: %v", err)
		}
		time.Sleep(500 * time.Millisecond)
	}

	deadline = time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		if follower.BestHeight() >= 3 {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	t.Fatalf("wire sync failed seed=%d follower=%d", seed.BestHeight(), follower.BestHeight())
}
