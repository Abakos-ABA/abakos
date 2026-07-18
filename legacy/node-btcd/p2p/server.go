package p2p

import (
	"bytes"
	"fmt"
	"net"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/btcsuite/btcd/addrmgr"
	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/connmgr"
	"github.com/btcsuite/btcd/database"
	_ "github.com/btcsuite/btcd/database/ffldb"
	"github.com/btcsuite/btcd/mempool"
	"github.com/btcsuite/btcd/netsync"
	"github.com/btcsuite/btcd/peer"
	"github.com/btcsuite/btcd/wire"
	"github.com/rexmarlon/abakos/node/chain"
	abchaincfg "github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/jobs"
	"github.com/rexmarlon/abakos/node/pouw"
)

const userAgent = "abkd"

func init() {
	netsync.DisableLog()
}

// Server is a minimal btcd P2P + netsync node for Abakos simnet.
type Server struct {
	cfg    Config
	params *chaincfg.Params
	db     database.DB
	chain  *blockchain.BlockChain
	txMemPool   *mempool.TxPool
	syncManager *netsync.SyncManager
	connManager *connmgr.ConnManager
	addrManager *addrmgr.AddrManager
	listeners   []net.Listener
	timeSource  blockchain.MedianTimeSource
	feeEstimator *mempool.FeeEstimator

	peers    map[int32]*nodePeer
	peersMtx sync.RWMutex

	relayInv          chan relayMsg
	broadcast         chan broadcastMsg
	newPeers          chan *nodePeer
	donePeers         chan *nodePeer
	peerHeightsUpdate chan updateHeightsMsg
	query             chan interface{}
	quit              chan struct{}
	wg                sync.WaitGroup
	started           int32
}

type relayMsg struct {
	invVect *wire.InvVect
	data    interface{}
}

type broadcastMsg struct {
	message      wire.Message
	excludePeers []*nodePeer
}

type updateHeightsMsg struct {
	newHash    *chainhash.Hash
	newHeight  int32
	originPeer *peer.Peer
}

type getConnCountMsg struct {
	reply chan int32
}

