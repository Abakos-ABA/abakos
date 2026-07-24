package sdkutil

import (
	"context"
	"encoding/json"
	"fmt"

	signingv1beta1 "cosmossdk.io/api/cosmos/tx/signing/v1beta1"
	sdkmath "cosmossdk.io/math"
	txsigning "cosmossdk.io/x/tx/signing"

	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/x/auth/migrations/legacytx"
)

// LegacyAminoJSONHandler builds SIGN_MODE_LEGACY_AMINO_JSON sign bytes with the legacy amino
// codec, replacing the descriptor-driven encoder that cosmos-sdk wires up by default.
//
// The default handler (cosmossdk.io/x/tx/signing/aminojson) reads protobuf descriptors. Akash
// protos are only registered in gogoproto's registry, never in protoregistry.GlobalFiles —
// buf.gen.pulsar.yaml exists but was never generated — so an imported message type resolves to a
// placeholder with no fields. Two consequences, both bad:
//
//  1. MsgCreateDeployment signs over `"groups":[{}]`. The resources and the price the tenant
//     agrees to are simply absent from the signed bytes, while the tx body carries them in full.
//     Anyone relaying such a tx can rewrite what is deployed and what it costs without breaking
//     the signature.
//  2. Without `option (amino.name)` the type falls back to the proto type url, so cosmos/evm
//     derives the EIP-712 type name "Typeakash.deployment.v1beta4.MsgCreateDeployment". go-ethereum
//     rejects type names containing dots, so MetaMask cannot sign any akash message at all.
//
// The legacy codec has neither problem: it marshals the Go structs, so nothing is lost, and it
// uses the names the modules already register via RegisterConcrete
// ("akash-sdk/x/deployment/MsgCreateDeployment"), which contain no dots. Those registrations
// exist in every module's codec.go and were dead code until now.
//
// Making the amino json lossless also fixes clients: cosmjs rebuilds the tx body from the signed
// amino messages, so a lossy encoding made it broadcast deployments with no groups at all.
type LegacyAminoJSONHandler struct {
	cdc      *codec.LegacyAmino
	registry codectypes.InterfaceRegistry
}

// NewLegacyAminoJSONHandler returns a handler that signs over legacy amino json. The codec is
// held by reference, so module registrations that happen after construction are picked up.
func NewLegacyAminoJSONHandler(cdc *codec.LegacyAmino, registry codectypes.InterfaceRegistry) LegacyAminoJSONHandler {
	return LegacyAminoJSONHandler{cdc: cdc, registry: registry}
}

func (LegacyAminoJSONHandler) Mode() signingv1beta1.SignMode {
	return signingv1beta1.SignMode_SIGN_MODE_LEGACY_AMINO_JSON
}

func (h LegacyAminoJSONHandler) GetSignBytes(_ context.Context, signerData txsigning.SignerData, txData txsigning.TxData) ([]byte, error) {
	if txData.Body == nil {
		return nil, fmt.Errorf("amino json: tx has no body")
	}

	msgs := make([]sdk.Msg, len(txData.Body.Messages))
	for i, anyMsg := range txData.Body.Messages {
		// The messages arrive as protov2 Any; unpack them through the interface registry to get
		// the gogo message the legacy codec knows how to marshal.
		var msg sdk.Msg
		packed := &codectypes.Any{TypeUrl: anyMsg.TypeUrl, Value: anyMsg.Value}
		if err := h.registry.UnpackAny(packed, &msg); err != nil {
			return nil, fmt.Errorf("amino json: cannot unpack message %d (%s): %w", i, anyMsg.TypeUrl, err)
		}
		msgs[i] = msg
	}

	fee := legacytx.StdFee{Gas: 0, Amount: sdk.Coins{}}
	if txData.AuthInfo != nil && txData.AuthInfo.Fee != nil {
		fee.Gas = txData.AuthInfo.Fee.GasLimit
		fee.Payer = txData.AuthInfo.Fee.Payer
		fee.Granter = txData.AuthInfo.Fee.Granter

		amount := make(sdk.Coins, len(txData.AuthInfo.Fee.Amount))
		for i, coin := range txData.AuthInfo.Fee.Amount {
			parsed, ok := sdkmath.NewIntFromString(coin.Amount)
			if !ok {
				return nil, fmt.Errorf("amino json: invalid fee amount %q", coin.Amount)
			}
			amount[i] = sdk.Coin{Denom: coin.Denom, Amount: parsed}
		}
		fee.Amount = amount
	}

	// legacytx.StdSignBytes would do this, but it marshals through package-level codecs that the
	// app has to remember to set. Building the doc here keeps the handler self-contained.
	msgsBytes := make([]json.RawMessage, len(msgs))
	for i, msg := range msgs {
		bz, err := h.cdc.MarshalJSON(msg)
		if err != nil {
			return nil, fmt.Errorf("amino json: cannot marshal message %d: %w", i, err)
		}
		msgsBytes[i] = sdk.MustSortJSON(bz)
	}

	feeBytes, err := h.cdc.MarshalJSON(fee)
	if err != nil {
		return nil, fmt.Errorf("amino json: cannot marshal fee: %w", err)
	}

	doc, err := h.cdc.MarshalJSON(legacytx.StdSignDoc{
		AccountNumber: signerData.AccountNumber,
		Sequence:      signerData.Sequence,
		TimeoutHeight: txData.Body.TimeoutHeight,
		ChainID:       signerData.ChainID,
		Memo:          txData.Body.Memo,
		Fee:           sdk.MustSortJSON(feeBytes),
		Msgs:          msgsBytes,
	})
	if err != nil {
		return nil, fmt.Errorf("amino json: cannot marshal sign doc: %w", err)
	}

	return sdk.MustSortJSON(doc), nil
}
