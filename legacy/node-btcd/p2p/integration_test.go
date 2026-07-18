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

func TestBtcdP2PTwoNodeSync(t *testing.T) {
	chain.ResetAbakosSimNetBtcdParamsForTest()
	fork.SetVerifier(pouw.CPUGEMMVerifier{})
	chain.SetSimNetVerifier(pouw.CPUGEMMVerifier{})

	root := t.TempDir()
	seedDir := filepath.Join(root, "seed")
	followDir := filepath.Join(root, "follower")

	seed, err := p2p.NewServer(p2p.Config{
		DataDir:  seedDir,
		Listen:   "127.0.0.1:0",
		MaxPeers: 4,
		Verifier: pouw.CPUGEMMVerifier{},
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	seed.Start()
	defer seed.Stop()

	listenAddr := seed.ListenAddr()
	if listenAddr == "" {
		t.Fatal("seed has no listen address")
	}

	follower, err := p2p.NewServer(p2p.Config{
		DataDir:  followDir,
		Connect:  []string{listenAddr},
		MaxPeers: 4,
		Verifier: pouw.CPUGEMMVerifier{},
	})
	if err != nil {
		t.Fatalf("follower: %v", err)
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
	for time.Now().Before(deadline) {
		if follower.BestHeight() >= 3 {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
	t.Fatalf("seed height=%d follower height=%d want >=3", seed.BestHeight(), follower.BestHeight())
}
