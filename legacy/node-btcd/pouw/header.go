// Package pouw defines the Abakos Proof-of-Useful-Work verifier interface and
// T0 stub implementations. The production verifier (NoisyGEMM + Blake3 jackpot)
// lives in ../pouw/ (CUDA/Rust) and plugs in via WorkVerifier.
package pouw

import "time"

// Header is a consensus header snapshot used for PoUW verification. It mirrors
// the fields Abakos will commit on-chain once the btcd fork lands (see
// docs/spec-pouw-integration.md).
type Header struct {
	Version         int32     `json:"version"`
	PrevBlock       [32]byte  `json:"prev_block"`
	MerkleRoot      [32]byte  `json:"merkle_root"`
	Timestamp       time.Time `json:"timestamp"`
	Bits            uint32    `json:"bits"`
	ProofCommitment [32]byte  `json:"proof_commitment"`
	UsefulRatioBps  uint16    `json:"useful_ratio_bps"`
}
