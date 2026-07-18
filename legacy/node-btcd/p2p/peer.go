package p2p

import (
	"net"

	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/connmgr"
	"github.com/btcsuite/btcd/peer"
	"github.com/btcsuite/btcd/wire"
)

type nodePeer struct {
	*peer.Peer
	server         *Server
	connReq        *connmgr.ConnReq
	blockProcessed chan struct{}
}

func newNodePeer(s *Server) *nodePeer {
	return &nodePeer{
		server:         s,
		blockProcessed: make(chan struct{}, 1),
	}
}

func (np *nodePeer) peerConfig() *peer.Config {
	return &peer.Config{
		Listeners: peer.MessageListeners{
			OnVersion:    np.onVersion,
			OnVerAck:     np.onVerAck,
			OnBlock:      np.onBlock,
			OnInv:        np.onInv,
			OnHeaders:    np.onHeaders,
			OnGetData:    np.onGetData,
			OnGetBlocks:  np.onGetBlocks,
			OnGetHeaders: np.onGetHeaders,
		},
		NewestBlock: func() (*chainhash.Hash, int32, error) {
			best := np.server.chain.BestSnapshot()
			return &best.Hash, best.Height, nil
		},
		HostToNetAddress: np.server.addrManager.HostToNetAddress,
		UserAgentName:    userAgent,
		UserAgentVersion: "0.0.6-dev",
		ChainParams:      np.server.params,
		Services:         wire.SFNodeNetwork | wire.SFNodeWitness,
		DisableRelayTx:   true,
		ProtocolVersion:  peer.MaxProtocolVersion,
		AllowSelfConns:   true, // simnet tests run multiple nodes in one process
	}
}

func (s *Server) inboundConnected(conn net.Conn) {
	np := newNodePeer(s)
	np.Peer = peer.NewInboundPeer(np.peerConfig())
	np.AssociateConnection(conn)
	go s.peerDone(np)
}

func (s *Server) outboundConnected(c *connmgr.ConnReq, conn net.Conn) {
	np := newNodePeer(s)
	np.connReq = c
	p, err := peer.NewOutboundPeer(np.peerConfig(), c.Addr.String())
	if err != nil {
		if c.Permanent {
			s.connManager.Disconnect(c.ID())
		}
		return
	}
	np.Peer = p
	np.AssociateConnection(conn)
	go s.peerDone(np)
}

func (s *Server) peerDone(np *nodePeer) {
	np.WaitForDisconnect()
	s.removePeer(np)
}

func (np *nodePeer) onVersion(_ *peer.Peer, _ *wire.MsgVersion) *wire.MsgReject {
	return nil
}

func (np *nodePeer) onVerAck(_ *peer.Peer, _ *wire.MsgVerAck) {
	np.server.addPeer(np)
}

func (np *nodePeer) onBlock(_ *peer.Peer, msg *wire.MsgBlock, _ []byte) {
	// Use NewBlock, not NewBlockFromBlockAndBytes: btcutil assumes an 80-byte
	// header when slicing serializedBlock for tx hashes; Abakos headers are 110
	// bytes plus a certificate prefix.
	block := btcutil.NewBlock(msg)
	iv := wire.NewInvVect(wire.InvTypeBlock, block.Hash())
	np.AddKnownInventory(iv)
	np.server.syncManager.QueueBlock(block, np.Peer, np.blockProcessed)
	<-np.blockProcessed
}

func (np *nodePeer) onInv(_ *peer.Peer, msg *wire.MsgInv) {
	filtered := wire.NewMsgInvSizeHint(uint(len(msg.InvList)))
	for _, iv := range msg.InvList {
		if iv.Type == wire.InvTypeTx {
			continue
		}
		_ = filtered.AddInvVect(iv)
	}
	if len(filtered.InvList) > 0 {
		np.server.syncManager.QueueInv(filtered, np.Peer)
	}
}

func (np *nodePeer) onHeaders(_ *peer.Peer, msg *wire.MsgHeaders) {
	np.server.syncManager.QueueHeaders(msg, np.Peer)
}

func (np *nodePeer) onGetData(_ *peer.Peer, msg *wire.MsgGetData) {
	doneChan := make(chan struct{}, 1)
	for i, iv := range msg.InvList {
		var c chan struct{}
		if i == len(msg.InvList)-1 {
			c = doneChan
		}
		switch iv.Type {
		case wire.InvTypeWitnessBlock:
			_ = np.server.pushBlock(np, &iv.Hash, c, wire.WitnessEncoding)
		case wire.InvTypeBlock:
			_ = np.server.pushBlock(np, &iv.Hash, c, wire.BaseEncoding)
		default:
			if c != nil {
				c <- struct{}{}
			}
		}
	}
	if len(msg.InvList) > 0 {
		<-doneChan
	}
}

func (np *nodePeer) onGetBlocks(_ *peer.Peer, msg *wire.MsgGetBlocks) {
	hashList := np.server.chain.LocateBlocks(msg.BlockLocatorHashes, &msg.HashStop, wire.MaxBlocksPerMsg)
	inv := wire.NewMsgInv()
	for i := range hashList {
		_ = inv.AddInvVect(wire.NewInvVect(wire.InvTypeBlock, &hashList[i]))
	}
	if len(inv.InvList) > 0 {
		np.QueueMessage(inv, nil)
	}
}

func (np *nodePeer) onGetHeaders(_ *peer.Peer, msg *wire.MsgGetHeaders) {
	headers := np.server.chain.LocateHeaders(msg.BlockLocatorHashes, &msg.HashStop)
	blockHeaders := make([]*wire.BlockHeader, len(headers))
	for i := range headers {
		blockHeaders[i] = &headers[i]
	}
	np.QueueMessage(&wire.MsgHeaders{Headers: blockHeaders}, nil)
}
