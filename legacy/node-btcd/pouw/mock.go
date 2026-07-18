package pouw

// MockVerifier accepts proofs prefixed with "ok:" and rejects everything else.
// Used in unit tests and local simnet before the real kernel is wired.
type MockVerifier struct{}

func (MockVerifier) Verify(_ *Header, proof []byte) error {
	if len(proof) >= 3 && string(proof[:3]) == "ok:" {
		return nil
	}
	return ErrInvalidProof
}

func (MockVerifier) WorkUnits(proof []byte) uint64 {
	if len(proof) <= 3 {
		return 0
	}
	// Cheap stand-in: bytes after "ok:" as a small integer.
	var n uint64
	for _, b := range proof[3:] {
		n = n*31 + uint64(b)
	}
	if n == 0 {
		return 1
	}
	return n
}
