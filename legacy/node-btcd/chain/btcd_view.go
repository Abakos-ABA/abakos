package chain

import "github.com/btcsuite/btcd/blockchain"

// BtcdView exposes the btcd BlockChain for the explorer API.
type BtcdView struct {
	bc           *blockchain.BlockChain
	verifierName string
}

// NewBtcdView wraps a btcd main chain for read-only explorer queries.
func NewBtcdView(bc *blockchain.BlockChain, verifierName string) *BtcdView {
	return &BtcdView{bc: bc, verifierName: verifierName}
}

// Blocks returns main-chain blocks from genesis through the current tip.
func (v *BtcdView) Blocks() []*Block {
	best := v.bc.BestSnapshot()
	out := make([]*Block, 0, best.Height+1)
	for h := int32(0); h <= best.Height; h++ {
		bb, err := v.bc.BlockByHeight(h)
		if err != nil {
			break
		}
		out = append(out, BlockFromBtcutil(bb))
	}
	return out
}

// ComputeStats returns explorer-facing metrics (T0: all blocks).
func (v *BtcdView) ComputeStats() Stats {
	return statsFromBlocks(v.Blocks(), v.verifierName)
}

func statsFromBlocks(blocks []*Block, verifierName string) Stats {
	var weighted float64
	total := uint64(len(blocks))
	for _, b := range blocks {
		weighted += float64(b.Header.UsefulRatioBps)
	}
	pct := 0.0
	if total > 0 {
		pct = weighted / float64(total) / 100.0
	}
	height := uint64(0)
	if len(blocks) > 0 {
		height = blocks[len(blocks)-1].Height
	}
	return Stats{
		Height:          height,
		BlockCount:      len(blocks),
		UsefulPct24h:    pct,
		UsefulPctAll:    pct,
		ActiveMiners24h: 0,
		Verifier:        verifierName,
	}
}
