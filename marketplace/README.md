# marketplace/: Compute marketplace + escrow

The core differentiator: buyers order compute and lock stablecoin in escrow;
miners run the job, prove it, and settle atomically (stablecoin payout + full
block-reward share). Full spec: /docs/spec-marketplace.md.

## Status
Plan only. No code yet.

## Components (planned)
- Model registry (on-chain): model_id, weights_hash, precision, min_vram.
- Job lifecycle: CREATED → FUNDED → ASSIGNED → PROVEN → SETTLED / REFUNDED.
- Escrow (USDC/USDT; ABA optional) with dispute/timeout + reputation/stake.
- Indexer for the job pool + the public "% useful compute" dashboard.

> Note: Abakos does NOT issue its own stablecoin; it accepts existing ones
> (USDC/USDT). See /docs/04-marketplace-and-escrow.md.
