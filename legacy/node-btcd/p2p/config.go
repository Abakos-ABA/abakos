// Package p2p runs a slim btcd netsync node for Abakos simnet (T0.5).
package p2p

import (
	"time"

	"github.com/rexmarlon/abakos/node/pouw"
)

// Config holds Abakos btcd P2P settings.
type Config struct {
	DataDir    string
	Listen     string   // e.g. ":18555"
	Connect    []string // outbound peers
	MaxPeers   int
	Mine       bool
	MaxBlocks  int
	UsefulBps  uint16
	Verifier   pouw.WorkVerifier
	OnBlock    func(height int32, hash string)
}

// DefaultConfig returns simnet-friendly defaults.
func DefaultConfig() Config {
	return Config{
		MaxPeers: 8,
		Verifier: pouw.CPUGEMMVerifier{},
	}
}

const connectionRetry = 5 * time.Second
