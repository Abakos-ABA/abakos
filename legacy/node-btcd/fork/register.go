// Package fork wires the local btcd PoUW fork to Abakos consensus at node startup.
package fork

import (
	"time"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/wire"
	abconsensus "github.com/rexmarlon/abakos/node/consensus"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/pouw"
	abwire "github.com/rexmarlon/abakos/node/wire"
)

type verifier struct {
	v pouw.WorkVerifier
}

func (b verifier) Verify(h *wire.BlockHeader, cert []byte) error {
	ah := btcdHeaderToAbakos(h)
	return abconsensus.ValidateBlockEnforcement(&ah, cert, b.v, time.Now(), jobs.Global)
}

func btcdHeaderToAbakos(h *wire.BlockHeader) abwire.BlockHeader {
	var prev, merkle, commit [32]byte
	copy(prev[:], h.PrevBlock[:])
	copy(merkle[:], h.MerkleRoot[:])
	copy(commit[:], h.ProofCommitment[:])
	return abwire.BlockHeader{
		Version:         h.Version,
		PrevBlock:       prev,
		MerkleRoot:      merkle,
		Timestamp:       h.Timestamp,
		Bits:            h.Bits,
		ProofCommitment: commit,
		UsefulRatioBps:  h.UsefulRatioBps,
	}
}

func init() {
	blockchain.RegisterPoUWVerifier(verifier{v: pouw.CPUGEMMVerifier{}})
}

// SetVerifier replaces the default CPU GEMM verifier (e.g. for tests).
func SetVerifier(v pouw.WorkVerifier) {
	blockchain.RegisterPoUWVerifier(verifier{v: v})
}
