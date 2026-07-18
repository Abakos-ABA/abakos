// Package chain is a minimal in-process block chain for T0 local mining demos.

// It will be replaced by the btcd fork + P2P (see docs/spec-pouw-integration.md).

package chain



import (

	"fmt"

	"time"



	"github.com/rexmarlon/abakos/node/consensus"

	"github.com/rexmarlon/abakos/node/pouw"

	"github.com/rexmarlon/abakos/node/wire"

)



// Block is a mined Abakos block (header + PoUW proof).

type Block struct {

	Header pouw.Header

	Proof  []byte

	Height uint64

	id     [32]byte

}



// Hash returns the block identifier.

func (b *Block) Hash() [32]byte {

	if b.id != ([32]byte{}) {

		return b.id

	}

	return pouw.BlockHash(&b.Header, b.Proof)

}



// HashString returns the first 16 hex chars of the block hash.

func (b *Block) HashString() string {

	h := b.Hash()

	return fmt.Sprintf("%x", h[:8])

}



// UsefulRatio returns useful_ratio in [0,1].

func (b *Block) UsefulRatio() float64 {

	return float64(b.Header.UsefulRatioBps) / 10000.0

}



// ToMsgBlock encodes the block for simnet P2P.

func (b *Block) ToMsgBlock() wire.MsgBlock {

	return wire.MsgBlock{

		Header:      consensus.HeaderFromPouw(b.Header),

		Certificate: append([]byte(nil), b.Proof...),

		Height:      b.Height,

	}

}



// BlockFromMsgBlock decodes a wire block.

func BlockFromMsgBlock(msg wire.MsgBlock) *Block {

	return &Block{

		Header: consensus.HeaderToPouw(msg.Header),

		Proof:  append([]byte(nil), msg.Certificate...),

		Height: msg.Height,

	}

}



// headerAfter returns a child header template chained to parent.

func headerAfter(parent *Block, bits uint32, usefulBps uint16, ts time.Time) pouw.Header {

	h := pouw.Header{

		Version:        AbakosBlockVersion,

		PrevBlock:      parent.Hash(),

		Timestamp:      ts,

		Bits:           bits,

		UsefulRatioBps: usefulBps,

	}

	return h

}


