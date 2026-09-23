package signing

import (
	"bytes"
	"fmt"
	"math/big"

	"github.com/decred/dcrd/dcrec/secp256k1/v4"
	"github.com/decred/dcrd/dcrec/secp256k1/v4/ecdsa"
	"golang.org/x/crypto/sha3"

	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
)

// ethPubKeyType is the key type reported by cosmos/evm's ethsecp256k1.PubKey.
const ethPubKeyType = "eth_secp256k1"

// ethPersonalSignPrefix is the EIP-191 version 0x45 ("E") prefix wallets put in front of the
// message for personal_sign; the decimal byte length of the message follows it.
const ethPersonalSignPrefix = "\x19Ethereum Signed Message:\n"

// secp256k1HalfOrder is N/2; a signature whose S is above it is the malleable twin of a valid
// signature, and every wallet produces the low form, so the high form is refused.
var secp256k1HalfOrder = new(big.Int).Rsh(secp256k1.S256().N, 1)

// verifyEthPersonalSign accepts an EIP-191 personal_sign signature over the raw sign bytes from
// an eth_secp256k1 key.
//
// Abakos fork addition. The EIP-712 route (eth_signTypedData_v4) cannot represent every Cosmos
// message: typed data derives an array's element type from its FIRST element, so an array whose
// elements carry different key sets — e.g. one persistent storage volume with attributes next to
// an ephemeral one without — is unverifiable. go-ethereum rejects the extra keys ("there is
// extra data provided in the message") while MetaMask silently signs a digest that does not even
// cover them. Structurally, EIP-712 cannot sign an akash deployment.
//
// personal_sign has no such limit: the wallet signs (and shows the user) the complete amino
// sign-doc JSON, so the signature covers every byte of what is broadcast. The EIP-191 prefix
// domain-separates the digest from real Ethereum transactions, and the sign doc itself still
// binds chain id, account number and sequence, so replay protection is unchanged. Messages this
// signature could be phished for are exactly the messages the user would be signing anyway.
//
// Tried only after the pubkey's own VerifySignature (keccak and EIP-712) has failed, so existing
// wallets are untouched. The console (abakos-console MetaMaskEvmClient.signAmino) depends on this
// path; the regression test in chain/cmd/akash/cmd/eth_signing_test.go replays a real console
// transaction through it.
func verifyEthPersonalSign(pubKey cryptotypes.PubKey, signBytes, sig []byte) bool {
	if pubKey == nil || pubKey.Type() != ethPubKeyType || len(sig) != 65 {
		return false
	}

	// Wallets return r || s || v with v in {0, 1} or {27, 28}.
	code := sig[64]
	if code < 27 {
		code += 27
	}
	if code != 27 && code != 28 {
		return false
	}
	if new(big.Int).SetBytes(sig[32:64]).Cmp(secp256k1HalfOrder) > 0 {
		return false
	}

	digest := ethPersonalSignDigest(signBytes)

	// RecoverCompact wants the recovery code first.
	compact := make([]byte, 65)
	compact[0] = code
	copy(compact[1:], sig[:64])

	recovered, _, err := ecdsa.RecoverCompact(compact, digest)
	if err != nil {
		return false
	}

	return bytes.Equal(recovered.SerializeCompressed(), pubKey.Bytes())
}

// ethPersonalSignDigest is keccak256 of the EIP-191 prefixed message: exactly what a wallet
// hashes for personal_sign over raw bytes.
func ethPersonalSignDigest(msg []byte) []byte {
	prefixed := append([]byte(fmt.Sprintf("%s%d", ethPersonalSignPrefix, len(msg))), msg...)
	hasher := sha3.NewLegacyKeccak256()
	hasher.Write(prefixed)
	return hasher.Sum(nil)
}
