# 12 · Funding & Treasury

Goal: ensure **enough money (fiat) and tokens** for development, audit, legal **and listing**, without damaging credibility ("honesty as brand"). Figures are starting assumptions.

## 1. The central tension: fair launch vs. funding

Pearl is a pure Bitcoin fork **without premine** (everything via mining). That is credible but does not fund development. Abakos needs budget → solution: **moderate, transparent, vested allocation** (30% non-mining) + a **small private token sale** + **fiat pre-seed**. Transparency (vesting on-chain) preserves credibility.

## 2. Token allocation (coverage in tokens, 2.1B ABA)

| Bucket | Share | Tokens | Purpose |
|---|---|---|---|
| Mining emission | 70% | 1.470B | fair PoUW distribution over years |
| Treasury / development | 10% | 210M | dev financing (via OTC/vesting) |
| Team / advisors | 8% | 168M | 1 yr cliff, 4 yr vesting |
| **Liquidity & listing** | 7% | 147M | DEX pools + CEX market-making |
| Ecosystem / grants / chat credits | 5% | 105M | demand incentives, researcher grants |

> Once ABA has value, these buckets are **ample** for dev + listing. The real bottleneck is the **early fiat phase** (before token value) → pre-seed for that (§4).

## 3. Budget until mainnet + token (~12 months, illustrative)

| Item | Estimate (12 mo.) |
|---|---|
| Team (3–4 people, remote/crypto-native) | $420k–660k |
| Infra (seed nodes, indexer, chat gateway, hybrid partner GPUs) | $40k–100k |
| Protocol audit (before mainnet) | $40k–80k |
| Legal (token structure, ToS/privacy, **trademark search abacus.ai**) | $30k–60k |
| Listing fees (1–2 tier-2 CEX) + MM setup | $10k–80k |
| Marketing / grants (remainder from ecosystem bucket) | $20k–50k |
| **Total fiat need** | **~$0.8M–1.5M** |

## 4. Funding sources (order)

1. **Pre-seed / angel (fiat), $1–2M**: main source for runway *before* the token has value. Covers team, audit, legal, early infra.
2. **Strategic neocloud partner**: capital **and** GPU supply (also solves supply side, Doc 06).
3. **Private token sale (SAFT/private round)**: small, vested, legally clean; only part from treasury/liquidity. Only after legal opinion (Doc 10).
4. **Treasury OTC later**: after token value, vested, **no market dumping**, for ongoing development.
5. **Stablecoin revenue** (marketplace fee + chat margin): from phase 3 the **price-independent** second pillar → reduces dependence on token sales.

## 4a. Instrument (decision): SAFT, token-only, no equity

**Decision:** raise on a **SAFT** (Simple Agreement for Future Tokens), not a SAFE + token warrant. Investors get a contractual right to ABA at the Token Generation Event; they do **not** get IOTAplus AG shares, ever, from this instrument. This was chosen deliberately over the equity-bundled structure because the founder wants to keep IOTAplus AG's cap table exactly as it is (sole owner) rather than add shareholders, and a pure token instrument does that cleanly: there is no conversion event to plan for, batch, or manage, because there are no shares involved at all.

**The honest trade-off (say this to investors who ask, don't bury it):** a SAFE + token warrant gives an investor two independent shots at return, company equity and token upside, which some crypto VCs specifically prefer as a hedge if the token launch is delayed or runs into regulatory friction. A pure SAFT is 100% token exposure: no equity cushion if the token is delayed, no participation in any value IOTAplus AG builds outside the token. That's a real, legitimate choice, not a shortcut, but it can make the round slightly less appealing to investors who specifically want the equity hedge. Expect some investors to ask for the equity-bundled version anyway; deciding whether to offer both instruments side by side (SAFT for those who want simplicity, SAFE + warrant for those who want the hedge) is a real option, not required.

**What does not change just because equity is off the table:** this is still a private, signed agreement to accredited/qualified investors, not a public sale. Removing the equity component doesn't remove the securities analysis (Doc 10), a SAFT is still very likely a security under Howey (money in, common enterprise, profit expectation, from the founder's efforts) and still needs the same private-placement discipline: signed contract, accreditation check, no public self-serve payment page. "Simpler cap table" and "less legal rigor" are not the same thing; only the first is true here.

## 4b. Pricing by phase (SAFT tiers, illustrative)

Reward early commitments with a better implied price, without running a public token sale. The mechanism is a **valuation cap on the SAFT**: the cap determines how much ABA the investment converts into at the Token Generation Event, a lower cap now means more ABA per dollar later. The cap an investor gets is locked in at signing, tied to whichever tier is active on that date; it does not improve retroactively if a later tier is lower, and does not get worse if a later tier is higher.

