// Package simnet runs a minimal two-node TCP block sync for T0 (pre-btcd P2P).
package simnet

import (
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"sync"
	"time"

	"github.com/rexmarlon/abakos/node/chain"
	"github.com/rexmarlon/abakos/node/wire"
)

const magic = "ABAB"

const (
	msgBlock byte = 1
	msgInv   byte = 2
	msgGet   byte = 3
)

// Node is a T0 simnet peer with in-memory chain and optional mining.
type Node struct {
	Chain    *chain.Chain
	listen   string
	peers    []string
	mu       sync.Mutex
	onBlock  func(*chain.Block)
	quit     chan struct{}
	listener net.Listener
}

// NewNode creates a simnet node. Call Run to start networking.
func NewNode(c *chain.Chain, listen string, peers []string) *Node {
	return &Node{
		Chain:  c,
		listen: listen,
		peers:  peers,
		quit:   make(chan struct{}),
	}
}

// OnBlock sets a callback invoked when a new block is accepted (local or peer).
func (n *Node) OnBlock(fn func(*chain.Block)) {
	n.onBlock = fn
}

// PublishBlock announces a locally mined block to peers and invokes callback.
func (n *Node) PublishBlock(b *chain.Block) {
	if n.onBlock != nil {
		n.onBlock(b)
	}
	n.broadcastBlock(b)
}

// Run starts the listener and outbound peer connections until Stop.
func (n *Node) Run() error {
	if n.listen != "" {
		ln, err := net.Listen("tcp", n.listen)
		if err != nil {
			return err
		}
		n.listener = ln
		go n.acceptLoop(ln)
	}
	for _, addr := range n.peers {
		go n.dialPeer(addr)
	}
	return nil
}

// Stop shuts down the node.
func (n *Node) Stop() {
	close(n.quit)
	if n.listener != nil {
		_ = n.listener.Close()
	}
}

func (n *Node) acceptLoop(ln net.Listener) {
	for {
		conn, err := ln.Accept()
		if err != nil {
			select {
			case <-n.quit:
				return
			default:
			}
			continue
		}
		go n.serveConn(conn)
	}
}

func (n *Node) dialPeer(addr string) {
	for {
		select {
		case <-n.quit:
			return
		default:
		}
		conn, err := net.DialTimeout("tcp", addr, 3*time.Second)
		if err != nil {
			time.Sleep(2 * time.Second)
			continue
		}
		go n.readLoop(conn)
		return
	}
}

func (n *Node) serveConn(conn net.Conn) {
	defer conn.Close()
	_ = n.sendChain(conn)
	n.readLoop(conn)
}

func (n *Node) readLoop(conn net.Conn) {
	for {
		select {
		case <-n.quit:
			return
		default:
		}
		_ = conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		typ, payload, err := readMsg(conn)
		if err != nil {
			return
		}
		switch typ {
		case msgBlock:
			if err := n.handleBlock(payload); err != nil {
				return
			}
		case msgGet:
			_ = n.sendChain(conn)
		}
	}
}

func (n *Node) handleBlock(payload []byte) error {
	var msg wire.MsgBlock
	if err := wire.DecodeMsgBlock(&byteReader{b: payload}, &msg); err != nil {
		return err
	}
	b := chain.BlockFromMsgBlock(msg)
	n.mu.Lock()
	defer n.mu.Unlock()
	if n.Chain.Len() > int(b.Height) {
		return nil // already have it
	}
	if n.Chain.Len() < int(b.Height) {
		return fmt.Errorf("simnet: missing parent for height %d", b.Height)
	}
	if err := n.Chain.ImportBlock(b); err != nil {
		return err
	}
	if n.onBlock != nil {
		n.onBlock(b)
	}
	return nil
}

func (n *Node) sendChain(conn net.Conn) error {
	n.mu.Lock()
	blocks := n.Chain.Blocks()
	n.mu.Unlock()
	for _, b := range blocks {
		msg := b.ToMsgBlock()
		var buf byteWriter
		if err := wire.EncodeMsgBlock(&buf, &msg); err != nil {
			return err
		}
		if err := writeMsg(conn, msgBlock, buf.b); err != nil {
			return err
		}
	}
	return nil
}

func (n *Node) broadcastBlock(b *chain.Block) {
	msg := b.ToMsgBlock()
	var buf byteWriter
	if err := wire.EncodeMsgBlock(&buf, &msg); err != nil {
		return
	}
	payload := buf.b
	if n.listener == nil {
		return
	}
	// Re-dial peers for fire-and-forget broadcast (T0 simple).
	for _, addr := range n.peers {
		conn, err := net.DialTimeout("tcp", addr, 2*time.Second)
		if err != nil {
			continue
		}
		_ = writeMsg(conn, msgBlock, payload)
		_ = conn.Close()
	}
}

func writeMsg(w io.Writer, typ byte, payload []byte) error {
	if _, err := w.Write([]byte(magic)); err != nil {
		return err
	}
	if _, err := w.Write([]byte{typ}); err != nil {
		return err
	}
	var lenBuf [4]byte
	binary.LittleEndian.PutUint32(lenBuf[:], uint32(len(payload)))
	if _, err := w.Write(lenBuf[:]); err != nil {
		return err
	}
	_, err := w.Write(payload)
	return err
}

func readMsg(r io.Reader) (byte, []byte, error) {
	var mg [4]byte
	if _, err := io.ReadFull(r, mg[:]); err != nil {
		return 0, nil, err
	}
	if string(mg[:]) != magic {
		return 0, nil, fmt.Errorf("simnet: bad magic")
	}
	var typ [1]byte
	if _, err := io.ReadFull(r, typ[:]); err != nil {
		return 0, nil, err
	}
	var lenBuf [4]byte
	if _, err := io.ReadFull(r, lenBuf[:]); err != nil {
		return 0, nil, err
	}
	n := binary.LittleEndian.Uint32(lenBuf[:])
	if n > 2*1024*1024 {
		return 0, nil, fmt.Errorf("simnet: message too large")
	}
	payload := make([]byte, n)
	if _, err := io.ReadFull(r, payload); err != nil {
		return 0, nil, err
	}
	return typ[0], payload, nil
}

type byteWriter struct{ b []byte }

func (w *byteWriter) Write(p []byte) (int, error) {
	w.b = append(w.b, p...)
	return len(p), nil
}

type byteReader struct {
	b []byte
	i int
}

func (r *byteReader) Read(p []byte) (int, error) {
	if r.i >= len(r.b) {
		return 0, io.EOF
	}
	n := copy(p, r.b[r.i:])
	r.i += n
	return n, nil
}
