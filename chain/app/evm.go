package app

import (
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	evmcryptocodec "github.com/cosmos/evm/crypto/codec"
	erc20types "github.com/cosmos/evm/x/erc20/types"
	evmtypes "github.com/cosmos/evm/x/vm/types"

	"pkg.akt.dev/go/sdkutil"
)

// init registers the EVM custom transaction signers with the chain-sdk signing
// options *before* the encoding config is built (encoding is built in
// NewRootCmd, which runs after all package init funcs). MsgEthereumTx and
// MsgConvertERC20 derive their signer from an Ethereum signature rather than a
// bech32 field, so they need a custom get-signer function rather than the
// generic field-based one.
func init() {
	sdkutil.RegisterCustomGetSigner(
		evmtypes.MsgEthereumTxCustomGetSigner.MsgType,
		evmtypes.MsgEthereumTxCustomGetSigner.Fn,
	)
	sdkutil.RegisterCustomGetSigner(
		erc20types.MsgConvertERC20CustomGetSigner.MsgType,
		erc20types.MsgConvertERC20CustomGetSigner.Fn,
	)
}

// RegisterEVMCryptoInterfaces registers the eth_secp256k1 key types on the
// interface registry. These are required to decode and verify Ethereum
// transactions (MsgEthereumTx) and eth-keyed accounts. The EVM module message
// types themselves are registered via the module BasicManager.
func RegisterEVMCryptoInterfaces(registry codectypes.InterfaceRegistry) {
	evmcryptocodec.RegisterInterfaces(registry)
}
