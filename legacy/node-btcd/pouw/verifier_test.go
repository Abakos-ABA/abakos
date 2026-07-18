package pouw

import (
	"encoding/binary"
	"testing"
	"time"
)

func TestMockVerifier(t *testing.T) {
	v := MockVerifier{}
	h := &Header{Bits: 0x1d00ffff}
	if err := v.Verify(h, []byte("ok:simnet")); err != nil {
		t.Fatalf("expected ok proof: %v", err)
	}
	if err := v.Verify(h, []byte("bad")); err == nil {
		t.Fatal("expected reject")
	}
	if v.WorkUnits([]byte("ok:ab")) == 0 {
		t.Fatal("expected non-zero work units")
	}
}

func TestSHA256StubVerifier_easyTarget(t *testing.T) {
	v := SHA256StubVerifier{}
	h := &Header{
		Version:   1,
		Timestamp: time.Unix(1_700_000_000, 0),
		Bits:      0x1f00ffff, // very easy target for CI brute-force
	}

	var found []byte
	for nonce := uint32(0); nonce < 5_000_000; nonce++ {
		proof := make([]byte, 4)
		binary.LittleEndian.PutUint32(proof, nonce)
		if v.Verify(h, proof) == nil {
			found = proof
			break
		}
	}
	if found == nil {
		t.Fatal("no nonce found under easy target in 5M tries")
	}
	if v.WorkUnits(found) != 1 {
		t.Fatalf("work units = %d, want 1", v.WorkUnits(found))
	}
}

func TestSHA256StubVerifier_rejectsEmpty(t *testing.T) {
	v := SHA256StubVerifier{}
	if err := v.Verify(&Header{Bits: 0x207fffff}, nil); err == nil {
		t.Fatal("expected error for empty proof")
	}
}