// NewServer opens the chain DB and wires netsync for Abakos simnet.
func NewServer(cfg Config) (*Server, error) {
	if cfg.Verifier == nil {
		cfg.Verifier = pouw.CPUGEMMVerifier{}
	}
	chain.SetSimNetVerifier(cfg.Verifier)

	params, err := chain.AbakosSimNetBtcdParams()
	if err != nil {
		return nil, err
	}
	if cfg.MaxPeers <= 0 {
		cfg.MaxPeers = 8
	}

	dbPath := cfg.DataDir
	if dbPath == "" {
		dbPath = "."
	}
	db, err := database.Create("ffldb", dbPath, wire.SimNet)
	if err != nil {
		return nil, fmt.Errorf("p2p: open db: %w", err)
	}

	s := &Server{
		cfg:               cfg,
		params:            params,
		db:                db,
		timeSource:        blockchain.NewMedianTime(),
		peers:             make(map[int32]*nodePeer),
		relayInv:          make(chan relayMsg, cfg.MaxPeers),
		broadcast:         make(chan broadcastMsg, cfg.MaxPeers),
		newPeers:          make(chan *nodePeer, cfg.MaxPeers),
		donePeers:         make(chan *nodePeer, cfg.MaxPeers),
		peerHeightsUpdate: make(chan updateHeightsMsg, cfg.MaxPeers),
		query:             make(chan interface{}),
		quit:              make(chan struct{}),
	}

	s.addrManager = addrmgr.New(cfg.DataDir, net.LookupIP)

	s.chain, err = blockchain.New(&blockchain.Config{
		DB:          db,
		ChainParams: params,
		TimeSource:  s.timeSource,
	})
	if err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("p2p: blockchain: %w", err)
	}

	s.feeEstimator = mempool.NewFeeEstimator(
		mempool.DefaultEstimateFeeMaxRollback,
		mempool.DefaultEstimateFeeMinRegisteredBlocks,
	)

	txCfg := mempool.Config{
		Policy: mempool.Policy{
			DisableRelayPriority: true,
			AcceptNonStd:         false,
			FreeTxRelayLimit:     0,
			MaxOrphanTxs:         0,
			MinRelayTxFee:        btcutil.Amount(1e8),
			MaxTxVersion:         2,
		},
		ChainParams:    params,
		FetchUtxoView:  s.chain.FetchUtxoView,
		BestHeight:     func() int32 { return s.chain.BestSnapshot().Height },
		MedianTimePast: func() time.Time { return s.chain.BestSnapshot().MedianTime },
		CalcSequenceLock: func(tx *btcutil.Tx, view *blockchain.UtxoViewpoint) (*blockchain.SequenceLock, error) {
			return s.chain.CalcSequenceLock(tx, view, true)
		},
		IsDeploymentActive: s.chain.IsDeploymentActive,
		FeeEstimator:       s.feeEstimator,
	}
	s.txMemPool = mempool.New(&txCfg)

	s.syncManager, err = netsync.New(&netsync.Config{
		PeerNotifier:       s,
		Chain:              s.chain,
		TxMemPool:          s.txMemPool,
		ChainParams:        params,
		DisableCheckpoints: true,
		MaxPeers:           cfg.MaxPeers,
		FeeEstimator:       s.feeEstimator,
	})
	if err != nil {
		_ = db.Close()
		return nil, err
	}

	var listeners []net.Listener
	if cfg.Listen != "" {
		ln, err := net.Listen("tcp", cfg.Listen)
		if err != nil {
			_ = db.Close()
			return nil, err
		}
		listeners = append(listeners, ln)
	}
	s.listeners = listeners

	targetOutbound := uint32(2)
	if cfg.MaxPeers < int(targetOutbound) {
		targetOutbound = uint32(cfg.MaxPeers)
	}

	cm, err := connmgr.New(&connmgr.Config{
		Listeners:      listeners,
		OnAccept:       s.inboundConnected,
		RetryDuration:  connectionRetry,
		TargetOutbound: targetOutbound,
		Dial: func(addr net.Addr) (net.Conn, error) {
			return net.Dial(addr.Network(), addr.String())
		},
		OnConnection:   s.outboundConnected,
	})
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	s.connManager = cm

	for _, addr := range cfg.Connect {
		netAddr, err := addrToNetAddr(addr)
		if err != nil {
			_ = db.Close()
			return nil, fmt.Errorf("p2p: connect addr %q: %w", addr, err)
		}
		go s.connManager.Connect(&connmgr.ConnReq{Addr: netAddr, Permanent: true})
	}

	return s, nil
}

// Chain returns the btcd blockchain instance.
func (s *Server) Chain() *blockchain.BlockChain { return s.chain }

// Start begins P2P and sync.
func (s *Server) Start() {
	if !atomic.CompareAndSwapInt32(&s.started, 0, 1) {
		return
	}
	s.wg.Add(1)
	go s.peerHandler()
	if s.cfg.Mine {
		go s.mineLoop()
	}
}

// Stop shuts down the node.
func (s *Server) Stop() {
	select {
	case <-s.quit:
		return
	default:
		close(s.quit)
	}
	s.wg.Wait()
	_ = s.db.Close()
}

// FetchMsgBlock loads a block from the local database (for tests).
func (s *Server) FetchMsgBlock(hash chainhash.Hash) (*wire.MsgBlock, error) {
	var blockBytes []byte
	err := s.db.View(func(tx database.Tx) error {
		var err error
		blockBytes, err = tx.FetchBlock(&hash)
		return err
	})
	if err != nil {
		return nil, err
	}
	var msg wire.MsgBlock
	if err := msg.Deserialize(bytes.NewReader(blockBytes)); err != nil {
		return nil, err
	}
	return &msg, nil
}

