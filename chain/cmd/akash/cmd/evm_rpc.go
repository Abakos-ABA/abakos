package cmd

import (
	"context"
	"errors"

	"github.com/spf13/cobra"
	"golang.org/x/sync/errgroup"

	cmtcmd "github.com/cometbft/cometbft/cmd/cometbft/commands"
	rpcclient "github.com/cometbft/cometbft/rpc/client"

	"github.com/cosmos/cosmos-sdk/client"
	sdkserver "github.com/cosmos/cosmos-sdk/server"
	servercmtlog "github.com/cosmos/cosmos-sdk/server/log"
	"github.com/cosmos/cosmos-sdk/version"

	"github.com/cosmos/evm/indexer"
	cosmosevmserverconfig "github.com/cosmos/evm/server/config"
	evmservertypes "github.com/cosmos/evm/server/types"

	"pkg.akt.dev/go/cli"
	evmrpc "pkg.akt.dev/node/v2/evmrpc"
)

// evmServerCmds mirrors akash's cli.ServerCmds but builds the `start` command via
// StartCmdWithOptions so we can inject the eth JSON-RPC PostSetup hook. All other
// server subcommands (comet, export, rollback, ...) are registered identically.
func evmServerCmds(rootCmd *cobra.Command, defaultNodeHome string, ac appCreator, addStartFlags func(*cobra.Command)) {
	cometCmd := &cobra.Command{
		Use:     "comet",
		Aliases: []string{"cometbft", "tendermint"},
		Short:   "CometBFT subcommands",
	}
	cometCmd.AddCommand(
		cli.ShowNodeIDCmd(),
		cli.ShowValidatorCmd(),
		cli.ShowAddressCmd(),
		cli.VersionCmd(),
		cmtcmd.ResetAllCmd,
		cmtcmd.ResetStateCmd,
		cli.BootstrapStateCmd(ac.newApp),
		cli.GetValidatorSetCmd(),
	)

	startCmd := cli.StartCmdWithOptions(ac.newApp, defaultNodeHome, cli.StartCmdOptions{
		PostSetup: evmJSONRPCPostSetup,
	})
	addStartFlags(startCmd)

	rootCmd.AddCommand(
		startCmd,
		cometCmd,
		cli.ExportCmd(ac.appExport, defaultNodeHome),
		version.NewVersionCommand(),
		cli.NewRollbackCmd(ac.newApp, defaultNodeHome),
		cli.ModuleHashByHeightQuery(ac.newApp),
	)
}

// evmJSONRPCPostSetup starts the Ethereum JSON-RPC server (and its optional tx
// indexer) in-process alongside the node, sharing the same cancellable context
// and errgroup. Enabled via the [json-rpc] section of app.toml. Mirrors cosmos/evm's
// server/start.go wiring, adapted to akash's start command hook.
func evmJSONRPCPostSetup(svrCtx *sdkserver.Context, clientCtx client.Context, ctx context.Context, g *errgroup.Group) error {
	config, err := cosmosevmserverconfig.GetConfig(svrCtx.Viper)
	if err != nil {
		return err
	}
	if !config.JSONRPC.Enable {
		return nil
	}
	if startedApp == nil {
		return errors.New("evm json-rpc: app instance was not captured")
	}
	if clientCtx.Client == nil {
		return errors.New("evm json-rpc: client context has no CometBFT client")
	}

	home := svrCtx.Config.RootDir

	var idxer evmservertypes.EVMTxIndexer
	if config.JSONRPC.EnableIndexer {
		idxDB, err := evmrpc.OpenIndexerDB(home, sdkserver.GetAppDBBackend(svrCtx.Viper))
		if err != nil {
			return err
		}
		idxLogger := svrCtx.Logger.With("indexer", "evm")
		kvIndexer := indexer.NewKVIndexer(idxDB, idxLogger, clientCtx)
		idxer = kvIndexer

		indexerService := evmrpc.NewEVMIndexerService(kvIndexer, clientCtx.Client.(rpcclient.Client))
		indexerService.SetLogger(servercmtlog.CometLoggerWrapper{Logger: idxLogger})

		g.Go(func() error {
			errCh := make(chan error, 1)
			go func() {
				if err := indexerService.Start(); err != nil {
					errCh <- err
				}
			}()
			select {
			case <-ctx.Done():
				return indexerService.Stop()
			case err := <-errCh:
				return err
			}
		})
	}

	if _, err := evmrpc.StartJSONRPC(ctx, svrCtx, clientCtx, g, &config, idxer, startedApp, nil); err != nil {
		return err
	}
	svrCtx.Logger.Info("Ethereum JSON-RPC server enabled", "address", config.JSONRPC.Address)
	return nil
}
