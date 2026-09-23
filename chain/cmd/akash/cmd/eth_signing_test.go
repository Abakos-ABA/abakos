package cmd

// Regression tests for the signature schemes an eth_secp256k1 (MetaMask / Keplr-EVM) account can
// use for SIGN_MODE_LEGACY_AMINO_JSON, run through the node's real encoding config — the same
// codec, amino handler and sign-mode handler map the running binary uses — and the same
// authsigning.VerifySignature call the ante handler makes.
//
// Background: the console signs Cosmos txs with MetaMask's personal_sign (EIP-191) over the amino
// sign doc, because EIP-712 typed data cannot represent an akash deployment whose storage volumes
// differ in shape. The node accepts that signature only through the cosmos-sdk fork's fallback in
// x/auth/signing/verify_eth_personal.go. A binary built from a tree without that fallback rejects
// every console transaction with "signature verification failed" (that is what happened on
// 2026-07-24: the validator's build tree was synced without the cosmos-sdk change). These tests
// make such a build fail before it ships.

import (
	"context"
	"encoding/base64"
	"strconv"
	"sync"
	"testing"

	signingv1beta1 "cosmossdk.io/api/cosmos/tx/signing/v1beta1"
	sdkmath "cosmossdk.io/math"
	txsigning "cosmossdk.io/x/tx/signing"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/types/known/anypb"

	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/tx/signing"
	authsigning "github.com/cosmos/cosmos-sdk/x/auth/signing"
	"github.com/cosmos/evm/crypto/ethsecp256k1"
	"github.com/cosmos/evm/ethereum/eip712"
	gethcrypto "github.com/ethereum/go-ethereum/crypto"

	dv1 "pkg.akt.dev/go/node/deployment/v1"
	dv1beta4 "pkg.akt.dev/go/node/deployment/v1beta4"
	attrv1 "pkg.akt.dev/go/node/types/attributes/v1"
	depositv1 "pkg.akt.dev/go/node/types/deposit/v1"
	resv1beta4 "pkg.akt.dev/go/node/types/resources/v1beta4"
	"pkg.akt.dev/go/sdkutil"
)

const (
	sandboxChainID = "abakos-sandbox-1"

	// A real console transaction (MetaMask personal_sign, abakos-sandbox-1 height 160521, tx
	// 871278E6F6725CE6F5DBFC8860462C408A696C23EF8EC30CAA66080D105C6F34): MsgCreateDeployment
	// for dseq 160518 by abakos1cy93rz4spyy4n84hmklclvc7ay9dk8kf37u725, account 17, sequence 32.
	consoleTxRaw = "CqUCCpUCCi0vYWthc2guZGVwbG95bWVudC52MWJldGE0Lk1zZ0NyZWF0ZURlcGxveW1lbnQS4wEKMwotYWJha29zMWN5OTNyejRzcHl5NG44NGhta2xjbHZjN2F5OWRrOGtmMzd1NzI1EIbmCRJzCgZkY2xvdWQSAgoAGmUKQAgBEggKBgoEMzAwMBoOCgwKCjYwMDAwMDAwMDAiFwoHZGVmYXVsdBIMCgoxMDczNzQxODI0KgUKAwoBMDICCAEQARofCgR1YWJhEhcxMDAwMDAwMDAwMDAwMDAwMDAwMDAwMBogr4GT4rkpWsIANzVmhZQ+ZvV8Nb8CDvotqT0z87vsF0siFQoPCgR1YWJhEgcxMDAwMDAwKAIoARILY29uc29sZSBhaXISbQpaClAKKS9jb3Ntb3MuZXZtLmNyeXB0by52MS5ldGhzZWNwMjU2azEuUHViS2V5EiMKIQIj0+v/8hnshrPGwWdtI223qAvaZt3/t16nr4vbEPN9oRIECgIIfxggEg8KCQoEdWFiYRIBMBCvtgwaQa8UbV63xSvb2U3NhU+tbbgMfJlz7RcNt1ZAG1fN0cZme6zSbw94aL0DICtraGcFfUZWHY79NelW6u3jALa4zZIc"
	consoleTxAccountNumber = 17

	// The sign doc the node derives for that transaction. The console builds the same bytes
	// (abakos-console customAminoTypes + cosmjs serializeSignDoc) and MetaMask signed exactly
	// them, so any drift in the amino output — a renamed field, a null that is no longer
	// dropped, a changed type name — shows up here as a byte difference.
	consoleTxSignDoc = `{"account_number":"17","chain_id":"abakos-sandbox-1","fee":{"amount":[{"amount":"0","denom":"uaba"}],"gas":"203567"},"memo":"console air","msgs":[{"type":"akash-sdk/x/deployment/MsgCreateDeployment","value":{"deposit":{"amount":{"amount":"1000000","denom":"uaba"},"deposit_sources":[2,1]},"groups":[{"name":"dcloud","resources":[{"count":1,"price":{"amount":"10000.000000000000000000","denom":"uaba"},"resource":{"cpu":{"units":{"val":"3000"}},"endpoints":[{"kind":1,"sequence_number":0}],"gpu":{"units":{"val":"0"}},"id":1,"memory":{"size":{"val":"6000000000"}},"storage":[{"name":"default","size":{"val":"1073741824"}}]}}]}],"hash":"r4GT4rkpWsIANzVmhZQ+ZvV8Nb8CDvotqT0z87vsF0s=","id":{"dseq":"160518","owner":"abakos1cy93rz4spyy4n84hmklclvc7ay9dk8kf37u725"}}}],"sequence":"32"}`
)

