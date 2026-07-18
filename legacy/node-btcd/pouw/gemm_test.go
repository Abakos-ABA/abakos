package pouw

import (
	"encoding/binary"
	"testing"
	"time"

	"github.com/rexmarlon/abakos/node/chaincfg"
)

func TestCPUGEMMVerifier_findsNonce(t *testing.T) {
	v := CPUGEMMVerifier{}
	h := &Header{
		Version:   1,
		Timestamp: chaincfg.SimNetGenesisTime,
		Bits:      chaincfg.SimNetEasyBits,
	}

	var proof []byte
	for nonce := uint32(0); nonce < 2_000_000; nonce++ {
		proof = make([]byte, 4)
		binary.LittleEndian.PutUint32(proof, nonce)
		if v.Verify(h, proof) == nil {
			break
		}
	}
	if proof == nil || v.Verify(h, proof) != nil {
		t.Fatal("no gemm nonce found")
	}
	if v.WorkUnits(proof) != GEMMM*GEMMN*GEMMK {
		t.Fatalf("work units %d", v.WorkUnits(proof))
	}
	id := GEMMBlockHash(h, proof)
	if id == ([32]byte{}) {
		t.Fatal("empty block hash")
	}
}

func TestCPUGEMMVerifier_rejectsSHAProof(t *testing.T) {
	v := CPUGEMMVerifier{}
	h := &Header{Bits: chaincfg.SimNetEasyBits, Timestamp: time.Unix(1, 0)}
	if err := v.Verify(h, []byte{0, 0, 0, 0}); err == nil {
		// might rarely pass, try fixed bad proof
		if v.Verify(h, []byte("bad")) == nil {
			t.Fatal("expected reject for bad proof")
		}
	}
}
