package chain

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/pouw"
)

func TestSaveLoadRoundtrip(t *testing.T) {
	dir := t.TempDir()
	v := pouw.CPUGEMMVerifier{}
	c := NewNamed(v, "gemm", chaincfg.SimNetEasyBits)
	if _, err := c.InitGenesis(); err != nil {
		t.Fatal(err)
	}
	if _, err := c.MineNext(5000); err != nil {
		t.Fatal(err)
	}
	if err := c.Save(dir); err != nil {
		t.Fatal(err)
	}
	snap, err := LoadSnapshot(dir)
	if err != nil {
		t.Fatal(err)
	}
	c2 := NewNamed(v, "gemm", chaincfg.SimNetEasyBits)
	if err := c2.Restore(snap); err != nil {
		t.Fatal(err)
	}
	if c2.Len() != c.Len() {
		t.Fatalf("len %d want %d", c2.Len(), c.Len())
	}
	if c2.Tip().Hash() != c.Tip().Hash() {
		t.Fatal("tip hash mismatch")
	}
	if _, err := os.Stat(filepath.Join(dir, chainFile)); err != nil {
		t.Fatal(err)
	}
}
