package sdkutil_test

import (
	"context"
	"encoding/json"
	"testing"

	txv1beta1 "cosmossdk.io/api/cosmos/tx/v1beta1"
	sdkmath "cosmossdk.io/math"
	txsigning "cosmossdk.io/x/tx/signing"
	"github.com/stretchr/testify/require"
	anypb "google.golang.org/protobuf/types/known/anypb"
	gogoproto "github.com/cosmos/gogoproto/proto"

	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"

	certv1 "pkg.akt.dev/go/node/cert/v1"
	cv1 "pkg.akt.dev/go/node/cert/v1"
	dv1 "pkg.akt.dev/go/node/deployment/v1"
	ev1 "pkg.akt.dev/go/node/escrow/v1"
	escrowid "pkg.akt.dev/go/node/escrow/id/v1"
	dv1beta4 "pkg.akt.dev/go/node/deployment/v1beta4"
	mv1 "pkg.akt.dev/go/node/market/v1"
	mv1beta5 "pkg.akt.dev/go/node/market/v1beta5"
	"pkg.akt.dev/go/sdkutil"
	attrv1 "pkg.akt.dev/go/node/types/attributes/v1"
	depositv1 "pkg.akt.dev/go/node/types/deposit/v1"
	resv1beta4 "pkg.akt.dev/go/node/types/resources/v1beta4"
)

// The descriptor-driven default handler signs over "groups":[{}] for this message, which leaves
// the tenant's resources and price outside the signature. The codec-based handler must carry
// them, and must name the message without dots so EIP-712 can wrap it.
func TestLegacyAminoJSONHandlerSignsWholeDeployment(t *testing.T) {
	encCfg := sdkutil.MakeEncodingConfig()
	dv1beta4.RegisterLegacyAminoCodec(encCfg.Amino)
	dv1beta4.RegisterInterfaces(encCfg.InterfaceRegistry)

	units := resv1beta4.NewResourceValue(100)
	msg := &dv1beta4.MsgCreateDeployment{
		ID:   dv1.DeploymentID{Owner: "abakos1owner", DSeq: 620},
		Hash: []byte{7, 7, 7},
		Groups: dv1beta4.GroupSpecs{{
			Name:         "akash",
			Requirements: attrv1.PlacementRequirements{},
			Resources: dv1beta4.ResourceUnits{{
				Resources: resv1beta4.Resources{
					ID:        1,
					CPU:       &resv1beta4.CPU{Units: units},
					Memory:    &resv1beta4.Memory{Quantity: resv1beta4.NewResourceValue(268435456)},
					Storage:   resv1beta4.Volumes{{Name: "default", Quantity: resv1beta4.NewResourceValue(268435456)}},
					GPU:       &resv1beta4.GPU{Units: resv1beta4.NewResourceValue(0)},
					Endpoints: resv1beta4.Endpoints{{SequenceNumber: 0}},
				},
				Count: 1,
				Price: sdk.NewDecCoin("uaba", sdkmath.NewInt(1000)),
			}},
		}},
		Deposit: depositv1.Deposit{
			Amount:  sdk.NewCoin("uaba", sdkmath.NewInt(500000)),
			Sources: depositv1.Sources{depositv1.SourceGrant, depositv1.SourceBalance},
		},
	}

	packed, err := codec.NewProtoCodec(encCfg.InterfaceRegistry).MarshalInterface(msg)
	require.NoError(t, err)
	var wire struct{ TypeURL string }
	_ = wire

	anyMsg, err := anyFromMsg(encCfg, msg)
	require.NoError(t, err)
	require.NotEmpty(t, packed)

	handler := sdkutil.NewLegacyAminoJSONHandler(encCfg.Amino, encCfg.InterfaceRegistry)
	signBytes, err := handler.GetSignBytes(context.Background(),
		txsigning.SignerData{ChainID: "abakos-sandbox-1", AccountNumber: 17, Sequence: 0},
		txsigning.TxData{
			Body:     &txv1beta1.TxBody{Messages: []*anypb.Any{anyMsg}, Memo: "console air"},
			AuthInfo: &txv1beta1.AuthInfo{Fee: &txv1beta1.Fee{GasLimit: 400000}},
		})
	require.NoError(t, err)

	var doc struct {
		Msgs []struct {
			Type  string          `json:"type"`
			Value json.RawMessage `json:"value"`
		} `json:"msgs"`
	}
	require.NoError(t, json.Unmarshal(signBytes, &doc))
	require.Len(t, doc.Msgs, 1)

	// Dot-free name: cosmos/evm turns this into an EIP-712 type name, and go-ethereum rejects dots.
	require.Equal(t, "akash-sdk/x/deployment/MsgCreateDeployment", doc.Msgs[0].Type)
	require.NotContains(t, doc.Msgs[0].Type, ".")

	// The signature has to cover what is deployed and what it costs.
	value := string(doc.Msgs[0].Value)
	require.Contains(t, value, "\"akash\"")
	require.Contains(t, value, "uaba")
	require.Contains(t, value, "268435456")
	// EIP-712 cannot carry null fields: cosmos/evm emits no type for them and go-ethereum then
	// rejects the message for having more fields than its type.
	require.NotContains(t, value, ":null")
	t.Logf("sign bytes: %s", value)
}