var (
	nodeEncodingOnce sync.Once
	nodeEncoding     sdkutil.EncodingConfig
)

// nodeEncodingConfig returns the encoding config exactly as the node builds it: NewRootCmd runs
// every registration the binary runs (module amino codecs, evm crypto, eip712 codec). It may only
// run once per process, so it is cached.
func nodeEncodingConfig() sdkutil.EncodingConfig {
	nodeEncodingOnce.Do(func() {
		_, nodeEncoding = NewRootCmd()
	})
	return nodeEncoding
}

func signerDataFor(t *testing.T, pubKey cryptotypes.PubKey, accountNumber, sequence uint64) txsigning.SignerData {
	t.Helper()
	anyPk, err := codectypes.NewAnyWithValue(pubKey)
	require.NoError(t, err)
	return txsigning.SignerData{
		Address:       sdk.AccAddress(pubKey.Address()).String(),
		ChainID:       sandboxChainID,
		AccountNumber: accountNumber,
		Sequence:      sequence,
		PubKey:        &anypb.Any{TypeUrl: anyPk.TypeUrl, Value: anyPk.Value},
	}
}

// verifyLikeAnte runs the exact check the SigVerificationDecorator runs for one signer.
func verifyLikeAnte(ec sdkutil.EncodingConfig, tx sdk.Tx, signerData txsigning.SignerData, pubKey cryptotypes.PubKey, sig signing.SignatureData) error {
	txData := tx.(authsigning.V2AdaptableTx).GetSigningTxData()
	return authsigning.VerifySignature(context.Background(), pubKey, signerData, sig, ec.TxConfig.SignModeHandler(), txData)
}

func aminoSignBytes(t *testing.T, ec sdkutil.EncodingConfig, tx sdk.Tx, signerData txsigning.SignerData) []byte {
	t.Helper()
	txData := tx.(authsigning.V2AdaptableTx).GetSigningTxData()
	bz, err := ec.TxConfig.SignModeHandler().GetSignBytes(context.Background(), signingv1beta1.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, signerData, txData)
	require.NoError(t, err)
	return bz
}

// TestNodeAcceptsConsolePersonalSignTx replays the recorded console transaction: the node must
// derive the recorded sign doc for it and accept MetaMask's EIP-191 signature over those bytes.
func TestNodeAcceptsConsolePersonalSignTx(t *testing.T) {
	ec := nodeEncodingConfig()

	txBytes, err := base64.StdEncoding.DecodeString(consoleTxRaw)
	require.NoError(t, err)
	tx, err := ec.TxConfig.TxDecoder()(txBytes)
	require.NoError(t, err)

	sigs, err := tx.(authsigning.SigVerifiableTx).GetSignaturesV2()
	require.NoError(t, err)
	require.Len(t, sigs, 1)
	pubKey := sigs[0].PubKey
	require.Equal(t, ethsecp256k1.KeyType, pubKey.Type(), "console accounts are eth_secp256k1")
	single, ok := sigs[0].Data.(*signing.SingleSignatureData)
	require.True(t, ok)
	require.Equal(t, signing.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, single.SignMode)
	require.Len(t, single.Signature, 65, "MetaMask returns r||s||v")

	signerData := signerDataFor(t, pubKey, consoleTxAccountNumber, sigs[0].Sequence)
	require.Equal(t, "abakos1cy93rz4spyy4n84hmklclvc7ay9dk8kf37u725", signerData.Address)

	signBytes := aminoSignBytes(t, ec, tx, signerData)
	require.Equal(t, consoleTxSignDoc, string(signBytes), "node amino sign doc drifted from what the console signs")

	// cosmos/evm's own check knows keccak(sign bytes) and EIP-712 only; the console's signature
	// is neither, which is why the fork's EIP-191 fallback exists.
	t.Logf("stock ethsecp256k1 VerifySignature accepts console signature: %v", pubKey.VerifySignature(signBytes, single.Signature))

	require.NoError(t, verifyLikeAnte(ec, tx, signerData, pubKey, single), "node rejects the console's personal_sign transaction")

	t.Run("still binds account number", func(t *testing.T) {
		other := signerDataFor(t, pubKey, consoleTxAccountNumber+1, sigs[0].Sequence)
		require.Error(t, verifyLikeAnte(ec, tx, other, pubKey, single))
	})

	t.Run("still binds sequence", func(t *testing.T) {
		other := signerDataFor(t, pubKey, consoleTxAccountNumber, sigs[0].Sequence+1)
		require.Error(t, verifyLikeAnte(ec, tx, other, pubKey, single))
	})

	t.Run("still binds chain id", func(t *testing.T) {
		other := signerDataFor(t, pubKey, consoleTxAccountNumber, sigs[0].Sequence)
		other.ChainID = "abakos-sandbox-2"
		require.Error(t, verifyLikeAnte(ec, tx, other, pubKey, single))
	})
}

