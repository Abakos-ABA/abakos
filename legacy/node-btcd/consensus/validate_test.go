package consensus

import (
	"testing"
	"time"

	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/pouw"
	"github.com/rexmarlon/abakos/node/wire"
)

func TestCheckProofOfUsefulWork_GEMM(t *testing.T) {
	v := pouw.CPUGEMMVerifier{}
	h := wire.BlockHeader{
		Version:   1,
		Timestamp: chaincfg.SimNetGenesisTime,
		Bits:      chaincfg.SimNetEasyBits,
	}
	ph := HeaderToPouw(h)
	var proof []byte
	for nonce := uint32(0); nonce < 3_000_000; nonce++ {
		proof = []byte{byte(nonce), byte(nonce >> 8), byte(nonce >> 16), byte(nonce >> 24)}
		if v.Verify(&ph, proof) == nil {
			break
		}
	}
	if err := CheckProofOfUsefulWork(&h, proof, v); err != nil {
		t.Fatalf("valid gemm proof rejected: %v", err)
	}
}

func TestValidateHeaderSanity(t *testing.T) {
	if err := ValidateHeaderSanity(&wire.BlockHeader{UsefulRatioBps: 10001, Bits: 1, Timestamp: time.Now()}); err == nil {
		t.Fatal("expected error")
	}
}

func TestCheckJobCommitment_Enforced(t *testing.T) {
	r := jobs.NewRegistry()
	h := &wire.BlockHeader{Bits: 1, UsefulRatioBps: 10000}
	if err := CheckJobCommitment(h, time.Now(), r); err == nil {
		t.Fatal("useful without job must fail")
	}
	id := r.RegisterDemoFunded("consensus-test")
	h.ProofCommitment = id
	if err := CheckJobCommitment(h, time.Now(), r); err != nil {
		t.Fatal(err)
	}
	h.UsefulRatioBps = 0
	h.ProofCommitment = id
	if err := CheckJobCommitment(h, time.Now(), r); err == nil {
		t.Fatal("empty mining with commitment must fail")
	}
}

func TestCheckCoinbaseSubsidy_Enforced(t *testing.T) {
	const base int64 = 5_000_000_000
	if err := CheckCoinbaseSubsidy(base, base, 0); err == nil {
		t.Fatal("full subsidy at useful=0 must fail")
	}
	if err := CheckCoinbaseSubsidy(ExpectedCoinbaseSubsidy(base, 0), base, 0); err != nil {
		t.Fatal(err)
	}
	if err := CheckCoinbaseSubsidy(base, base, 10000); err != nil {
		t.Fatal(err)
	}
}
