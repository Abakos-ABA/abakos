#!/usr/bin/env python3
"""Apply Phase A blockNode UsefulRatioBps persistence to .btcd-fork."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / ".btcd-fork" / "blockchain" / "blockindex.go"

def main() -> None:
    if not INDEX.exists():
        raise SystemExit(f"missing {INDEX}")
    text = INDEX.read_text(encoding="utf-8")
    if "usefulRatioBps" in text:
        print("blockNode usefulRatioBps already present")
        return

    old_fields = """\tmerkleRoot chainhash.Hash

\t// status is a bitfield representing the validation state of the block. The
"""
    new_fields = """\tmerkleRoot chainhash.Hash

\t// Abakos PoUW header fields (zero for Bitcoin blocks).
\tproofCommitment chainhash.Hash
\tusefulRatioBps  uint16

\t// status is a bitfield representing the validation state of the block. The
"""
    if old_fields not in text:
        raise SystemExit("blockNode fields marker not found")
    text = text.replace(old_fields, new_fields, 1)

    old_init = """\t*node = blockNode{
\t\thash:       blockHeader.BlockHash(),
\t\tworkSum:    CalcWork(blockHeader.Bits),
\t\tversion:    blockHeader.Version,
\t\tbits:       blockHeader.Bits,
\t\tnonce:      blockHeader.Nonce,
\t\ttimestamp:  blockHeader.Timestamp.Unix(),
\t\tmerkleRoot: blockHeader.MerkleRoot,
\t}
"""
    new_init = """\t*node = blockNode{
\t\thash:            blockHeader.BlockHash(),
\t\tworkSum:         CalcWork(blockHeader.Bits),
\t\tversion:         blockHeader.Version,
\t\tbits:            blockHeader.Bits,
\t\tnonce:           blockHeader.Nonce,
\t\ttimestamp:       blockHeader.Timestamp.Unix(),
\t\tmerkleRoot:      blockHeader.MerkleRoot,
\t\tproofCommitment: blockHeader.ProofCommitment,
\t\tusefulRatioBps:  blockHeader.UsefulRatioBps,
\t}
"""
    if old_init not in text:
        raise SystemExit("initBlockNode body not found")
    text = text.replace(old_init, new_init, 1)

    old_eq = """\t\tnode.merkleRoot == other.merkleRoot &&
\t\tnode.status == other.status
"""
    new_eq = """\t\tnode.merkleRoot == other.merkleRoot &&
\t\tnode.proofCommitment == other.proofCommitment &&
\t\tnode.usefulRatioBps == other.usefulRatioBps &&
\t\tnode.status == other.status
"""
    if old_eq not in text:
        raise SystemExit("Equals body not found")
    text = text.replace(old_eq, new_eq, 1)

    old_hdr = """\treturn wire.BlockHeader{
\t\tVersion:    node.version,
\t\tPrevBlock:  *prevHash,
\t\tMerkleRoot: node.merkleRoot,
\t\tTimestamp:  time.Unix(node.timestamp, 0),
\t\tBits:       node.bits,
\t\tNonce:      node.nonce,
\t}
"""
    new_hdr = """\treturn wire.BlockHeader{
\t\tVersion:         node.version,
\t\tPrevBlock:       *prevHash,
\t\tMerkleRoot:      node.merkleRoot,
\t\tTimestamp:       time.Unix(node.timestamp, 0),
\t\tBits:            node.bits,
\t\tNonce:           node.nonce,
\t\tProofCommitment: node.proofCommitment,
\t\tUsefulRatioBps:  node.usefulRatioBps,
\t}
"""
    if old_hdr not in text:
        raise SystemExit("Header() body not found")
    text = text.replace(old_hdr, new_hdr, 1)

    INDEX.write_text(text, encoding="utf-8")
    print(f"patched {INDEX}")

if __name__ == "__main__":
    main()
