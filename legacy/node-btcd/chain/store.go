package chain

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/rexmarlon/abakos/node/pouw"
)

const chainFile = "chain.json"

// Snapshot is the on-disk chain format for --datadir.
type Snapshot struct {
	Verifier string          `json:"verifier"`
	Bits     uint32          `json:"bits"`
	Blocks   []snapshotBlock `json:"blocks"`
}

type snapshotBlock struct {
	Header pouw.Header `json:"header"`
	Proof  string      `json:"proof_hex"`
	Height uint64      `json:"height"`
}

// Save writes the chain to datadir/chain.json.
func (c *Chain) Save(datadir string) error {
	if err := os.MkdirAll(datadir, 0o755); err != nil {
		return err
	}
	snap := Snapshot{
		Verifier: c.verifierName,
		Bits:     c.bits,
		Blocks:   make([]snapshotBlock, 0, len(c.blocks)),
	}
	for _, b := range c.blocks {
		snap.Blocks = append(snap.Blocks, snapshotBlock{
			Header: b.Header,
			Proof:  hex.EncodeToString(b.Proof),
			Height: b.Height,
		})
	}
	data, err := json.MarshalIndent(snap, "", "  ")
	if err != nil {
		return err
	}
	path := filepath.Join(datadir, chainFile)
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// LoadSnapshot reads datadir/chain.json.
func LoadSnapshot(datadir string) (*Snapshot, error) {
	path := filepath.Join(datadir, chainFile)
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var snap Snapshot
	if err := json.Unmarshal(data, &snap); err != nil {
		return nil, err
	}
	return &snap, nil
}

// Restore imports blocks from a snapshot into a fresh chain.
func (c *Chain) Restore(snap *Snapshot) error {
	if snap.Verifier != c.verifierName {
		return fmt.Errorf("chain: verifier mismatch (disk %q, node %q)", snap.Verifier, c.verifierName)
	}
	if snap.Bits != c.bits {
		return fmt.Errorf("chain: difficulty bits mismatch")
	}
	for _, sb := range snap.Blocks {
		proof, err := hex.DecodeString(sb.Proof)
		if err != nil {
			return err
		}
		b := &Block{Header: sb.Header, Proof: proof, Height: sb.Height}
		if err := c.ImportBlock(b); err != nil {
			return fmt.Errorf("restore height %d: %w", sb.Height, err)
		}
	}
	return nil
}

// Stats summarizes the chain for explorer/API.
type Stats struct {
	Height          uint64  `json:"height"`
	BlockCount      int     `json:"block_count"`
	UsefulPct24h    float64 `json:"useful_pct_24h"`
	UsefulPctAll    float64 `json:"useful_pct_all"`
	ActiveMiners24h int     `json:"active_miners_24h"`
	Verifier        string  `json:"verifier"`
}

// ComputeStats returns explorer-facing metrics (T0: all blocks, no real 24h window).
func (c *Chain) ComputeStats() Stats {
	return statsFromBlocks(c.Blocks(), c.verifierName)
}
