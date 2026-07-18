# 08 · Financial Model (illustrative)

> All figures are placeholders for calibration, **not** calibrated mainnet values.

## Revenue sources

1. **Marketplace fee** (2% on compute trades): scales with real volume. Split by settlement currency (Doc 04): the stablecoin share is real, spendable revenue; the ABA share is burned directly and is not spendable cash, only a deflation contribution. The model below treats all fee volume as USD-equivalent for the burn figures, but does not yet separate the two currencies for runway purposes; treat the stablecoin share as the conservative number for cash planning.
2. **Abakos Chat margin** (chat price > network cost).
3. **Managed API margin** (phase 4).
4. **Token launch/liquidity**: bootstrap financing, **not** sustainable revenue (track separately).

## Example calculation: marketplace fee

| Scenario | Active GPUs | Avg sale/h | Utilization | Volume/month | Fee revenue/month (2%) |
|---|---|---|---|---|---|
| Start | 500 | $1.50 | 50% | ~$270k | ~$5.4k |
| Growth | 2,000 | $1.50 | 55% | ~$1.19M | ~$23.8k |
| Scale | 10,000 | $1.50 | 60% | ~$6.48M | ~$130k |

(Formula: GPUs × $/h × 24 × 30 × utilization × 2%.)

## Example calculation: Abakos Chat

- Assumption: 50,000 active users, avg $3/month paying (ARPU), 20% paying
  → 10,000 × $3 = **$30k/month** gross, minus network inference cost.
- Scales strongly with user growth; largest long-term revenue driver.

## Mining economics (derived from arXiv)

- Consumer GPUs: ROI positive (e.g. +67% on RTX 3060 Ti at PRL price $0.76).
- Datacenter GPUs: unprofitable without customer payment → **therefore** escrow coupling is decisive (customer pays on top).

## Cost side (rough, monthly)

| Item | Assumption |
|---|---|
| Team (3–4) | main cost block |
| Infra (seed nodes, indexer, chat gateway, partner GPUs) | medium |
| Liquidity / listing | one-time + ongoing |
| Legal / audit | one-time (before mainnet) |
| Marketing / grants | from ecosystem pool |

## Financing

- Pre-seed / angel.
- Treasury allocation (10%) as development budget.
- Strategic neocloud partner.
- Token sale (legally structured, see Doc 10).

## Break-even logic

Protocol becomes self-sustaining when `fee revenue + chat margin > operating costs`. In the scenarios above, realistic from "growth/scale," primarily through Abakos Chat scaling.

## Calculation model (workstream D)

A parameterized script reproduces these numbers: **[`model/model.py`](../model/model.py)** (`python model.py` → report + `model_output.csv`).

**Key results (default assumptions, illustrative):**
- **Emission year 1:** ~183.8M ABA (~20,976 ABA/h), halving every 4 years → cumulative converges toward 1.47B (mining bucket).
- **Revenue/month:** start ~$6.4k · growth ~$35.9k · scale ~$224k.
- **Runway:** pre-seed $1.5M, opex $50k/mo, one-time costs $145k → **break-even month 14**, survives >24 months (cash low ~$872k around month 13).
- **Annual fee burn:** start ~$32k · growth ~$143k · scale ~$778k (USD equiv.).
- **Bucket value (treasury+liquidity, 17%):** at ABA $0.20 ≈ $71M · $0.76 ≈ $271M.

Calibrate assumptions in the `CONFIG` block before putting numbers in the pre-seed deck.
