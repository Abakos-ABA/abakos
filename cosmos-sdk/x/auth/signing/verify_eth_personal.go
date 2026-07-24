package signing

import (
	"bytes"
	"fmt"

	"github.com/decred/dcrd/dcrec/secp256k1/v4/ecdsa"
	"golang.org/x/crypto/sha3"

	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
)

const ethPubKeyType = "eth_secp256k1"

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
// wallets are untouched.
func verifyEthPersonalSign(pubKey cryptotypes.PubKey, signBytes, sig []byte) bool {
	if pubKey == nil || pubKey.Type() != ethPubKeyType || len(sig) != 65 {
		return false
	}

	prefixed := append([]byte(fmt.Sprintf("\x19Ethereum Signed Message:\n%d", len(signBytes))), signBytes...)
	hasher := sha3.NewLegacyKeccak256()
	hasher.Write(prefixed)
	digest := hasher.Sum(nil)

	// Wallets return r||s||v; RecoverCompact wants the recovery code first, offset by 27.
	code := sig[64]
	if code < 27 {
		code += 27
	}
	compact := make([]byte, 65)
	compact[0] = code
	copy(compact[1:], sig[:64])

	recovered, _, err := ecdsa.RecoverCompact(compact, digest)
	if err != nil {
		return false
	}

	return bytes.Equal(recovered.SerializeCompressed(), pubKey.Bytes())
}
