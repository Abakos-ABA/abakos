package evmrpc

import (
	"net"

	"golang.org/x/net/netutil"

	serverconfig "github.com/cosmos/evm/server/config"
)

// Listen starts a net.Listener on the tcp network for the given address,
// applying the JSON-RPC MaxOpenConnections limit if configured. Copied from
// cosmos/evm's server package (see db.go for why the helpers are vendored here).
func Listen(addr string, config *serverconfig.Config) (net.Listener, error) {
	if addr == "" {
		addr = ":http"
	}
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return nil, err
	}
	if config.JSONRPC.MaxOpenConnections > 0 {
		ln = netutil.LimitListener(ln, config.JSONRPC.MaxOpenConnections)
	}
	return ln, err
}
