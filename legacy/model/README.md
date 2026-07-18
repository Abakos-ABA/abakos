# Financial & Runway Model (workstream D)

Parameterized, dependency-free Python script for pre-seed numbers.

## Run
```
python model.py
```
Prints a console report and writes `model_output.csv` (for deck/spreadsheet).

## What it calculates
1. **Token allocation** (from `max_supply` + `alloc`).
2. **Emission/supply:** Bitcoin-style halving, auto-fitted so cumulative emission converges toward mining allocation (70%).
3. **Revenue scenarios:** marketplace fee (2%) + Abakos Chat margin, per month/year.
4. **Burn estimate:** annual, from fee-burn share.
5. **Runway simulation:** month by month: revenue ramp vs. opex + one-time costs → **break-even month** and runway.
6. **Token value sensitivity:** value of treasury/liquidity buckets at various ABA prices.

## Key results (default assumptions, illustrative)
- **Emission year 1:** ~183.8M ABA (~20,976 ABA/h), halving every 4 years.
- **Revenue/month:** start ~$6.4k · growth ~$35.9k · scale ~$224k.
- **Runway:** pre-seed $1.5M, opex $50k/mo → **break-even month 14**, survives >24 months (cash low ~$872k around month 13).
- **Bucket value** (treasury+liquidity, 17% = 357M ABA): at $0.20 ≈ $71M, at $0.76 ≈ $271M.

## Calibrate
All assumptions are in the `CONFIG` block at the top of `model.py`. Adjust and re-run. Deliberately conservative/illustrative; replace with real numbers (GPU prices, chat ARPU, actual opex) before putting in the deck.
