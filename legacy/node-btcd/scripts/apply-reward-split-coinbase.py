#!/usr/bin/env python3
"""Apply Phase A reward-split coinbase check to a freshly patched .btcd-fork."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = ROOT / ".btcd-fork" / "blockchain" / "validate.go"

OLD = """\texpectedSatoshiOut := CalcBlockSubsidy(node.height, b.chainParams) +
\t\ttotalFees
\tif totalSatoshiOut > expectedSatoshiOut {
\t\tstr := fmt.Sprintf("coinbase transaction for block pays %v "+
\t\t\t"which is more than expected value of %v",
\t\t\ttotalSatoshiOut, expectedSatoshiOut)
\t\treturn ruleError(ErrBadCoinbaseValue, str)
\t}
"""

NEW = """\tbaseSubsidy := CalcBlockSubsidy(node.height, b.chainParams)
\texpectedSubsidy := baseSubsidy
\tif wire.IsAbakosVersion(node.Header().Version) {
\t\t// Abakos reward split: empty mining pays floor (25%); full useful pays 100%.
\t\t// See github.com/rexmarlon/abakos/node/economics.CoinbaseSubsidy.
\t\tconst rewardFloorBps int64 = 2500
\t\tusefulBps := int64(node.Header().UsefulRatioBps)
\t\tif usefulBps > 10000 {
\t\t\tusefulBps = 10000
\t\t}
\t\tnum := rewardFloorBps*10000 + (10000-rewardFloorBps)*usefulBps
\t\texpectedSubsidy = baseSubsidy * num / 100_000_000
\t}
\texpectedSatoshiOut := expectedSubsidy + totalFees
\tif wire.IsAbakosVersion(node.Header().Version) {
\t\t// Exact match: underpaying would let miners claim useful_ratio without paying burn.
\t\tif totalSatoshiOut != expectedSatoshiOut {
\t\t\tstr := fmt.Sprintf("coinbase transaction for Abakos block pays %v "+
\t\t\t\t"which is not the expected reward-split value of %v (useful_bps=%d)",
\t\t\t\ttotalSatoshiOut, expectedSatoshiOut, node.Header().UsefulRatioBps)
\t\t\treturn ruleError(ErrBadCoinbaseValue, str)
\t\t}
\t} else if totalSatoshiOut > expectedSatoshiOut {
\t\tstr := fmt.Sprintf("coinbase transaction for block pays %v "+
\t\t\t"which is more than expected value of %v",
\t\t\ttotalSatoshiOut, expectedSatoshiOut)
\t\treturn ruleError(ErrBadCoinbaseValue, str)
\t}
"""

def main() -> None:
    if not VALIDATE.exists():
        raise SystemExit(f"missing {VALIDATE}, run init-btcd-fork.sh first")
    text = VALIDATE.read_text(encoding="utf-8")
    if "rewardFloorBps" in text:
        print("reward-split coinbase already applied")
        return
    if OLD not in text:
        raise SystemExit("expected coinbase check block not found in validate.go")
    VALIDATE.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"patched {VALIDATE}")

if __name__ == "__main__":
    main()
