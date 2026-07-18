#!/usr/bin/env python3
"""Abakos (ABA) financial & runway model, calibratable, stdlib-only.

Computes, from a single CONFIG block:
  1) Token emission / supply schedule (Bitcoin-style halving, fit to the
     mining allocation so cumulative emission converges to it).
  2) Revenue scenarios (marketplace fee + Abakos Chat margin).
  3) Annual burn estimate (fee burn).
  4) Month-by-month runway simulation -> months of runway + break-even.
  5) Token-value sensitivity for the treasury / liquidity buckets.

All numbers are ILLUSTRATIVE starting assumptions. Edit CONFIG and re-run:
    python model.py
Outputs a console report and writes model_output.csv next to this file.
"""
from __future__ import annotations

import csv
import os
import sys

# --------------------------------------------------------------------------
# CONFIG: edit these
# --------------------------------------------------------------------------
CONFIG = {
    "max_supply": 2_100_000_000,        # total ABA
    "alloc": {                          # must sum to 1.0
        "mining": 0.70,
        "treasury": 0.10,
        "team": 0.08,
        "liquidity_listing": 0.07,
        "ecosystem": 0.05,
    },
    "halving_years": 4,                 # emission halves every N years
    "model_years": 8,

    "marketplace_fee": 0.02,            # 2% on every compute trade
    "fee_burn_share": 0.50,            # half of the fee is burned
    "reward_floor": 0.25,              # empty mining gets 25% of block reward

    # Revenue scenarios: (label, active_gpus, usd_per_gpu_hour, utilization,
    #                     chat_users, chat_paying_pct, chat_arpu_usd_month)
    "scenarios": [
        ("Start",    500,   1.50, 0.50,   5_000, 0.15, 3.0),
        ("Growth",   2_000, 1.50, 0.55,  50_000, 0.18, 3.0),
        ("Scale",    10_000, 1.50, 0.60, 300_000, 0.20, 3.5),
    ],
    "chat_gross_margin": 0.45,          # share of chat revenue kept after inference cost

    # Runway
    "preseed_usd": 1_500_000,
    "opex_monthly_usd": 50_000,         # team + infra + misc
    "onetime": {"audit": 60_000, "legal": 45_000, "listing": 40_000},
    "onetime_month": 5,                 # month the one-time costs hit
    "runway_months": 24,
    # Stablecoin revenue ramp: revenue reaches the Start scenario by month
    # `ramp_start_m`, Growth by `ramp_growth_m`, Scale by `ramp_scale_m`.
    "ramp_start_m": 7,
    "ramp_growth_m": 13,
    "ramp_scale_m": 20,

    # Sensitivity: ABA prices to value the buckets at
    "abk_prices": [0.05, 0.20, 0.76, 2.00],
}


# --------------------------------------------------------------------------
def fmt(n, money=True):
    if money:
        if abs(n) >= 1e9:
            return f"${n/1e9:.2f}B"
        if abs(n) >= 1e6:
            return f"${n/1e6:.2f}M"
        if abs(n) >= 1e3:
            return f"${n/1e3:.1f}k"
        return f"${n:,.0f}"
    if abs(n) >= 1e9:
        return f"{n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"{n/1e6:.1f}M"
    if abs(n) >= 1e3:
        return f"{n/1e3:.1f}k"
    return f"{n:,.0f}"


def emission_schedule(cfg):
    """Halving emission fit so cumulative -> mining allocation."""
    mining = cfg["max_supply"] * cfg["alloc"]["mining"]
    h = cfg["halving_years"]
    # sum over infinite halvings of annual emission across epochs:
    #   total = first_epoch_annual * h * (1 + 1/2 + 1/4 + ...) = first_epoch_annual * h * 2
    first_annual = mining / (h * 2)
    rows, cum = [], 0.0
    for y in range(1, cfg["model_years"] + 1):
        epoch = (y - 1) // h
        annual = first_annual * (0.5 ** epoch)
        cum += annual
        rows.append((y, annual, cum, cum / cfg["max_supply"]))
    return first_annual, rows


def scenario_revenue(cfg, gpus, price, util, users, paying, arpu):
    days = 30
    volume_m = gpus * price * 24 * days * util          # monthly compute traded ($)
    fee_m = volume_m * cfg["marketplace_fee"]
    chat_gross_m = users * paying * arpu
    chat_net_m = chat_gross_m * cfg["chat_gross_margin"]
    total_m = fee_m + chat_net_m
    return {
        "volume_m": volume_m, "fee_m": fee_m,
        "chat_gross_m": chat_gross_m, "chat_net_m": chat_net_m,
        "total_m": total_m,
    }


def runway_sim(cfg, scen_rev):
    """Month-by-month cash simulation."""
    start = scen_rev["Start"]["total_m"]
    growth = scen_rev["Growth"]["total_m"]
    scale = scen_rev["Scale"]["total_m"]
    rs, rg, rc = cfg["ramp_start_m"], cfg["ramp_growth_m"], cfg["ramp_scale_m"]

    def rev_at(m):
        if m < rs:
            return start * (m / rs)                      # ramp 0 -> Start
        if m < rg:
            return start + (growth - start) * (m - rs) / (rg - rs)
        if m < rc:
            return growth + (scale - growth) * (m - rg) / (rc - rg)
        return scale

    cash = cfg["preseed_usd"]
    opex = cfg["opex_monthly_usd"]
    onetime_total = sum(cfg["onetime"].values())
    rows = []
    runway_end = None
    breakeven = None
    for m in range(1, cfg["runway_months"] + 1):
        rev = rev_at(m)
        cost = opex + (onetime_total if m == cfg["onetime_month"] else 0)
        net = rev - cost
        cash += net
        if breakeven is None and rev >= opex:
            breakeven = m
        if runway_end is None and cash <= 0:
            runway_end = m
        rows.append((m, rev, cost, net, cash))
    return rows, runway_end, breakeven


