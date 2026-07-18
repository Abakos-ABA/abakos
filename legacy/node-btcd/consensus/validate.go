// Package consensus validates Abakos blocks (btcd validate.go fork precursor).
package consensus

import (
	"fmt"
	"time"

	"github.com/rexmarlon/abakos/node/economics"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/pouw"
	"github.com/rexmarlon/abakos/node/wire"
)

// ValidateHeaderSanity performs context-free header checks.
func ValidateHeaderSanity(h *wire.BlockHeader) error {
	if h.UsefulRatioBps > 10000 {
		return fmt.Errorf("consensus: useful_ratio bps out of range")
	}
	if h.Bits == 0 {
		return fmt.Errorf("consensus: zero difficulty bits")
	}
	return nil
}

// CheckJobCommitment enforces economic binding of useful_ratio to a funded job.
// useful_bps == 0 requires a zero ProofCommitment; useful_bps > 0 requires a
// registered, funded, non-expired job ID in ProofCommitment.
func CheckJobCommitment(h *wire.BlockHeader, now time.Time, r *jobs.Registry) error {
	if err := ValidateHeaderSanity(h); err != nil {
		return err
	}
	if err := jobs.ValidateCommitment(h.UsefulRatioBps, h.ProofCommitment, now, r); err != nil {
		return fmt.Errorf("consensus: %w", err)
	}
	return nil
}

// CheckCoinbaseSubsidy verifies the coinbase pays exactly the reward-split amount.
func CheckCoinbaseSubsidy(paid, baseSubsidy int64, usefulBps uint16) error {
	if err := economics.ValidateCoinbaseSubsidy(paid, baseSubsidy, usefulBps); err != nil {
		return fmt.Errorf("consensus: %w", err)
	}
	return nil
}

// ExpectedCoinbaseSubsidy returns the consensus coinbase for base + useful_bps.
func ExpectedCoinbaseSubsidy(baseSubsidy int64, usefulBps uint16) int64 {
	return economics.CoinbaseSubsidy(baseSubsidy, usefulBps)
}

// CheckProofOfUsefulWork verifies the PoUW certificate against the header.
func CheckProofOfUsefulWork(h *wire.BlockHeader, certificate []byte, v pouw.WorkVerifier) error {
	if err := ValidateHeaderSanity(h); err != nil {
		return err
	}
	if len(certificate) == 0 {
		return fmt.Errorf("consensus: missing certificate")
	}
	ph := pouw.Header{
		Version:         h.Version,
		PrevBlock:       h.PrevBlock,
		MerkleRoot:      h.MerkleRoot,
		Timestamp:       h.Timestamp,
		Bits:            h.Bits,
		ProofCommitment: h.ProofCommitment,
		UsefulRatioBps:  h.UsefulRatioBps,
	}
	if err := v.Verify(&ph, certificate); err != nil {
		return fmt.Errorf("consensus: pouw: %w", err)
	}
	return nil
}

// ValidateBlockEnforcement runs PoUW + job commitment checks (T0 Phase A).
func ValidateBlockEnforcement(h *wire.BlockHeader, certificate []byte, v pouw.WorkVerifier, now time.Time, r *jobs.Registry) error {
	if err := CheckProofOfUsefulWork(h, certificate, v); err != nil {
		return err
	}
	if err := CheckJobCommitment(h, now, r); err != nil {
		return err
	}
	return nil
}

// HeaderFromPouw converts a pouw header to wire format.
func HeaderFromPouw(h pouw.Header) wire.BlockHeader {
	return wire.BlockHeader{
		Version:         h.Version,
		PrevBlock:       h.PrevBlock,
		MerkleRoot:      h.MerkleRoot,
		Timestamp:       h.Timestamp,
		Bits:            h.Bits,
		ProofCommitment: h.ProofCommitment,
		UsefulRatioBps:  h.UsefulRatioBps,
	}
}

// HeaderToPouw converts wire header to pouw format.
func HeaderToPouw(h wire.BlockHeader) pouw.Header {
	return pouw.Header{
		Version:         h.Version,
		PrevBlock:       h.PrevBlock,
		MerkleRoot:      h.MerkleRoot,
		Timestamp:       h.Timestamp,
		Bits:            h.Bits,
		ProofCommitment: h.ProofCommitment,
		UsefulRatioBps:  h.UsefulRatioBps,
	}
}