| Tier | Proof point required | Illustrative FDV cap | Implied ABA price (cap ÷ 2.1B) |
|---|---|---|---|
| Phase 0 (now) | None beyond what's live today (local simnet, reward-split enforced) | $18M | ~$0.0086 |
| Phase 1 | Public testnet live, externally verifiable | $35M | ~$0.0167 |
| Phase 2 | Marketplace live, first real (non-team) revenue | $65M | ~$0.031 |
| Launch | Mainnet, audited | Market (TGE price discovery); ~$100M+ as a reference ceiling | ~$0.048+ |

All figures are draft and will be calibrated with legal advice before being put in a signed SAFT; do not quote these externally as final. The point of the table is the *shape* (earlier, more verifiable proof point → lower cap → more ABA per dollar), not the exact numbers yet.

**On-chain vesting administration (planned, post-TGE only):** once ABA exists, SAFT vesting for already-qualified investors (accredited, SAFT signed) can be administered by a smart contract (e.g. a standard vesting-schedule contract releasing ABA on a cliff + linear schedule), which is a genuinely good idea for transparency and removes any manual trust requirement on the unlock schedule. This is different from, and does not require, selling a wrapped pre-launch token to the public; see Doc 10 for why that specific idea (wABA on BSC, public USDT sale, instant delivery, bridge later) was considered and rejected. §4c.1 below covers taking the *payment* leg on-chain too, not just the eventual vesting.

## 4c.1 Payment mechanism: on-chain option (recommended over manual wires)