def main():
    cfg = CONFIG
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    assert abs(sum(cfg["alloc"].values()) - 1.0) < 1e-9, "alloc must sum to 1"
    out_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_output.csv")
    csv_rows = []

    print("=" * 68)
    print("  ABAKOS (ABA) - FINANCIAL & RUNWAY MODEL  (illustrative)")
    print("=" * 68)

    # 1) Allocation
    print("\n[1] TOKEN ALLOCATION  (max supply %s ABA)" % fmt(cfg["max_supply"], False))
    for k, v in cfg["alloc"].items():
        tok = cfg["max_supply"] * v
        print(f"    {k:18s} {v*100:5.1f}%   {fmt(tok, False):>8s} ABA")

    # 2) Emission schedule
    first_annual, rows = emission_schedule(cfg)
    print(f"\n[2] EMISSION (halving every {cfg['halving_years']}y; "
          f"yr1 ~ {fmt(first_annual, False)} ABA = {first_annual/365/24:,.0f} ABA/h)")
    print(f"    {'year':>4} {'minted':>10} {'cum.supply':>12} {'% of max':>9}")
    for y, annual, cum, pct in rows:
        print(f"    {y:>4} {fmt(annual, False):>10} {fmt(cum, False):>12} {pct*100:>8.1f}%")
        csv_rows.append(["emission", y, round(annual), round(cum), round(pct, 4)])

    # 3) Revenue scenarios
    print("\n[3] REVENUE SCENARIOS  (per month)")
    print(f"    {'scenario':9} {'GPUs':>7} {'volume':>9} {'fee':>8} "
          f"{'chat_net':>9} {'TOTAL/mo':>10} {'TOTAL/yr':>10}")
    scen_rev = {}
    for (label, gpus, price, util, users, paying, arpu) in cfg["scenarios"]:
        r = scenario_revenue(cfg, gpus, price, util, users, paying, arpu)
        scen_rev[label] = r
        print(f"    {label:9} {gpus:>7,} {fmt(r['volume_m']):>9} {fmt(r['fee_m']):>8} "
              f"{fmt(r['chat_net_m']):>9} {fmt(r['total_m']):>10} {fmt(r['total_m']*12):>10}")
        csv_rows.append(["revenue", label, round(r["volume_m"]), round(r["fee_m"]),
                         round(r["chat_net_m"]), round(r["total_m"])])

    # 4) Burn estimate (annual, from fee burn) per scenario
    print("\n[4] ANNUAL FEE-BURN ESTIMATE  (%.0f%% of the %.0f%% fee)"
          % (cfg["fee_burn_share"] * 100, cfg["marketplace_fee"] * 100))
    for label, r in scen_rev.items():
        burn_usd_yr = r["fee_m"] * 12 * cfg["fee_burn_share"]
        print(f"    {label:9} ~ {fmt(burn_usd_yr)}/yr burned (USD-equiv of ABA)")
        csv_rows.append(["burn", label, round(burn_usd_yr)])

    # 5) Runway
    rows, runway_end, breakeven = runway_sim(cfg, scen_rev)
    print(f"\n[5] RUNWAY  (pre-seed {fmt(cfg['preseed_usd'])}, opex "
          f"{fmt(cfg['opex_monthly_usd'])}/mo, one-time {fmt(sum(cfg['onetime'].values()))} @ m{cfg['onetime_month']})")
    print(f"    {'month':>5} {'revenue':>9} {'cost':>9} {'net':>10} {'cash':>11}")
    for (m, rev, cost, net, cash) in rows:
        flag = ""
        if m == breakeven:
            flag = "  <- break-even (rev>=opex)"
        print(f"    {m:>5} {fmt(rev):>9} {fmt(cost):>9} {fmt(net):>10} {fmt(cash):>11}{flag}")
        csv_rows.append(["runway", m, round(rev), round(cost), round(net), round(cash)])
    print(f"\n    Break-even month: {breakeven if breakeven else 'n/a'}")
    print(f"    Cash exhausted:   {('month '+str(runway_end)) if runway_end else 'NOT within '+str(cfg['runway_months'])+' months (survives)'}")

    # 6) Sensitivity
    print("\n[6] BUCKET VALUE BY ABA PRICE  (treasury + liquidity+listing)")
    tre = cfg["max_supply"] * cfg["alloc"]["treasury"]
    liq = cfg["max_supply"] * cfg["alloc"]["liquidity_listing"]
    print(f"    {'ABA $':>7} {'treasury':>11} {'liq+listing':>12} {'combined':>11}")
    for p in cfg["abk_prices"]:
        print(f"    {p:>7.2f} {fmt(tre*p):>11} {fmt(liq*p):>12} {fmt((tre+liq)*p):>11}")
        csv_rows.append(["bucket_value", p, round(tre*p), round(liq*p)])

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["section", "k", "a", "b", "c", "d"]] + csv_rows)
    print(f"\n[csv] wrote {out_csv}")
    print("=" * 68)
    print("  NOTE: illustrative assumptions, calibrate CONFIG to real data.")
    print("=" * 68)


if __name__ == "__main__":
    main()