// ethSigner signs digests the way the wallet flows do.
type ethSigner struct {
	priv   *ethsecp256k1.PrivKey
	pubKey cryptotypes.PubKey
}

func newEthSigner(t *testing.T) ethSigner {
	t.Helper()
	priv, err := ethsecp256k1.GenerateKey()
	require.NoError(t, err)
	return ethSigner{priv: priv, pubKey: priv.PubKey()}
}

func (s ethSigner) owner() string { return sdk.AccAddress(s.pubKey.Address()).String() }

// signDigest returns r||s||v; MetaMask style v (27/28) when metamaskV is set.
func (s ethSigner) signDigest(t *testing.T, digest []byte, metamaskV bool) []byte {
	t.Helper()
	ecdsaKey, err := s.priv.ToECDSA()
	require.NoError(t, err)
	sig, err := gethcrypto.Sign(digest, ecdsaKey)
	require.NoError(t, err)
	if metamaskV {
		sig[64] += 27
	}
	return sig
}

func eip191Digest(msg []byte) []byte {
	prefixed := []byte("\x19Ethereum Signed Message:\n" + strconv.Itoa(len(msg)))
	return gethcrypto.Keccak256(append(prefixed, msg...))
}

func buildAminoTx(t *testing.T, ec sdkutil.EncodingConfig, pubKey cryptotypes.PubKey, sequence uint64, sig []byte, msgs ...sdk.Msg) sdk.Tx {
	t.Helper()
	txb := ec.TxConfig.NewTxBuilder()
	require.NoError(t, txb.SetMsgs(msgs...))
	txb.SetGasLimit(400000)
	txb.SetFeeAmount(sdk.Coins{sdk.NewInt64Coin("uaba", 0)})
	txb.SetMemo("console air")
	require.NoError(t, txb.SetSignatures(signing.SignatureV2{
		PubKey:   pubKey,
		Data:     &signing.SingleSignatureData{SignMode: signing.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, Signature: sig},
		Sequence: sequence,
	}))
	return txb.GetTx()
}

// mixedStorageDeployment is the shape EIP-712 cannot sign: two storage volumes, one with
// attributes and one without, so the array's elements have different key sets.
func mixedStorageDeployment(owner string) *dv1beta4.MsgCreateDeployment {
	return &dv1beta4.MsgCreateDeployment{
		ID:   dv1.DeploymentID{Owner: owner, DSeq: 620},
		Hash: []byte{7, 7, 7},
		Groups: dv1beta4.GroupSpecs{{
			Name:         "dcloud",
			Requirements: attrv1.PlacementRequirements{},
			Resources: dv1beta4.ResourceUnits{{
				Resources: resv1beta4.Resources{
					ID:     1,
					CPU:    &resv1beta4.CPU{Units: resv1beta4.NewResourceValue(1000)},
					Memory: &resv1beta4.Memory{Quantity: resv1beta4.NewResourceValue(536870912)},
					Storage: resv1beta4.Volumes{
						{Name: "default", Quantity: resv1beta4.NewResourceValue(1073741824)},
						{Name: "data", Quantity: resv1beta4.NewResourceValue(10737418240), Attributes: attrv1.Attributes{
							{Key: "class", Value: "beta2"},
							{Key: "persistent", Value: "true"},
						}},
					},
					GPU:       &resv1beta4.GPU{Units: resv1beta4.NewResourceValue(0)},
					Endpoints: resv1beta4.Endpoints{{SequenceNumber: 0}},
				},
				Count: 1,
				Price: sdk.NewDecCoin("uaba", sdkmath.NewInt(10000)),
			}},
		}},
		Deposit: depositv1.Deposit{
			Amount:  sdk.NewCoin("uaba", sdkmath.NewInt(500000)),
			Sources: depositv1.Sources{depositv1.SourceBalance},
		},
	}
}

