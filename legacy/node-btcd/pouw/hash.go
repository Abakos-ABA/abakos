package pouw

import (
	"crypto/sha256"
	"encoding/binary"
)

// SerializeForPoW returns the byte sequence hashed for stub PoW (header + nonce).
func SerializeForPoW(h *Header, nonce uint32) []byte {
	buf := make([]byte, 0, 128)
	buf = binary.LittleEndian.AppendUint32(buf, uint32(h.Version))
	buf = append(buf, h.PrevBlock[:]...)
	buf = append(buf, h.MerkleRoot[:]...)
	buf = binary.LittleEndian.AppendUint32(buf, uint32(h.Timestamp.Unix()))
	buf = binary.LittleEndian.AppendUint32(buf, h.Bits)
	buf = append(buf, h.ProofCommitment[:]...)
	buf = binary.LittleEndian.AppendUint32(buf, nonce)
	return buf
}

// BlockHash returns double-SHA256 of the PoW serialization for a valid proof.
func BlockHash(h *Header, proof []byte) [32]byte {
	if len(proof) < 4 {
		return [32]byte{}
	}
	nonce := binary.LittleEndian.Uint32(proof[:4])
	first := sha256.Sum256(SerializeForPoW(h, nonce))
	return sha256.Sum256(first[:])
}
