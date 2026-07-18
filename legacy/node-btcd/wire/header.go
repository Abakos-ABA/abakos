// Package wire defines Abakos on-wire block structures (btcd-fork precursor).
// See docs/spec-pouw-integration.md.
package wire

import (
	"encoding/binary"
	"io"
	"time"
)

const (
	// MaxCertificateSize caps plain PoUW certificate bytes on the wire (T0).
	MaxCertificateSize = 65536
	// HeaderPayloadSize is the fixed Abakos block header (no Bitcoin nonce field).
	HeaderPayloadSize = 4 + 32 + 32 + 4 + 4 + 32 + 2 // 110 bytes
)

// BlockHeader is the Abakos block header committed before the PoUW certificate.
type BlockHeader struct {
	Version         int32
	PrevBlock       [32]byte
	MerkleRoot      [32]byte
	Timestamp       time.Time
	Bits            uint32
	ProofCommitment [32]byte
	UsefulRatioBps  uint16
}

// MsgBlock is header + certificate + metadata for T0 simnet transport.
type MsgBlock struct {
	Header      BlockHeader
	Certificate []byte // plain PoUW proof bytes
	Height      uint64
}

// EncodeBlockHeader writes the header in wire order.
func EncodeBlockHeader(w io.Writer, h *BlockHeader) error {
	var buf [HeaderPayloadSize]byte
	binary.LittleEndian.PutUint32(buf[0:4], uint32(h.Version))
	copy(buf[4:36], h.PrevBlock[:])
	copy(buf[36:68], h.MerkleRoot[:])
	binary.LittleEndian.PutUint32(buf[68:72], uint32(h.Timestamp.Unix()))
	binary.LittleEndian.PutUint32(buf[72:76], h.Bits)
	copy(buf[76:108], h.ProofCommitment[:])
	binary.LittleEndian.PutUint16(buf[108:110], h.UsefulRatioBps)
	_, err := w.Write(buf[:])
	return err
}

// DecodeBlockHeader reads a block header from r.
func DecodeBlockHeader(r io.Reader, h *BlockHeader) error {
	var buf [HeaderPayloadSize]byte
	if _, err := io.ReadFull(r, buf[:]); err != nil {
		return err
	}
	h.Version = int32(binary.LittleEndian.Uint32(buf[0:4]))
	copy(h.PrevBlock[:], buf[4:36])
	copy(h.MerkleRoot[:], buf[36:68])
	h.Timestamp = time.Unix(int64(binary.LittleEndian.Uint32(buf[68:72])), 0)
	h.Bits = binary.LittleEndian.Uint32(buf[72:76])
	copy(h.ProofCommitment[:], buf[76:108])
	h.UsefulRatioBps = binary.LittleEndian.Uint16(buf[108:110])
	return nil
}