// TestEthAccountAminoSignatureSchemes checks every way an eth_secp256k1 wallet signs the amino
// sign doc: keccak over the bytes (Keplr on an EVM chain), EIP-712 typed data (MetaMask
// eth_signTypedData_v4, where the message shape allows it) and EIP-191 personal_sign (the
// console). All must verify; a foreign key must not.
func TestEthAccountAminoSignatureSchemes(t *testing.T) {
	ec := nodeEncodingConfig()
	signer := newEthSigner(t)
	stranger := newEthSigner(t)

	cases := []struct {
		name           string
		msg            sdk.Msg
		eip712Signable bool
	}{
		{"MsgCloseDeployment", &dv1beta4.MsgCloseDeployment{ID: dv1.DeploymentID{Owner: signer.owner(), DSeq: 620}}, true},
		{"MsgCreateDeployment with mixed storage volumes", mixedStorageDeployment(signer.owner()), false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			const sequence = 60
			signerData := signerDataFor(t, signer.pubKey, 17, sequence)
			unsigned := buildAminoTx(t, ec, signer.pubKey, sequence, nil, tc.msg)
			signBytes := aminoSignBytes(t, ec, unsigned, signerData)

			schemes := map[string][]byte{
				"keccak (Keplr)":                  signer.signDigest(t, gethcrypto.Keccak256(signBytes), false),
				"EIP-191 personal_sign (console)": signer.signDigest(t, eip191Digest(signBytes), true),
				"EIP-191 personal_sign, raw v":    signer.signDigest(t, eip191Digest(signBytes), false),
			}
			if typed, err := eip712.GetEIP712BytesForMsg(signBytes); err == nil {
				schemes["EIP-712 typed data (MetaMask)"] = signer.signDigest(t, gethcrypto.Keccak256(typed), true)
			} else {
				require.False(t, tc.eip712Signable, "EIP-712 unexpectedly unavailable: %v", err)
				t.Logf("EIP-712 cannot represent this message (expected): %v", err)
			}
			if tc.eip712Signable {
				require.Contains(t, schemes, "EIP-712 typed data (MetaMask)")
			}

			for name, sig := range schemes {
				t.Run(name, func(t *testing.T) {
					tx := buildAminoTx(t, ec, signer.pubKey, sequence, sig, tc.msg)
					data := &signing.SingleSignatureData{SignMode: signing.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, Signature: sig}
					require.NoError(t, verifyLikeAnte(ec, tx, signerData, signer.pubKey, data))
				})
			}

			t.Run("rejects a stranger's personal_sign", func(t *testing.T) {
				sig := stranger.signDigest(t, eip191Digest(signBytes), true)
				tx := buildAminoTx(t, ec, signer.pubKey, sequence, sig, tc.msg)
				data := &signing.SingleSignatureData{SignMode: signing.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, Signature: sig}
				require.Error(t, verifyLikeAnte(ec, tx, signerData, signer.pubKey, data))
			})
		})
	}
}

// A plain cosmos secp256k1 account gets no EIP-191 fallback: the personal_sign path is reserved
// for eth keys, so a Keplr-native account's signature rules are unchanged.
func TestCosmosAccountGetsNoPersonalSignFallback(t *testing.T) {
	ec := nodeEncodingConfig()
	priv := secp256k1.GenPrivKey()
	pubKey := priv.PubKey()
	owner := sdk.AccAddress(pubKey.Address()).String()
	msg := &dv1beta4.MsgCloseDeployment{ID: dv1.DeploymentID{Owner: owner, DSeq: 620}}

	const sequence = 1
	signerData := signerDataFor(t, pubKey, 99, sequence)
	signBytes := aminoSignBytes(t, ec, buildAminoTx(t, ec, pubKey, sequence, nil, msg), signerData)

	// A correct EIP-191 signature from the same key material must still be refused.
	ecdsaKey, err := gethcrypto.ToECDSA(priv.Bytes())
	require.NoError(t, err)
	sig, err := gethcrypto.Sign(eip191Digest(signBytes), ecdsaKey)
	require.NoError(t, err)
	sig[64] += 27

	tx := buildAminoTx(t, ec, pubKey, sequence, sig, msg)
	data := &signing.SingleSignatureData{SignMode: signing.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, Signature: sig}
	require.Error(t, verifyLikeAnte(ec, tx, signerData, pubKey, data))

	// while its normal sha256 signature passes
	good, err := priv.Sign(signBytes)
	require.NoError(t, err)
	tx = buildAminoTx(t, ec, pubKey, sequence, good, msg)
	data = &signing.SingleSignatureData{SignMode: signing.SignMode_SIGN_MODE_LEGACY_AMINO_JSON, Signature: good}
	require.NoError(t, verifyLikeAnte(ec, tx, signerData, pubKey, data))
}
