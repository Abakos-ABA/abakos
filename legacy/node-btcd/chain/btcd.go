package chain

import (
	"fmt"

	"github.com/btcsuite/btcd/blockchain"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/txscript"
	btcwire "github.com/btcsuite/btcd/wire"
	"github.com/rexmarlon/abakos/node/chaincfg"
	"github.com/rexmarlon/abakos/node/consensus"
	"github.com/rexmarlon/abakos/node/economics"
	"github.com/rexmarlon/abakos/node/pouw"
)

// AbakosBlockVersion is the btcd wire version flag for PoUW blocks.
const AbakosBlockVersion = btcwire.BlockVersionAbakos | 1

// CoinbaseSubsidySat is deprecated; use CalcBlockSubsidy per height.
const CoinbaseSubsidySat = int64(50e8)

// AdjustedCoinbaseSubsidy returns the consensus coinbase after reward-split.
func AdjustedCoinbaseSubsidy(baseSubsidy int64, usefulBps uint16) int64 {
	return economics.CoinbaseSubsidy(baseSubsidy, usefulBps)
}

// NewCoinbaseTx builds a minimal coinbase for height with the given subsidy (satoshis).
func NewCoinbaseTx(height int32, subsidy int64, tag string) *btcwire.MsgTx {
	script := mustCoinbaseScript(height, tag)
	return &btcwire.MsgTx{
		Version: 1,
		TxIn: []*btcwire.TxIn{{
			PreviousOutPoint: btcwire.OutPoint{Index: 0xffffffff},
			SignatureScript:  script,
			Sequence:         0xffffffff,
		}},
		TxOut: []*btcwire.TxOut{{
			Value:    subsidy,
			PkScript: []byte{0x51}, // OP_1
		}},
		LockTime: 0,
	}
}

func mustCoinbaseScript(height int32, tag string) []byte {
	script, err := txscript.NewScriptBuilder().
		AddInt64(int64(height)).
		AddData([]byte(tag)).
		Script()
	if err != nil {
		panic(err)
	}
	return script
}

// CoinbaseMerkleRoot returns the merkle root of a single coinbase tx at height.
func CoinbaseMerkleRoot(height int32, subsidy int64) [32]byte {
	coinbase := NewCoinbaseTx(height, subsidy, chaincfg.GenesisCoinbaseTag)
	merkle := blockchain.CalcMerkleRoot([]*btcutil.Tx{btcutil.NewTx(coinbase)}, false)
	var out [32]byte
	copy(out[:], merkle[:])
	return out
}

// BuildBtcdMsgBlock assembles a btcd wire block from a mined Abakos header+proof.
// header.MerkleRoot must be set before mining (see CoinbaseMerkleRoot).
func BuildBtcdMsgBlock(prevHash chainhash.Hash, header pouw.Header, proof []byte, height int32, subsidy int64) (*btcwire.MsgBlock, error) {
	coinbase := NewCoinbaseTx(height, subsidy, chaincfg.GenesisCoinbaseTag)
	txs := []*btcwire.MsgTx{coinbase}
	utilTxs := make([]*btcutil.Tx, len(txs))
	for i, tx := range txs {
		utilTxs[i] = btcutil.NewTx(tx)
	}
	merkle := blockchain.CalcMerkleRoot(utilTxs, false)
	var expect [32]byte
	copy(expect[:], merkle[:])
	if header.MerkleRoot != expect {
		return nil, fmt.Errorf("chain: header merkle root does not match coinbase")
	}

	var commit chainhash.Hash
	copy(commit[:], header.ProofCommitment[:])

	msg := &btcwire.MsgBlock{
		Header: btcwire.BlockHeader{
			Version:         header.Version,
			PrevBlock:       prevHash,
			MerkleRoot:      merkle,
			Timestamp:       header.Timestamp,
			Bits:            header.Bits,
			ProofCommitment: commit,
			UsefulRatioBps:  header.UsefulRatioBps,
		},
		Certificate:  append([]byte(nil), proof...),
		Transactions: txs,
	}
	return msg, nil
}

// BlockFromBtcutil converts a btcd block to the in-memory Abakos block view.
func BlockFromBtcutil(block *btcutil.Block) *Block {
	msg := block.MsgBlock()
	h := msg.Header
	var prev, merkle, commit [32]byte
	copy(prev[:], h.PrevBlock[:])
	copy(merkle[:], h.MerkleRoot[:])
	copy(commit[:], h.ProofCommitment[:])
	ph := pouw.Header{
		Version:         h.Version,
		PrevBlock:       prev,
		MerkleRoot:      merkle,
		Timestamp:       h.Timestamp,
		Bits:            h.Bits,
		ProofCommitment: commit,
		UsefulRatioBps:  h.UsefulRatioBps,
	}
	b := &Block{
		Header: ph,
		Proof:  append([]byte(nil), msg.Certificate...),
		Height: uint64(block.Height()),
	}
	if hash := block.Hash(); hash != nil {
		copy(b.id[:], hash[:])
	}
	return b
}

// ToBtcutilBlock wraps a mined Abakos block as btcutil.Block at height.
func (b *Block) ToBtcutilBlock(prevHash chainhash.Hash, height int32, subsidy int64) (*btcutil.Block, error) {
	msg, err := BuildBtcdMsgBlock(prevHash, b.Header, b.Proof, height, subsidy)
	if err != nil {
		return nil, err
	}
	block := btcutil.NewBlock(msg)
	block.SetHeight(height)
	return block, nil
}

// HeaderToBtcd converts pouw header to btcd wire header (no prev hash).
func HeaderToBtcd(h pouw.Header) btcwire.BlockHeader {
	wh := consensus.HeaderFromPouw(h)
	var hdr btcwire.BlockHeader
	hdr.Version = wh.Version
	copy(hdr.PrevBlock[:], wh.PrevBlock[:])
	copy(hdr.MerkleRoot[:], wh.MerkleRoot[:])
	hdr.Timestamp = wh.Timestamp
	hdr.Bits = wh.Bits
	copy(hdr.ProofCommitment[:], wh.ProofCommitment[:])
	hdr.UsefulRatioBps = wh.UsefulRatioBps
	return hdr
}
