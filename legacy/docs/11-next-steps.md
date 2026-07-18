# 11 · Next Steps

## Immediate open decisions

1. **Name:** ✅ `Abakos` (ticker `ABA`) decided, `abakos.ai` reserved. Fallbacks: `Calxis` / `Zultanite` / `Kunzite`. Open: **trademark search due to abacus.ai** (classes 9/42), remaining domains/social handles, ticker collision on exchanges.
2. **Direction:** ✅ **serious protocol**: token only around mainnet (Launch phase), no fast launch.
3. **Penalty share for empty mining:** ✅ **burn** (deflationary, clean; changeable via governance later).
4. **Workstreams:** ✅ **B** marketplace spec · ✅ **C** litepaper + landing page (**live at https://abakos.ai** with waitlist) · ✅ **D** financial/runway model (`model/model.py`). **Open: A) `btcd` fork repo** (private on GitHub). Funding: `docs/12`, fundraising: `docs/13`.
5. **Launch strategy:** ✅ **mainnet-first**, but with mandatory gate of **incentivized testnet + audit** first (see Doc 07). Token only at mainnet.
6. **Product order:** ✅ **testnet first** → marketplace (batch) → developer API → Abakos Chat. Master plan: **`docs/17-testnet-plan.md`**.

## The next 14 days (testnet Phase 0)

See **`docs/17-testnet-plan.md` §14**, summary:

1. [x] Pearl/btcd: document PoW replacement points → [`docs/spec-pouw-integration.md`](spec-pouw-integration.md)
2. [x] `btcd` as Go module dep, `abkd` builds with Abakos `params` + `chaincfg`
3. [x] local simnet (2 nodes P2P, `abkd --listen` + `--connect`)
4. [x] PoUW CPU spike (INT8 GEMM + Blake3, `pouw/gemm.go`, `--verifier gemm`)
5. [x] `WorkVerifier` interface in `node/pouw/`
6. [x] first PoUW block locally (GEMM verifier, 2-node sync)
7. [ ] explorer wireframe + testnet genesis parameters finalize → explorer ✅, genesis draft in `chaincfg/genesis.go`
8. [ ] 2 outreach contacts (neocloud + dev from waitlist)

## Before launch (mandatory checklist)

- [ ] secure remaining domains + brand + ticker + social handles (`abakos.ai` ✅)
- [ ] trademark search "Abakos" due to abacus.ai (classes 9/42)
- [ ] protocol audit
- [ ] legal opinion (token + chat)
- [ ] ToS/privacy for Abakos Chat
- [ ] prepare liquidity/listing
- [ ] benchmark Gonka & Pearl in detail (Doc 09)

## References (research sources)

- Pearl whitepaper: https://pearlresearch.ai/
- cuPOW paper (eprint): https://eprint.iacr.org/2025/685
- "Usefulness gap" study: https://arxiv.org/html/2606.04819v2
- AGTI report (PoUW critique): https://agti.net/intelligence-reports/2026/05/23/pearl-pouw-useful-work-asic-analysis/
- HashrateIndex Pearl explainer: https://hashrateindex.com/blog/pearl-prl-ai-compute-cryptocurrency/
- Gonka (competitor): https://gonka.ai/ , https://github.com/gonka-ai/gonka
