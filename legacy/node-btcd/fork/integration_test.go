package fork_test

import (
	"bytes"
	"testing"
	"time"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/wire"
	abchaincfg "github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/fork"
	"github.com/rexmarlon/abakos/node/pouw"
)

func mineGEMMCert(t *testing.T, h pouw.Header) []byte {
	t.Helper()
	v := pouw.CPUGEMMVerifier{}
	for nonce := uint32(0); nonce < 3_000_000; nonce++ {
		proof := []byte{byte(nonce), byte(nonce >> 8), byte(nonce >> 16), byte(nonce >> 24)}
		if v.Verify(&h, proof) == nil {
			return proof
		}
	}
	t.Fatal("could not mine GEMM cert")
	return nil
}

func TestBtcdForkAbakosWireRoundTrip(t *testing.T) {
	hdr := wire.BlockHeader{
		Version:    wire.BlockVersionAbakos | 1,
		Timestamp:  abchaincfg.SimNetGenesisTime,
		Bits:       abchaincfg.SimNetEasyBits,
		UsefulRatioBps: 0,
	}
	ph := pouw.Header{
		Version:        hdr.Version,
		Timestamp:      hdr.Timestamp,
		Bits:           hdr.Bits,
		UsefulRatioBps: hdr.UsefulRatioBps,
	}
	cert := mineGEMMCert(t, ph)

	msg := &wire.MsgBlock{
		Header:      hdr,
		Certificate: cert,
	}
	var buf bytes.Buffer
	if err := msg.BtcEncode(&buf, wire.ProtocolVersion, wire.WitnessEncoding); err != nil {
		t.Fatalf("encode: %v", err)
	}
	var decoded wire.MsgBlock
	if err := decoded.BtcDecode(&buf, wire.ProtocolVersion, wire.WitnessEncoding); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !bytes.Equal(decoded.Certificate, cert) {
		t.Fatalf("certificate mismatch")
	}
	if decoded.Header.Bits != hdr.Bits || decoded.Header.UsefulRatioBps != hdr.UsefulRatioBps {
		t.Fatalf("header field mismatch")
	}
}

func TestBtcdForkCheckProofOfUsefulWork(t *testing.T) {
	fork.SetVerifier(pouw.CPUGEMMVerifier{})

	hdr := wire.BlockHeader{
		Version:    wire.BlockVersionAbakos | 1,
		Timestamp:  time.Unix(abchaincfg.SimNetGenesisTime.Unix(), 0),
		Bits:       abchaincfg.SimNetEasyBits,
	}
	ph := pouw.Header{
		Version:   hdr.Version,
		Timestamp: hdr.Timestamp,
		Bits:      hdr.Bits,
	}
	cert := mineGEMMCert(t, ph)

	msg := &wire.MsgBlock{Header: hdr, Certificate: cert}
	block := btcutil.NewBlock(msg)
	powLimit := chaincfg.SimNetParams.PowLimit

	if err := blockchain.CheckProofOfUsefulWork(block, powLimit); err != nil {
		t.Fatalf("valid Abakos block rejected: %v", err)
	}

	msg.Certificate = nil
	block = btcutil.NewBlock(msg)
	if err := blockchain.CheckProofOfUsefulWork(block, powLimit); err == nil {
		t.Fatal("expected missing certificate error")
	}
}
