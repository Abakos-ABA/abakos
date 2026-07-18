package wire

import (
	"encoding/binary"
	"fmt"
	"io"
)

// EncodeMsgBlock serializes a block for T0 simnet P2P.
func EncodeMsgBlock(w io.Writer, msg *MsgBlock) error {
	if err := EncodeBlockHeader(w, &msg.Header); err != nil {
		return err
	}
	if len(msg.Certificate) > MaxCertificateSize {
		return fmt.Errorf("wire: certificate too large")
	}
	var lenBuf [8]byte
	binary.LittleEndian.PutUint64(lenBuf[:], uint64(len(msg.Certificate)))
	if _, err := w.Write(lenBuf[:]); err != nil {
		return err
	}
	if _, err := w.Write(msg.Certificate); err != nil {
		return err
	}
	binary.LittleEndian.PutUint64(lenBuf[:], msg.Height)
	_, err := w.Write(lenBuf[:])
	return err
}

// DecodeMsgBlock deserializes a block from T0 simnet P2P.
func DecodeMsgBlock(r io.Reader, msg *MsgBlock) error {
	if err := DecodeBlockHeader(r, &msg.Header); err != nil {
		return err
	}
	var lenBuf [8]byte
	if _, err := io.ReadFull(r, lenBuf[:]); err != nil {
		return err
	}
	certLen := binary.LittleEndian.Uint64(lenBuf[:])
	if certLen > MaxCertificateSize {
		return fmt.Errorf("wire: certificate length %d exceeds max", certLen)
	}
	msg.Certificate = make([]byte, certLen)
	if _, err := io.ReadFull(r, msg.Certificate); err != nil {
		return err
	}
	if _, err := io.ReadFull(r, lenBuf[:]); err != nil {
		return err
	}
	msg.Height = binary.LittleEndian.Uint64(lenBuf[:])
	return nil
}
