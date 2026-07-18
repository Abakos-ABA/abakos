package chain

import (
	"testing"

	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/pouw"
)

func TestGenesisAndMineFive(t *testing.T) {
	c := New(pouw.SHA256StubVerifier{}, chaincfg.SimNetEasyBits)
	gen, err := c.InitGenesis()
	if err != nil {
		t.Fatalf("genesis: %v", err)
	}
	if gen.Height != 0 {
		t.Fatalf("genesis height %d", gen.Height)
	}
	info := RewardInfo(gen)
	if info.UsefulRatio != 0 || info.RewardABA >= info.BaseSubsidyABA {
		t.Fatalf("genesis reward: %+v", info)
	}

	for i := 1; i <= 5; i++ {
		b, err := c.MineNext(0)
		if err != nil {
			t.Fatalf("mine %d: %v", i, err)
		}
		if b.Height != uint64(i) {
			t.Fatalf("height %d want %d", b.Height, i)
		}
		if b.Header.PrevBlock != c.Blocks()[i-1].Hash() {
			t.Fatal("prev hash link broken")
		}
	}
	if c.Len() != 6 {
		t.Fatalf("len %d want 6", c.Len())
	}
}

func TestUsefulRatioReward(t *testing.T) {
	c := New(pouw.SHA256StubVerifier{}, chaincfg.SimNetEasyBits)
	if _, err := c.InitGenesis(); err != nil {
		t.Fatal(err)
	}
	b, err := c.MineNext(10000) // 100% useful, auto-registers demo job
	if err != nil {
		t.Fatal(err)
	}
	info := RewardInfo(b)
	if info.UsefulRatio != 1 {
		t.Fatalf("ratio %v", info.UsefulRatio)
	}
	if info.RewardABA < info.BaseSubsidyABA*0.99 {
		t.Fatalf("full useful should pay ~100%%: %+v", info)
	}
	if b.Header.ProofCommitment == ([32]byte{}) {
		t.Fatal("useful block must commit a job")
	}
}

func TestUsefulWithoutJobRejected(t *testing.T) {
	c := New(pouw.SHA256StubVerifier{}, chaincfg.SimNetEasyBits)
	r := jobs.NewRegistry()
	c.SetJobRegistry(r)
	if _, err := c.InitGenesis(); err != nil {
		t.Fatal(err)
	}
	parent := c.Tip()
	ts := parent.Header.Timestamp.Add(chaincfg.TargetBlockTime())
	header := pouw.Header{
		Version:        AbakosBlockVersion,
		PrevBlock:      parent.Hash(),
		Timestamp:      ts,
		Bits:           chaincfg.SimNetEasyBits,
		UsefulRatioBps: 5000,
		// ProofCommitment left zero → must fail
	}
	block, err := Mine(header, pouw.SHA256StubVerifier{})
	if err != nil {
		t.Fatal(err)
	}
	block.Height = 1
	if err := c.ImportBlock(block); err == nil {
		t.Fatal("expected reject for useful_ratio without job")
	}
}
