package pouw

import "errors"

// WorkVerifier checks that a block's PoUW proof is valid under the header's
// difficulty target and returns normalized work units for hashrate metrics.
type WorkVerifier interface {
	Verify(header *Header, proof []byte) error
	WorkUnits(proof []byte) uint64
}

// ErrInvalidProof is returned when proof bytes fail verification.
var ErrInvalidProof = errors.New("pouw: invalid proof")
