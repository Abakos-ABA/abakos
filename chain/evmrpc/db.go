package evmrpc

import (
	"path/filepath"

	dbm "github.com/cosmos/cosmos-db"
)

// OpenIndexerDB opens the custom eth tx indexer db, using the same db backend as
// the main app. Copied from cosmos/evm's server package (which we cannot import
// wholesale because its start.go targets vanilla CometBFT's node.NewNode, which
// differs from akash's CometBFT fork).
func OpenIndexerDB(rootDir string, backendType dbm.BackendType) (dbm.DB, error) {
	dataDir := filepath.Join(rootDir, "data")
	return dbm.NewDB("evmindexer", backendType, dataDir)
}
