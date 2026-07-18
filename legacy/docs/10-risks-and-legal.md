# 10 · Risks & Legal

## Technical / economic risks

| Risk | Severity | Mitigation |
|---|---|---|
| Verifiability gap (random matrices disguised) | high | solve **economically**: full rewards only for paid escrow jobs (not purely statistical; arXiv shows statistical checks are bypassable) |
| Chicken-and-egg (supply vs. demand) | high | supply first, bootstrap demand from ecosystem pool, Abakos Chat as demand magnet |
| Token price decline → subsidy shrinks | high | stablecoin revenue (fee + chat) as price-independent pillar |
| Latency of decentralized inference (chat) | medium | hybrid initially (partner GPUs for real-time) |
| ASIC/bare-mining convergence (as with Pearl) | medium | reward split makes empty mining unattractive |
| Model quality (open vs. GPT/Claude) | medium | expectation "cheap & good enough," curate best open models |

## Legal risks

| Topic | Note |
|---|---|
| Token = security? (MiCA/EU, SEC/US) | legal opinion before launch. Establish utility clearly before sale. |
| Token sale structure | structure cleanly (choose jurisdiction), transparent vesting. |
| Instrument choice: SAFE (equity) vs. SAFT (token-only) | **Decided: SAFT (Doc 12 §4a).** Raising on equity (a SAFE, or its Swiss equivalent, a convertible loan / "Wandeldarlehen", since a US SAFE doesn't map onto Swiss capital-increase rules) would have added shareholders to IOTAplus AG. A SAFT avoids that entirely, no shares are ever issued, at the cost of investors getting token-only exposure with no equity hedge. Still needs a lawyer to draft/adapt the SAFT itself and confirm accredited-investor requirements; "no equity" does not mean "no legal document." |
| "Wrap it and sell it now, bridge to native token later" (e.g. wABA on BSC, public USDT purchase, instant delivery) | **Considered and rejected (decision).** Wrapping the token and deferring the bridge to native ABA does not change the legal analysis: regulators apply an "economic reality" test (Howey: money in, common enterprise, expectation of profit, from the founder's efforts), not a label test, and a public, permissionless, no-KYC, instant-delivery sale is the clearest possible fact pattern for that test, arguably worse than a plain 2017-style ICO since there is no gate at all. This would very likely constitute an unregistered securities offering, expose the founder personally, and poison future institutional rounds and exchange listings. The SAFT structure (Doc 12 §4a) exists specifically to get the benefits people want from this idea (early commitment gets a better price, vesting is programmable) without the public-sale exposure; it is still a private, signed, gated instrument, not a public one. Do not revisit this without new legal advice specific to the exact mechanism proposed. |
| Stablecoin compute sale vs. token speculation | **strictly separate**: separate flows & possibly separate entities. |
| Abakos Chat: content liability / moderation | terms of use, filters against illegal content, optional age/KYC tiers. |
| Privacy (chat data, EU GDPR) | data minimization, clear policy, EU hosting option. |
| Data in inference jobs (confidentiality) | encryption / confidential compute (protect buyer inputs). |
| Tax (mining rewards, fee revenue) | set up accounting early. |
| Brand similarity to **abacus.ai** (AI company) | different spelling (`Abakos` with "k") + own ticker `ABA` + crypto/DePIN vs. AI tooling (different trademark class). **Trademark search (classes 9/42)** in target markets before launch; keep fallbacks `Calxis`/`Zultanite` ready. |

## Reputation risk

- DePIN/"AI coin" space is full of scams (see Granium, Gravium, Granume in name research). → **honesty as brand**: peer-reviewed basis, open code, honest "% useful" metric, no hype promises.

## Required before mainnet

- [ ] smart contract/protocol audit
- [ ] legal opinion token + chat
- [ ] clear ToS/privacy for Abakos Chat
- [ ] responsible tokenomics disclosure
- [ ] trademark search "Abakos" due to abacus.ai (classes 9/42)
