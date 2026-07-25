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
- **Stablecoin standard: USDC (Circle-issued on Noble, over IBC) — since 2026-07-25.**
  There is exactly ONE canonical USDC on Abakos: the Noble IBC voucher
  (`ibc/8E27BA2D...45B5`), exposed 1:1 in the EVM as the ERC20 precompile
  `0x4E46004562C46AB7EC0cC4C1ca14E9e20E2545B5`. Inflows from Polygon/Ethereum/etc. route
  Skip API -> CCTP -> Noble -> IBC and land as this same token (in-app bridge on
  `abakos.ai/dex`); mining payouts (unMineable) convert to it before the buyback.
  (Historical drafts standardized on USDT/BEP20 via Kryptex; fully replaced.)
- The ABA/USDC AMM (Uniswap-v2 fork; LP token "Abakos LP" / ABA-LP) charges the standard
  **0.30% swap fee: 0.25% to liquidity providers, 0.05% protocol** (the built-in factory
  `feeTo` switch = 1/6 of fees), and the protocol slice is split
  **1/3 stakers / 1/3 treasury / 1/3 burn**.

## Enforcement status
- **Idle mining (live):** enforced in `provider-agent/agent.py` (`SPLIT = host .88 /
  stakers .04 / treasury .04 / burn .04`); one distribution round per inflow. Shown on
  `abakos.ai/dashboard`.
- **DEX protocol fee (live since 2026-07-25):** factory `feeTo` -> agent wallet;
  `provider-agent/agent.py dex_fee_tick()` redeems the accrued fee-LP every epoch and
  splits 1/3 / 1/3 / 1/3 via the same payout rails.
- **Console / Marketplace (live since 2026-07-24):** enforced on-chain in the escrow
  keeper (`chain/x/escrow/keeper/fees.go`, `settlementPayout`): every lease payout is
  split 97% provider / 1% fee_collector (distributed to stakers next block) / 1%
  treasury / 1% burn address. Deposit refunds (bid collateral, unused tenant deposit)
  are exempt. Sandbox: destination addresses are code constants; mainnet TODO: gov
  params + real supply-reducing burn.
- **Chat / API:** not built yet -> this doc + site copy are the spec; the
  settlement logic must implement these splits when built.
