package cmd

import (
	wasmtypes "github.com/CosmWasm/wasmd/x/wasm/types"
	serverconfig "github.com/cosmos/cosmos-sdk/server/config"
	cosmosevmserverconfig "github.com/cosmos/evm/server/config"

	apptypes "pkg.akt.dev/node/v2/app/types"
)

// AppConfig extends the SDK server config with the wasm node config and the
// Cosmos EVM server config (EVM, JSON-RPC and TLS sections). The EVM/JSON-RPC
// sections drive the eth JSON-RPC server started from the start command's
// PostSetup hook (see root.go).
type AppConfig struct {
	serverconfig.Config

	WasmConfig wasmtypes.NodeConfig                `mapstructure:"wasm"`
	EVM        cosmosevmserverconfig.EVMConfig     `mapstructure:"evm"`
	JSONRPC    cosmosevmserverconfig.JSONRPCConfig `mapstructure:"json-rpc"`
	TLS        cosmosevmserverconfig.TLSConfig     `mapstructure:"tls"`
}

var AppTemplate = serverconfig.DefaultConfigTemplate + `
###############################################################################
###                            Wasm Configuration                           ###
###############################################################################
` + wasmtypes.DefaultConfigTemplate() + cosmosevmserverconfig.DefaultEVMConfigTemplate

func InitAppConfig() (string, interface{}) {
	appCfg := AppConfig{
		Config:     *serverconfig.DefaultConfig(),
		WasmConfig: wasmtypes.DefaultNodeConfig(),
		EVM:        *cosmosevmserverconfig.DefaultEVMConfig(),
		JSONRPC:    *cosmosevmserverconfig.DefaultJSONRPCConfig(),
		TLS:        *cosmosevmserverconfig.DefaultTLSConfig(),
	}

	appCfg.MinGasPrices = "0uaba"
	appCfg.API.Enable = true
	appCfg.API.Address = "tcp://localhost:1317"

	// Cosmos EVM: enable the eth JSON-RPC server + tx indexer by default and pin
	// the EIP-155 chain id. Listens locally; a reverse proxy exposes it publicly.
	appCfg.EVM.EVMChainID = apptypes.AbakosEVMChainID
	appCfg.JSONRPC.Enable = true
	appCfg.JSONRPC.Address = "127.0.0.1:8545"
	appCfg.JSONRPC.WsAddress = "127.0.0.1:8546"
	appCfg.JSONRPC.EnableIndexer = true

	return AppTemplate, appCfg
}