func anyFromMsg(encCfg sdkutil.EncodingConfig, msg sdk.Msg) (*anypb.Any, error) {
	bz, err := codec.NewProtoCodec(encCfg.InterfaceRegistry).Marshal(msg)
	if err != nil {
		return nil, err
	}
	return &anypb.Any{TypeUrl: "/" + sdk.MsgTypeURL(msg)[1:], Value: bz}, nil
}

// Records the node's sign bytes for MsgCreateLease — the one console message that had never been
// verified against the chain.
func TestLegacyAminoJSONHandlerLease(t *testing.T) {
	encCfg := sdkutil.MakeEncodingConfig()
	mv1beta5.RegisterLegacyAminoCodec(encCfg.Amino)
	mv1beta5.RegisterInterfaces(encCfg.InterfaceRegistry)

	msg := &mv1beta5.MsgCreateLease{
		BidID: mv1.BidID{Owner: "abakos1owner", DSeq: 138163, GSeq: 1, OSeq: 1, Provider: "abakos1prov"},
	}

	anyMsg, err := anyFromMsg(encCfg, msg)
	require.NoError(t, err)

	handler := sdkutil.NewLegacyAminoJSONHandler(encCfg.Amino, encCfg.InterfaceRegistry)
	signBytes, err := handler.GetSignBytes(context.Background(),
		txsigning.SignerData{ChainID: "abakos-sandbox-1", AccountNumber: 17, Sequence: 7},
		txsigning.TxData{
			Body:     &txv1beta1.TxBody{Messages: []*anypb.Any{anyMsg}, Memo: "console air"},
			AuthInfo: &txv1beta1.AuthInfo{Fee: &txv1beta1.Fee{GasLimit: 243347}},
		})
	require.NoError(t, err)
	t.Logf("lease sign bytes: %s", string(signBytes))
}

// Records the node's sign bytes for the remaining console messages, so the client converter can
// assert against them instead of guessing shapes.
func TestLegacyAminoJSONHandlerRemainingMsgs(t *testing.T) {
	encCfg := sdkutil.MakeEncodingConfig()
	cv1.RegisterLegacyAminoCodec(encCfg.Amino)
	cv1.RegisterInterfaces(encCfg.InterfaceRegistry)
	ev1.RegisterLegacyAminoCodec(encCfg.Amino)
	ev1.RegisterInterfaces(encCfg.InterfaceRegistry)
	dv1beta4.RegisterLegacyAminoCodec(encCfg.Amino)
	dv1beta4.RegisterInterfaces(encCfg.InterfaceRegistry)

	handler := sdkutil.NewLegacyAminoJSONHandler(encCfg.Amino, encCfg.InterfaceRegistry)

	msgs := []interface {
		gogoproto.Message
	}{
		&cv1.MsgCreateCertificate{Owner: "abakos1owner", Cert: []byte("CERT"), Pubkey: []byte("PUB")},
		&cv1.MsgRevokeCertificate{ID: certv1.ID{Owner: "abakos1owner", Serial: "12345"}},
		&dv1beta4.MsgUpdateDeployment{ID: dv1.DeploymentID{Owner: "abakos1owner", DSeq: 620}, Hash: []byte{3, 3, 3}},
		&dv1beta4.MsgCloseDeployment{ID: dv1.DeploymentID{Owner: "abakos1owner", DSeq: 620}},
		&ev1.MsgAccountDeposit{
			Signer:  "abakos1owner",
			ID:      escrowid.Account{Scope: escrowid.ScopeDeployment, XID: "abakos1owner/620"},
			Deposit: depositv1.Deposit{Amount: sdk.NewCoin("uaba", sdkmath.NewInt(5000000)), Sources: depositv1.Sources{depositv1.SourceGrant, depositv1.SourceBalance}},
		},
	}

	for _, msg := range msgs {
		anyMsg, err := anyFromMsg(encCfg, msg.(sdk.Msg))
		require.NoError(t, err)
		signBytes, err := handler.GetSignBytes(context.Background(),
			txsigning.SignerData{ChainID: "abakos-sandbox-1", AccountNumber: 17, Sequence: 7},
			txsigning.TxData{Body: &txv1beta1.TxBody{Messages: []*anypb.Any{anyMsg}}, AuthInfo: &txv1beta1.AuthInfo{Fee: &txv1beta1.Fee{GasLimit: 200000}}})
		require.NoError(t, err)
		t.Logf("%T: %s", msg, string(signBytes))
	}
}
