package sdkutil

import (
	"cosmossdk.io/x/tx/signing"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	"github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/std"
	"github.com/cosmos/cosmos-sdk/types/module"
	signingtypes "github.com/cosmos/cosmos-sdk/types/tx/signing"
	"github.com/cosmos/cosmos-sdk/x/auth/tx"

	offchain "pkg.akt.dev/go/node/types/offchain/sign"
)

// EncodingConfig specifies the concrete encoding types to use for a given app.
// This is provided for compatibility between protobuf and amino implementations.
type EncodingConfig struct {
	InterfaceRegistry types.InterfaceRegistry
	Codec             codec.Codec
	TxConfig          client.TxConfig
	SigningOptions    signing.Options
	Amino             *codec.LegacyAmino
}

// MakeEncodingConfig creates an EncodingConfig for a proto based test configuration.
func MakeEncodingConfig(modules ...module.AppModuleBasic) EncodingConfig {
	aminoCodec := codec.NewLegacyAmino()
	co := NewCodecOptions()

	interfaceRegistry := co.NewInterfaceRegistry()

	std.RegisterLegacyAminoCodec(aminoCodec)
	std.RegisterInterfaces(interfaceRegistry)

	aminoCodec.RegisterConcrete(&offchain.MsgSignData{}, "sign/"+(&offchain.MsgSignData{}).Type(), nil)

	if len(modules) > 0 {
		mb := module.NewBasicManager(modules...)
		mb.RegisterLegacyAminoCodec(aminoCodec)
		mb.RegisterInterfaces(interfaceRegistry)
	}

	cdc := codec.NewProtoCodec(interfaceRegistry)

	signingCtx, err := signing.NewContext(co.Options)
	if err != nil {
		panic(err)
	}

	// Amino json is handled by our own codec-based handler rather than the descriptor-driven
	// default, which loses the contents of akash messages. See aminojson.go.
	enabledSignModes := make([]signingtypes.SignMode, 0, len(tx.DefaultSignModes))
	for _, mode := range tx.DefaultSignModes {
		if mode != signingtypes.SignMode_SIGN_MODE_LEGACY_AMINO_JSON {
			enabledSignModes = append(enabledSignModes, mode)
		}
	}

	txConfig, err := tx.NewTxConfigWithOptions(cdc, tx.ConfigOptions{
		EnabledSignModes: enabledSignModes,
		CustomSignModes:  []signing.SignModeHandler{NewLegacyAminoJSONHandler(aminoCodec, interfaceRegistry)},
		SigningOptions:   &co.Options,
		SigningContext:   signingCtx,
	})
	if err != nil {
		panic(err)
	}

	encCfg := EncodingConfig{
		InterfaceRegistry: interfaceRegistry,
		Codec:             cdc,
		TxConfig:          txConfig,
		Amino:             aminoCodec,
		SigningOptions:    co.Options,
	}

	return encCfg
}