// ProcessBlockLocal validates and connects a block without P2P.
func (s *Server) ProcessBlockLocal(block *btcutil.Block) error {
	_, err := s.syncManager.ProcessBlock(block, blockchain.BFNone)
	return err
}
func (s *Server) ListenAddr() string {
	if len(s.listeners) == 0 {
		return ""
	}
	return s.listeners[0].Addr().String()
}

// BestHeight returns the current chain tip height.
func (s *Server) BestHeight() int32 {
	return s.chain.BestSnapshot().Height
}

// PeerCount returns connected peers.
func (s *Server) PeerCount() int32 {
	ch := make(chan int32, 1)
	select {
	case s.query <- getConnCountMsg{reply: ch}:
		return <-ch
	case <-s.quit:
		return 0
	}
}

// MineOne mines a single block (exported for tests and manual mining).
func (s *Server) MineOne() error {
	return s.mineNext()
}

// AnnounceNewTransactions implements netsync.PeerNotifier (no-op).
func (s *Server) AnnounceNewTransactions([]*mempool.TxDesc) {}

// TransactionConfirmed implements netsync.PeerNotifier (no-op).
func (s *Server) TransactionConfirmed(*btcutil.Tx) {}

// UpdatePeerHeights implements netsync.PeerNotifier.
func (s *Server) UpdatePeerHeights(latestBlkHash *chainhash.Hash, latestHeight int32, updateSource *peer.Peer) {
	select {
	case s.peerHeightsUpdate <- updateHeightsMsg{newHash: latestBlkHash, newHeight: latestHeight, originPeer: updateSource}:
	case <-s.quit:
	}
}

// RelayInventory implements netsync.PeerNotifier.
func (s *Server) RelayInventory(invVect *wire.InvVect, data interface{}) {
	select {
	case s.relayInv <- relayMsg{invVect: invVect, data: data}:
	case <-s.quit:
	}
}

func (s *Server) peerHandler() {
	defer s.wg.Done()
	s.addrManager.Start()
	s.syncManager.Start()
	go s.connManager.Start()

	for {
		select {
		case p := <-s.newPeers:
			s.peersMtx.Lock()
			s.peers[p.ID()] = p
			s.peersMtx.Unlock()
			s.syncManager.NewPeer(p.Peer)

		case p := <-s.donePeers:
			s.peersMtx.Lock()
			delete(s.peers, p.ID())
			s.peersMtx.Unlock()
			if p.VerAckReceived() {
				s.syncManager.DonePeer(p.Peer)
			}

		case msg := <-s.relayInv:
			s.forEachPeer(func(p *nodePeer) {
				if !p.Connected() {
					return
				}
				if msg.invVect.Type == wire.InvTypeBlock && p.WantsHeaders() {
					if hdr, ok := msg.data.(wire.BlockHeader); ok {
						headers := wire.NewMsgHeaders()
						_ = headers.AddBlockHeader(&hdr)
						p.QueueMessage(headers, nil)
						return
					}
				}
				p.QueueInventory(msg.invVect)
			})

		case bmsg := <-s.broadcast:
			s.forEachPeer(func(p *nodePeer) {
				if !p.Connected() {
					return
				}
				for _, ex := range bmsg.excludePeers {
					if p == ex {
						return
					}
				}
				p.QueueMessage(bmsg.message, nil)
			})

		case umsg := <-s.peerHeightsUpdate:
			s.forEachPeer(func(p *nodePeer) {
				if p.Peer == umsg.originPeer {
					return
				}
				last := p.LastAnnouncedBlock()
				if last != nil && *last == *umsg.newHash {
					p.UpdateLastBlockHeight(umsg.newHeight)
					p.UpdateLastAnnouncedBlock(nil)
				}
			})

		case q := <-s.query:
			if msg, ok := q.(getConnCountMsg); ok {
				var n int32
				s.forEachPeer(func(p *nodePeer) {
					if p.Connected() {
						n++
					}
				})
				msg.reply <- n
			}

		case <-s.quit:
			s.forEachPeer(func(p *nodePeer) { p.Disconnect() })
			s.connManager.Stop()
			s.syncManager.Stop()
			s.addrManager.Stop()
			return
		}
	}
}

