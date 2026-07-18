package pouw

import (
	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
)

// MeetsTarget reports whether hash is at or below the compact difficulty target.
func MeetsTarget(hash [32]byte, bits uint32) bool {
	target := blockchain.CompactToBig(bits)
	if target.Sign() <= 0 {
		return false
	}
	var h chainhash.Hash
	copy(h[:], hash[:])
	return blockchain.HashToBig(&h).Cmp(target) <= 0
}
