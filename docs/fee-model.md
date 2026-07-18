# Abakos Fee Model (source of truth)

Two independent mechanisms. Do not conflate them.

## 1. Gas / transaction fees = ZERO
- The L1 is intentionally zero-fee: `feemarket` params `no_base_fee=true`, `base_fee=0`,
  `min_gas_price=0`; validator `minimum-gas-prices = "0uaba"`.
- Users pay nothing to submit transactions (Cosmos or EVM). `eth_gasPrice = 0`.
- Spam control is not economic: bounded by consensus `block.max_gas = 100000000` and a
  capped mempool (`max_txs_bytes = 128MB`). Validators are compensated via the compute
  economy (Console rentals + idle-mining -> ABA buyback), not tx fees. ABA has 0 inflation.

## 2. Protocol revenue share (the "cut" on earnings)
The network keeps a share of compute/mining/service revenue; the rest goes to the
provider/service. Routing: stakers -> community/reward pool, treasury -> treasury account,
burn -> unspendable burn address (`abakos1qqqq...`, de-facto burn on the sandbox; a real
supply-reducing burn via module/precompile is a mainnet TODO).

| Revenue source        | Total protocol take | Split (staker / treasury / burn) | Provider/service keeps |
|-----------------------|---------------------|----------------------------------|------------------------|
| Idle-mining buyback   | 12%                 | 4% / 4% / 4%                      | 88% (host)             |
| Chat                  | 12%                 | 4% / 4% / 4%                      | 88%                    |
| API usage             | 12%                 | 4% / 4% / 4%                      | 88%                    |
| Console / Marketplace | 3%                  | 1% / 1% / 1%                      | 97%                    |

## 3. DEX + stablecoin
- **Stablecoin standard: USDT (BEP20).** Pool payouts (Kryptex) and the DEX pairing use
  USDT. Pool payout / treasury address (BEP20): `0x0BfFbd3F4cB218f0926218915adD810C6Be72dcB`.
  The sandbox test token mirrors this (symbol USDT, 6-dec, no value). Rationale: same cost
  and effort as USDC would be for us, deepest liquidity, and it is what we operate with.
- The ABA/USDT AMM (Uniswap-v2 fork) charges the standard **0.30% swap fee, which goes
  entirely to liquidity providers** (it stays in the pool reserves). No protocol split on
  DEX swaps. This is separate from the protocol revenue share above.

## Enforcement status
- **Idle mining (live):** enforced in `provider-agent/agent.py` (`SPLIT = host .88 /
  stakers .04 / treasury .04 / burn .04`). Shown on `abakos.ai/dashboard`.
- **Console / Chat / API:** not built yet -> this doc + site copy are the spec; the
  settlement logic must implement these splits when built.
