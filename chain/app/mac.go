package app

import (
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	distrtypes "github.com/cosmos/cosmos-sdk/x/distribution/types"
	govtypes "github.com/cosmos/cosmos-sdk/x/gov/types"
	minttypes "github.com/cosmos/cosmos-sdk/x/mint/types"
	stakingtypes "github.com/cosmos/cosmos-sdk/x/staking/types"
	ibctransfertypes "github.com/cosmos/ibc-go/v10/modules/apps/transfer/types"
	emodule "pkg.akt.dev/go/node/escrow/module"

	bmemodule "pkg.akt.dev/node/v2/x/bme"

	// Cosmos EVM module accounts
	erc20types "github.com/cosmos/evm/x/erc20/types"
	feemarkettypes "github.com/cosmos/evm/x/feemarket/types"
	precisebanktypes "github.com/cosmos/evm/x/precisebank/types"
	evmtypes "github.com/cosmos/evm/x/vm/types"
)

func ModuleAccountPerms() map[string][]string {
	return map[string][]string{
		authtypes.FeeCollectorName:     nil,
		bmemodule.ModuleName:           {authtypes.Burner, authtypes.Minter},
		emodule.ModuleName:             nil,
		distrtypes.ModuleName:          nil,
		minttypes.ModuleName:           {authtypes.Minter},
		stakingtypes.BondedPoolName:    {authtypes.Burner, authtypes.Staking},
		stakingtypes.NotBondedPoolName: {authtypes.Burner, authtypes.Staking},
		govtypes.ModuleName:            {authtypes.Burner},
		ibctransfertypes.ModuleName:    {authtypes.Minter, authtypes.Burner},
		// Cosmos EVM
		evmtypes.ModuleName:          {authtypes.Minter, authtypes.Burner},
		feemarkettypes.ModuleName:    nil,
		erc20types.ModuleName:        {authtypes.Minter, authtypes.Burner},
		precisebanktypes.ModuleName:  {authtypes.Minter, authtypes.Burner},
	}
}

func ModuleAccountAddrs() map[string]bool {
	perms := ModuleAccountPerms()
	addrs := make(map[string]bool, len(perms))
	for k := range perms {
		addrs[authtypes.NewModuleAddress(k).String()] = true
	}
	return addrs
}
