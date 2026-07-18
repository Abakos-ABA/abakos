package chain

import (
	"encoding/binary"
	"fmt"

	"github.com/rexmarlon/abakos/node/pouw"
)

const defaultMineLimit = 10_000_000

// Mine finds a valid PoUW proof for header using verifier (brute-force nonce).
func Mine(header pouw.Header, verifier pouw.WorkVerifier) (*Block, error) {
	return MineFrom(header, verifier, 0, defaultMineLimit)
}

// MineFrom searches nonces in [start, start+limit).
func MineFrom(header pouw.Header, verifier pouw.WorkVerifier, start, limit uint32) (*Block, error) {
	proof := make([]byte, 4)
	for nonce := start; nonce < start+limit; nonce++ {
		binary.LittleEndian.PutUint32(proof, nonce)
		if err := verifier.Verify(&header, proof); err == nil {
			return &Block{Header: header, Proof: append([]byte(nil), proof...)}, nil
		}
	}
	return nil, fmt.Errorf("chain: no valid proof found in %d attempts", limit)
}
