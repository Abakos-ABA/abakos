package signing

import (
	"encoding/hex"
	"math/big"
	"testing"

	"github.com/decred/dcrd/dcrec/secp256k1/v4"
	"github.com/decred/dcrd/dcrec/secp256k1/v4/ecdsa"
	"github.com/stretchr/testify/require"

	cosmossecp256k1 "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
)

// ethTestPubKey stands in for cosmos/evm's ethsecp256k1.PubKey, which this module cannot import:
// same compressed key bytes, same key type string.
type ethTestPubKey struct{ cosmossecp256k1.PubKey }

func (*ethTestPubKey) Type() string { return ethPubKeyType }

var _ cryptotypes.PubKey = (*ethTestPubKey)(nil)

type ethTestKey struct {
	priv *secp256k1.PrivateKey
	pub  *ethTestPubKey
}

func newEthTestKey(t *testing.T) ethTestKey {
	t.Helper()
	priv, err := secp256k1.GeneratePrivateKey()
	require.NoError(t, err)
	return ethTestKey{
		priv: priv,
		pub:  &ethTestPubKey{cosmossecp256k1.PubKey{Key: priv.PubKey().SerializeCompressed()}},
	}
}

// personalSign produces r || s || v exactly like MetaMask's personal_sign (v is 27 or 28).
func (k ethTestKey) personalSign(msg []byte) []byte {
	compact := ecdsa.SignCompact(k.priv, ethPersonalSignDigest(msg), false)
	sig := make([]byte, 65)
	copy(sig, compact[1:])
	sig[64] = compact[0] // 27 + recovery id (uncompressed flag, so no +4)
	return sig
}

func TestVerifyEthPersonalSign(t *testing.T) {
	key := newEthTestKey(t)
	signBytes := []byte(`{"account_number":"17","chain_id":"abakos-sandbox-1","fee":{"amount":[],"gas":"200000"},"memo":"","msgs":[{"type":"akash-sdk/x/deployment/MsgCloseDeployment","value":{"id":{"dseq":"620","owner":"abakos1owner"}}}],"sequence":"60"}`)
	sig := key.personalSign(signBytes)

	t.Run("accepts a MetaMask-style signature (v = 27/28)", func(t *testing.T) {
		require.True(t, verifyEthPersonalSign(key.pub, signBytes, sig))
	})

	t.Run("accepts the raw recovery id form (v = 0/1)", func(t *testing.T) {
		raw := append([]byte{}, sig...)
		raw[64] -= 27
		require.True(t, verifyEthPersonalSign(key.pub, signBytes, raw))
	})

	t.Run("rejects a signature over different sign bytes", func(t *testing.T) {
		tampered := append([]byte{}, signBytes...)
		tampered[len(tampered)-3] = '1' // sequence 60 -> 61
		require.False(t, verifyEthPersonalSign(key.pub, tampered, sig))
	})

	t.Run("rejects another key's signature", func(t *testing.T) {
		other := newEthTestKey(t)
		require.False(t, verifyEthPersonalSign(key.pub, signBytes, other.personalSign(signBytes)))
	})

	t.Run("rejects a non-eth key type", func(t *testing.T) {
		cosmosPub := &key.pub.PubKey // same bytes, type "secp256k1"
		require.False(t, verifyEthPersonalSign(cosmosPub, signBytes, sig))
	})

	t.Run("rejects a 64-byte signature", func(t *testing.T) {
		require.False(t, verifyEthPersonalSign(key.pub, signBytes, sig[:64]))
	})

	t.Run("rejects a malformed recovery byte", func(t *testing.T) {
		bad := append([]byte{}, sig...)
		bad[64] = 29
		require.False(t, verifyEthPersonalSign(key.pub, signBytes, bad))
	})

	t.Run("rejects the high-S malleable twin", func(t *testing.T) {
		high := append([]byte{}, sig...)
		s := new(big.Int).SetBytes(sig[32:64])
		s.Sub(secp256k1.S256().N, s)
		s.FillBytes(high[32:64])
		high[64] ^= 1 // flipping S flips the recovery id parity
		require.False(t, verifyEthPersonalSign(key.pub, signBytes, high))
	})

	t.Run("rejects a nil key", func(t *testing.T) {
		require.False(t, verifyEthPersonalSign(nil, signBytes, sig))
	})
}

// The digest must be keccak256("\x19Ethereum Signed Message:\n" + len + msg); the length is the
// byte count in decimal, which is what makes a wallet's signature over hex-encoded bytes match.
func TestEthPersonalSignDigest(t *testing.T) {
	// keccak256("\x19Ethereum Signed Message:\n5hello"), the reference vector used by ethers/web3.
	require.Equal(t,
		"50b2c43fd39106bafbba0da34fc430e1f91e3c96ea2acee2bc34119f92b37750",
		hex.EncodeToString(ethPersonalSignDigest([]byte("hello"))))
}
