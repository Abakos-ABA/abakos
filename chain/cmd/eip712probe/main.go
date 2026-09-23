package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	basev1beta1 "cosmossdk.io/api/cosmos/base/v1beta1"
	txv1beta1 "cosmossdk.io/api/cosmos/tx/v1beta1"
	txsigning "cosmossdk.io/x/tx/signing"
	anypb "google.golang.org/protobuf/types/known/anypb"

	"github.com/cosmos/cosmos-sdk/codec"
	"github.com/cosmos/cosmos-sdk/codec/legacy"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/x/auth/migrations/legacytx"
	"github.com/cosmos/evm/crypto/ethsecp256k1"
	"github.com/cosmos/evm/ethereum/eip712"

	dv1 "pkg.akt.dev/go/node/deployment/v1"
	dv1beta4 "pkg.akt.dev/go/node/deployment/v1beta4"
	"pkg.akt.dev/go/sdkutil"

	"pkg.akt.dev/node/v2/app"
	apptypes "pkg.akt.dev/node/v2/app/types"
)

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func anyFromMsg(reg interface {
	// codec.InterfaceRegistry satisfies this via NewProtoCodec
}, ic codec.Codec, msg sdk.Msg) (*anypb.Any, error) {
	bz, err := ic.Marshal(msg)
	if err != nil {
		return nil, err
	}
	return &anypb.Any{TypeUrl: "/" + sdk.MsgTypeURL(msg)[1:], Value: bz}, nil
}

func main() {
	// --- replicate NewRootCmd init exactly (chain/cmd/akash/cmd/root.go:34-52) ---
	encodingConfig := sdkutil.MakeEncodingConfig()
	app.ModuleBasics().RegisterLegacyAminoCodec(encodingConfig.Amino)
	app.ModuleBasics().RegisterInterfaces(encodingConfig.InterfaceRegistry)
	app.RegisterEVMCryptoInterfaces(encodingConfig.InterfaceRegistry)
	eip712.RegisterInterfaces(encodingConfig.InterfaceRegistry)
	eip712.SetEncodingConfig(encodingConfig.Amino, encodingConfig.InterfaceRegistry, apptypes.AbakosEVMChainID)
	encodingConfig.Amino.RegisterConcrete(&ethsecp256k1.PubKey{}, ethsecp256k1.PubKeyName, nil)
	encodingConfig.Amino.RegisterConcrete(&ethsecp256k1.PrivKey{}, ethsecp256k1.PrivKeyName, nil)
	legacy.Cdc.RegisterConcrete(&ethsecp256k1.PubKey{}, ethsecp256k1.PubKeyName, nil)
	legacy.Cdc.RegisterConcrete(&ethsecp256k1.PrivKey{}, ethsecp256k1.PrivKeyName, nil)
	legacytx.RegressionTestingAminoCodec = encodingConfig.Amino

	ic := codec.NewProtoCodec(encodingConfig.InterfaceRegistry)

	owner := "abakos1cy93rz4spyy4n84hmklclvc7ay9dk8kf37u725"
	msg := &dv1beta4.MsgCloseDeployment{ID: dv1.DeploymentID{Owner: owner, DSeq: 160518}}

	anyMsg, err := anyFromMsg(nil, ic, msg)
	must(err)

	handler := sdkutil.NewLegacyAminoJSONHandler(encodingConfig.Amino, encodingConfig.InterfaceRegistry)
	signBytes, err := handler.GetSignBytes(context.Background(),
		txsigning.SignerData{ChainID: "abakos-sandbox-1", AccountNumber: 17, Sequence: 60},
		txsigning.TxData{
			Body: &txv1beta1.TxBody{Messages: []*anypb.Any{anyMsg}, Memo: "console air"},
			AuthInfo: &txv1beta1.AuthInfo{Fee: &txv1beta1.Fee{
				GasLimit: 471908,
				Amount:   []*basev1beta1.Coin{{Denom: "uaba", Amount: "0"}},
			}},
		})
	must(err)

	fmt.Println("=== NODE amino sign doc (what the node signs/verifies over) ===")
	fmt.Println(string(signBytes))
	fmt.Println()
	fmt.Println("=== CONSOLE amino sign doc (from your MetaMask popup) ===")
	fmt.Println(`{"account_number":"17","chain_id":"abakos-sandbox-1","fee":{"amount":[{"amount":"0","denom":"uaba"}],"gas":"471908"},"memo":"console air","msgs":[{"type":"akash-sdk/x/deployment/MsgCloseDeployment","value":{"id":{"dseq":"160518","owner":"abakos1cy93rz4spyy4n84hmklclvc7ay9dk8kf37u725"}}}],"sequence":"60"}`)
	fmt.Println()

	fmt.Println("=== eip712 GetEIP712TypedDataForMsg(nodeSignDoc) ===")
	td, err := eip712.GetEIP712TypedDataForMsg(signBytes)
	if err != nil {
		fmt.Println(">>> ERROR:", err)
		os.Exit(0)
	}
	b, _ := json.MarshalIndent(td, "", "  ")
	fmt.Println(string(b))

	h, err := eip712.GetEIP712BytesForMsg(signBytes)
	if err != nil {
		fmt.Println(">>> hash ERROR:", err)
	} else {
		fmt.Printf("eip712 hash: %x\n", h)
	}
}
