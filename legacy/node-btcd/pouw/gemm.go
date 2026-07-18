package pouw

import (
	"encoding/binary"

	"github.com/zeebo/blake3"
)

// T0 CPU spike dimensions (tiny for CI; production uses GPU tiles).
const (
	GEMMM = 8
	GEMMN = 8
	GEMMK = 8
)

// CPUGEMMVerifier implements a simplified NoisyGEMM-style PoUW in pure Go.
// Matrices are derived deterministically from the header + nonce; a small INT8
// matmul produces a jackpot checked against difficulty (cuPOW paper §3 sketch).
type CPUGEMMVerifier struct{}

func (CPUGEMMVerifier) Verify(header *Header, proof []byte) error {
	if len(proof) < 4 {
		return ErrInvalidProof
	}
	nonce := binary.LittleEndian.Uint32(proof[:4])
	jackpot := computeJackpot(header, nonce)
	if !MeetsTarget(jackpot, header.Bits) {
		return ErrInvalidProof
	}
	return nil
}

func (CPUGEMMVerifier) WorkUnits(proof []byte) uint64 {
	if len(proof) < 4 {
		return 0
	}
	return GEMMM * GEMMN * GEMMK
}

// GEMMBlockHash returns the block ID for GEMM-mode blocks.
func GEMMBlockHash(header *Header, proof []byte) [32]byte {
	if len(proof) < 4 {
		return [32]byte{}
	}
	nonce := binary.LittleEndian.Uint32(proof[:4])
	jackpot := computeJackpot(header, nonce)
	h := blake3.New()
	h.Write(serializeHeaderForGEMM(header))
	h.Write(jackpot[:])
	var out [32]byte
	copy(out[:], h.Sum(nil))
	return out
}

func serializeHeaderForGEMM(h *Header) []byte {
	buf := make([]byte, 0, 96)
	buf = binary.LittleEndian.AppendUint32(buf, uint32(h.Version))
	buf = append(buf, h.PrevBlock[:]...)
	buf = append(buf, h.MerkleRoot[:]...)
	buf = binary.LittleEndian.AppendUint32(buf, uint32(h.Timestamp.Unix()))
	buf = binary.LittleEndian.AppendUint32(buf, h.Bits)
	buf = append(buf, h.ProofCommitment[:]...)
	buf = binary.LittleEndian.AppendUint16(buf, h.UsefulRatioBps)
	return buf
}

func computeJackpot(header *Header, nonce uint32) [32]byte {
	a, b := deriveMatrices(header, nonce)
	// INT32 accumulators; XOR-reduce into jackpot (T0 simplification).
	var acc [32]byte
	for i := 0; i < GEMMM; i++ {
		for j := 0; j < GEMMN; j++ {
			var sum int32
			for k := 0; k < GEMMK; k++ {
				sum += int32(a[i][k]) * int32(b[k][j])
			}
			// Structured noise from commitment (simplified cuPOW noise term).
			noise := int32((uint32(i*GEMMN+j) ^ nonce) & 0x7f)
			sum += noise
			acc[(i*GEMMN+j)%32] ^= byte(sum & 0xff)
		}
	}
	return blake3.Sum256(acc[:])
}

func deriveMatrices(header *Header, nonce uint32) ([GEMMM][GEMMK]int8, [GEMMK][GEMMN]int8) {
	seed := blake3.Sum256(append(serializeHeaderForGEMM(header), byte(nonce), byte(nonce>>8), byte(nonce>>16), byte(nonce>>24)))
	var a [GEMMM][GEMMK]int8
	var b [GEMMK][GEMMN]int8
	idx := 0
	for i := 0; i < GEMMM; i++ {
		for k := 0; k < GEMMK; k++ {
			a[i][k] = int8((int(seed[idx%32]) % 129) - 64)
			idx++
		}
	}
	for k := 0; k < GEMMK; k++ {
		for j := 0; j < GEMMN; j++ {
			b[k][j] = int8((int(seed[idx%32]) % 129) - 64)
			idx++
		}
	}
	return a, b
}