func (s *Server) forEachPeer(fn func(*nodePeer)) {
	s.peersMtx.RLock()
	defer s.peersMtx.RUnlock()
	for _, p := range s.peers {
		fn(p)
	}
}

func (s *Server) addPeer(np *nodePeer) {
	select {
	case s.newPeers <- np:
	case <-s.quit:
	}
}

func (s *Server) removePeer(np *nodePeer) {
	select {
	case s.donePeers <- np:
	case <-s.quit:
	}
}

func (s *Server) mineLoop() {
	time.Sleep(500 * time.Millisecond)
	for {
		select {
		case <-s.quit:
			return
		default:
		}
		if s.cfg.MaxBlocks > 0 && int(s.BestHeight()) >= s.cfg.MaxBlocks-1 {
			return
		}
		if err := s.mineNext(); err != nil {
			time.Sleep(time.Second)
			continue
		}
		time.Sleep(300 * time.Millisecond)
	}
}

func (s *Server) mineNext() error {
	best := s.chain.BestSnapshot()
	ts := best.MedianTime.Add(abchaincfg.TargetBlockTime())
	header := nextPouwHeader(*best, s.cfg.UsefulBps, ts)
	if s.cfg.UsefulBps > 0 {
		header.ProofCommitment = jobs.Global.RegisterDemoFunded("simnet-paid")
	}

	height := best.Height + 1
	base := blockchain.CalcBlockSubsidy(height, s.params)
	subsidy := chain.AdjustedCoinbaseSubsidy(base, s.cfg.UsefulBps)
	header.MerkleRoot = chain.CoinbaseMerkleRoot(height, subsidy)

	mined, err := chain.Mine(header, s.cfg.Verifier)
	if err != nil {
		return err
	}
	msg, err := chain.BuildBtcdMsgBlock(best.Hash, mined.Header, mined.Proof, height, subsidy)
	if err != nil {
		return err
	}
	block := btcutil.NewBlock(msg)
	block.SetHeight(height)

	_, err = s.syncManager.ProcessBlock(block, blockchain.BFNone)
	if err != nil {
		return err
	}
	iv := wire.NewInvVect(wire.InvTypeBlock, block.Hash())
	s.RelayInventory(iv, msg.Header)
	if s.cfg.OnBlock != nil {
		s.cfg.OnBlock(height, block.Hash().String())
	}
	return nil
}

func nextPouwHeader(best blockchain.BestState, usefulBps uint16, ts time.Time) pouw.Header {
	var prev [32]byte
	copy(prev[:], best.Hash[:])
	return pouw.Header{
		Version:        chain.AbakosBlockVersion,
		PrevBlock:      prev,
		Timestamp:      ts,
		Bits:           abchaincfg.SimNetEasyBits,
		UsefulRatioBps: usefulBps,
	}
}

func (s *Server) pushBlock(np *nodePeer, hash *chainhash.Hash, done chan<- struct{}, encoding wire.MessageEncoding) error {
	var blockBytes []byte
	err := s.db.View(func(tx database.Tx) error {
		var err error
		blockBytes, err = tx.FetchBlock(hash)
		return err
	})
	if err != nil {
		if done != nil {
			done <- struct{}{}
		}
		return err
	}
	var msgBlock wire.MsgBlock
	if err := msgBlock.Deserialize(bytes.NewReader(blockBytes)); err != nil {
		if done != nil {
			done <- struct{}{}
		}
		return err
	}
	np.QueueMessageWithEncoding(&msgBlock, done, encoding)
	return nil
}

func addrToNetAddr(addr string) (net.Addr, error) {
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		return nil, err
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return nil, err
	}
	if ip := net.ParseIP(host); ip != nil {
		return &net.TCPAddr{IP: ip, Port: port}, nil
	}
	ips, err := net.LookupIP(host)
	if err != nil || len(ips) == 0 {
		return nil, fmt.Errorf("p2p: lookup %s: %w", host, err)
	}
	return &net.TCPAddr{IP: ips[0], Port: port}, nil
}
