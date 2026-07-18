package chain

import (
	"fmt"

	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/consensus"
	"github.com/rexmarlon/abakos/node/economics"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/params"
	"github.com/rexmarlon/abakos/node/pouw"
)

// BlockRewardInfo holds subsidy split for a block.
type BlockRewardInfo struct {
	BaseSubsidyABA float64
	RewardABA      float64
	BurnedABA      float64
	UsefulRatio    float64
}

// Chain is an in-memory block chain for T0 simnet demos.
type Chain struct {
	blocks       []*Block
	verifier     pouw.WorkVerifier
	verifierName string
	bits         uint32
	jobs         *jobs.Registry
}

// New creates an empty chain with the given verifier and difficulty bits.
func New(verifier pouw.WorkVerifier, bits uint32) *Chain {
	return &Chain{verifier: verifier, bits: bits, verifierName: "default", jobs: jobs.Global}
}

// NewNamed creates a chain and records the verifier name for persistence.
func NewNamed(verifier pouw.WorkVerifier, verifierName string, bits uint32) *Chain {
	return &Chain{verifier: verifier, verifierName: verifierName, bits: bits, jobs: jobs.Global}
}

// SetJobRegistry overrides the job registry used for useful_ratio enforcement.
func (c *Chain) SetJobRegistry(r *jobs.Registry) { c.jobs = r }

// VerifierName returns the verifier identifier stored on disk.
func (c *Chain) VerifierName() string { return c.verifierName }

// Blocks returns all blocks (genesis first).
func (c *Chain) Blocks() []*Block {
	out := make([]*Block, len(c.blocks))
	copy(out, c.blocks)
	return out
}

// Tip returns the latest block or nil.
func (c *Chain) Tip() *Block {
	if len(c.blocks) == 0 {
		return nil
	}
	return c.blocks[len(c.blocks)-1]
}

// Len returns the number of blocks.
func (c *Chain) Len() int { return len(c.blocks) }

// InitGenesis mines and appends the genesis block.
func (c *Chain) InitGenesis() (*Block, error) {
	genesisHeader := pouw.Header{
		Version:        AbakosBlockVersion,
		Timestamp:      chaincfg.SimNetGenesisTime,
		Bits:           c.bits,
		UsefulRatioBps: 0,
	}
	block, err := Mine(genesisHeader, c.verifier)
	if err != nil {
		return nil, err
	}
	block.Height = 0
	block.id = c.computeBlockID(block)
	if err := c.validate(block); err != nil {
		return nil, err
	}
	c.blocks = append(c.blocks, block)
	return block, nil
}

// MineNext mines a child of the current tip.
// usefulBps > 0 requires a funded job in the registry; ProofCommitment is set
// automatically from the demo job "simnet-paid" (registered on demand).
func (c *Chain) MineNext(usefulBps uint16) (*Block, error) {
	if len(c.blocks) == 0 {
		return nil, fmt.Errorf("chain: genesis required before mining")
	}
	parent := c.Tip()
	ts := parent.Header.Timestamp.Add(chaincfg.TargetBlockTime())
	header := headerAfter(parent, c.bits, usefulBps, ts)
	if usefulBps > 0 {
		r := c.jobs
		if r == nil {
			r = jobs.Global
		}
		header.ProofCommitment = r.RegisterDemoFunded("simnet-paid")
	}
	block, err := Mine(header, c.verifier)
	if err != nil {
		return nil, err
	}
	block.Height = parent.Height + 1
	block.id = c.computeBlockID(block)
	if err := c.validate(block); err != nil {
		return nil, err
	}
	c.blocks = append(c.blocks, block)
	return block, nil
}

// ImportBlock validates and appends a block received from a peer.
func (c *Chain) ImportBlock(block *Block) error {
	block.id = c.computeBlockID(block)
	if err := c.validate(block); err != nil {
		return err
	}
	if block.Height != uint64(len(c.blocks)) {
		return fmt.Errorf("chain: expected height %d got %d", len(c.blocks), block.Height)
	}
	c.blocks = append(c.blocks, block)
	return nil
}

func (c *Chain) validate(block *Block) error {
	h := consensus.HeaderFromPouw(block.Header)
	r := c.jobs
	if r == nil {
		r = jobs.Global
	}
	if err := consensus.ValidateBlockEnforcement(&h, block.Proof, c.verifier, block.Header.Timestamp, r); err != nil {
		return err
	}
	if block.Height > 0 {
		parent := c.blocks[block.Height-1]
		if block.Header.PrevBlock != parent.Hash() {
			return fmt.Errorf("chain: prev block hash mismatch")
		}
		if !block.Header.Timestamp.After(parent.Header.Timestamp) {
			return fmt.Errorf("chain: timestamp must increase")
		}
	} else if block.Height == 0 && len(c.blocks) > 0 {
		return fmt.Errorf("chain: duplicate genesis")
	}
	return nil
}

func (c *Chain) computeBlockID(block *Block) [32]byte {
	switch c.verifier.(type) {
	case pouw.CPUGEMMVerifier:
		return pouw.GEMMBlockHash(&block.Header, block.Proof)
	default:
		return pouw.BlockHash(&block.Header, block.Proof)
	}
}

// RewardInfo computes the block subsidy split for a block at its height.
func RewardInfo(block *Block) BlockRewardInfo {
	base := blockSubsidyABA(block.Height)
	ratio := block.UsefulRatio()
	reward := economics.BlockReward(base, ratio)
	return BlockRewardInfo{
		BaseSubsidyABA: base,
		RewardABA:      reward,
		BurnedABA:      base - reward,
		UsefulRatio:    ratio,
	}
}

func blockSubsidyABA(height uint64) float64 {
	_ = height // halving wired when btcd fork lands
	blocksPerYear := 365.0 * 24.0 * 3600.0 / float64(params.TargetBlockSeconds)
	return economics.AnnualEmissionABA(1) / blocksPerYear
}