**How Pearl solved this, for context: it didn't.** Pearl ran a pure fair launch, no premine, no VC, no founder allocation; every PRL was mined, including the team's, from genesis. That's the opposite end of the spectrum from raising money now, and it's exactly why §1 already rejected copying that model (it doesn't fund development). Not a usable template for this question.

**What is a real, usable pattern from elsewhere in crypto:** a private, whitelist-gated presale-and-vesting smart contract. This is standard infrastructure, not something to build from scratch:

- **Access is still gated.** Only wallet addresses added to a whitelist can call the contract's `buy()` function, and addresses are only added *after* the same accreditation/KYC check and signed SAFT this doc already requires. This is what keeps it a private placement instead of a public sale (Doc 10); the smart contract changes *how* payment and vesting are administered, not *who* can participate or whether marketing/gating rules apply.
- **Investor pays in USDT/USDC directly**, on-chain, immediately. No bank wire, no multi-day settlement.
- **The contract records the commitment and locks a vesting schedule** (cliff + linear, matching the SAFT's terms) for the eventual ABA allocation, typically represented as a claim the investor can see and later redeem, sometimes as an NFT "claim ticket" (the pattern used by **Hedgey Finance**, an existing, already-audited OTC/vesting protocol). This gives the investor a visible, on-chain, independently verifiable record of what they're owed, a real security improvement over "trust the cap table spreadsheet."
- **Use an existing, audited platform (Hedgey Finance or equivalent) rather than a custom contract.** Commissioning a bespoke contract plus a real third-party audit is a real cost (audits commonly run five figures) that isn't proportionate to a $300k-500k first close; an established, already-audited protocol removes most of that cost and risk.
- **Chain choice:** Abakos' own L1 is not a smart-contract chain (a btcd-style PoUW fork, no EVM), so this has to run on an existing EVM chain, independent of Abakos itself. A low-fee chain with real USDT/USDC liquidity (Base, Arbitrum, or BSC) is the practical choice; pick based on where your actual investors already hold stablecoins.
- **The company stays the legal counterparty either way.** The contract should be deployed and controlled by a company-held address (or a multisig the company controls), not a personal wallet with no legal entity behind it; the SAFT remains the governing legal document, the contract just automates the mechanics it describes. Removing the company from the picture entirely doesn't reduce risk, it removes the only accountable party and any liability shield for the founder.

**Net effect:** same SAFT, same accredited-investor gating, same private-not-public rule as before, but the investor experience becomes "connect wallet, pay USDT, get an on-chain, verifiable claim" instead of "wire fiat, wait for a spreadsheet update." Worth building once check volume justifies the integration work; a manual wire is fine for the first few checks while this gets set up.

## 4c. Legal entity and instrument mechanics (operational)

**Issuing party:** IOTAplus AG (Swiss Aktiengesellschaft, already registered, sole-owner) is the counterparty that signs the SAFT and receives the fiat, unless a separate structure is decided later with counsel. This is an internal fact; the public site deliberately does not name the entity (disclosed to investors directly in the signed SAFT, not on the marketing pages).

**A SAFT is not a Swiss-vs-Delaware problem the way a SAFE was.** Because no shares are ever issued, there's no Swiss capital-increase mechanic to accommodate, that whole mismatch (Doc 10) goes away with this instrument choice. The SAFT still needs a real lawyer to draft or adapt a template (crypto-specialized; Swiss firms with token experience, or a crypto-native firm with a template, either can work since the agreement's governing law is a choice, not dictated by IOTAplus AG's incorporation), and to confirm accredited-investor requirements for whichever jurisdictions your actual investors are in. **Do not send any template to a real investor before a lawyer has reviewed it for this specific setup.**

**Process, concretely, once the instrument is ready:**
1. Investor and IOTAplus AG sign the SAFT (e-signature is fine).
2. Investor pays: either a fiat/stablecoin wire to IOTAplus AG's corporate account (simplest, works from day one), or, once set up, directly in USDT/USDC through a whitelisted on-chain presale contract (see §4c.1) for an immediate, on-chain record of their claim. Both are the same legal deal underneath; the second is a smoother experience once it exists.
3. Record the commitment on a token cap table (tracking who is owed how much ABA, at what cap; Ledgy and similar cap-table tools increasingly support token-based instruments alongside equity ones, confirm current feature support before relying on it), or let the on-chain contract be the record of truth if using §4c.1.
4. IOTAplus AG's own shareholding is untouched by any of this; no new shares are ever issued from a SAFT.
5. ABA vests and is delivered to the investor's wallet at and after the Token Generation Event (mainnet), per the vesting schedule in the SAFT. This step is when the wallet address is actually needed, collect it during signing so there's no delay later.

**Profit-sharing:** none, and that's the direct consequence of choosing tokens-only. A SAFT holder is not a shareholder and has no claim on IOTAplus AG's profits, dividends, or exit proceeds, only on the ABA the SAFT entitles them to. Their return case is entirely the token's value and utility, not the company's.

## 4d. Keeping many small checks manageable

With a pure SAFT there is no shareholder-count problem to manage (no shares are ever issued), so the concerns that used to apply to a share-based instrument mostly don't apply here. What's still worth doing regardless of instrument:

- **Track commitments centrally from the start** (a simple spreadsheet is fine at pre-seed scale; move to a proper token cap-table tool once past a handful of investors) so nobody's terms or vesting get ambiguous later.
- **Pooling many small checks through an SPV** (Sydecar, AngelList, Vauban/Odin) is still an option if managing many individual SAFT contracts directly becomes a lot of paperwork, but it's an administrative convenience now, not a legal necessity the way it would be for a share-based round.
- $5k minimum checks are fine; there's no structural reason to raise it now that shares aren't the constraint.

**Considered and rejected: incorporating a new entity just to use an unmodified foreign template, or skipping the contract entirely and taking USDT with no agreement at all.** A SAFT already solves the cap-table concern that motivated looking at a new entity; there's no remaining reason to set one up for this round. Skipping the contract doesn't remove securities exposure (Doc 10), it only removes the documentation that would have protected both sides, and leaves the founder personally exposed with no liability shield at all. Revisit a separate legal entity for the token/treasury side (e.g. a Cayman foundation) only if a specific major investor requires it, or when that structure needs to formalize closer to mainnet, not for this round.

## 5. Listing plan

- **Phase 3 (mainnet):**
  - **DEX first:** own liquidity pools from liquidity bucket (147M ABA) + stable. Immediately tradable, no gatekeepers.
  - **1–2 tier-2 CEX:** moderate fees, early reach.
  - **Market-making contract:** funded from liquidity bucket + some stable.
- **Later:** tier-1 CEX when volume, compliance, and liquidity are there.
- Listing budget comes **primarily from tokens** (liquidity bucket), not scarce fiat.

## 6. Guardrails (protect credibility)

- **Vesting transparent on-chain** (team 1 yr cliff/4 yr; treasury 4 yr).
- **No sale before utility** (testnet/product first, then token, Doc 11).
- **Burn** of empty-mining penalty share + 1% fee burn (direct if the fee was paid in ABA, buyback-and-burn if it was paid in stablecoin) → deflation story with real volume, currency-agnostic.
- **Two separate money flows** (subsidy in token vs. revenue normally in stable, occasionally in ABA when a buyer opts for the discount), separated technically & legally (Doc 03/10, Doc 04).

## 7. How do I actually get the money?

Step-by-step guide (accelerator, VCs, angels, strategic partners, grants, bootstrapping via revenue): see **[`docs/13-fundraising-playbook.md`](13-fundraising-playbook.md)**.

## 8. To-dos

- [ ] create pre-seed pitch (one-pager + deck)
- [ ] approach 1–2 strategic neocloud partners as investor+supply
- [ ] clarify legal structure for token sale (jurisdiction, SAFT) (Doc 10)
- [ ] calculate liquidity/MM plan with concrete pool sizes (Doc 08)
- [ ] runway model (burn rate vs. funding) as script (workstream D)
