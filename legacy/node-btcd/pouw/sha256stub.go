package pouw

import (
	"crypto/sha256"
	"encoding/binary"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
)

// SHA256StubVerifier is a T0 placeholder that treats proof as a candidate nonce
// and checks double-SHA256(header || nonce) < target(bits), matching vanilla
// btcd semantics until NoisyGEMM replaces it.
type SHA256StubVerifier struct{}

func (SHA256StubVerifier) Verify(header *Header, proof []byte) error {
	if len(proof) < 4 {
		return ErrInvalidProof
	}
	nonce := binary.LittleEndian.Uint32(proof[:4])
	if !hashBelowTarget(header, nonce) {
		return ErrInvalidProof
	}
	return nil
}

func (SHA256StubVerifier) WorkUnits(proof []byte) uint64 {
	if len(proof) < 4 {
		return 0
	}
	return 1
}

func hashBelowTarget(h *Header, nonce uint32) bool {
	target := blockchain.CompactToBig(h.Bits)
	if target.Sign() <= 0 {
		return false
	}

	first := sha256.Sum256(SerializeForPoW(h, nonce))
	second := sha256.Sum256(first[:])
	var blockHash chainhash.Hash
	copy(blockHash[:], second[:])
	return MeetsTarget(blockHash, h.Bits)
}
