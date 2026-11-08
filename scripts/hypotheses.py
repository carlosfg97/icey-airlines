"""Pre-specified follow-up hypotheses on data/results.jsonl. Deterministic, no API calls, no LLMs.

  python scripts/hypotheses.py            # discovery set (batches up to CUTOFF) and confirmation set (after it)

Method: calls inside one hourly batch share routes/dates, so they are NOT independent. Every interval and
p-value comes from a cluster bootstrap that resamples whole batches (10,000 reps, seed 7). The three
primary p-values get a Holm correction. The hypotheses were formed by looking at the data up to CUTOFF,
so results on that set are exploratory; batches that arrive after CUTOFF are the confirmation set.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.analyze import build_frame, load_rows  # noqa: E402
from src.classify import load_domains  # noqa: E402

CUTOFF = "2026-11-08T02:05:00+00:00"   # hypotheses were written after seeing the data up to here
REPS, SEED = 10_000, 7
AIRLINES = ["alaska", "delta", "southwest"]
EQ_MARGIN = 0.20                        # H3: "same within +-20 percentage points"


def prep(d, specs):
    g = pd.DataFrame({k: v.astype(float).values for k, v in specs.items()})
    g["_b"] = d.run_number.values
    return g.groupby("_b").sum()


def bootstrap(m, stat):
    X = m.values
    nb = len(X)
    rng = np.random.default_rng(SEED)
    S = rng.multinomial(nb, [1 / nb] * nb, size=REPS) @ X
    cols = {c: S[:, i] for i, c in enumerate(m.columns)}
    obs = {c: X[:, i].sum() for i, c in enumerate(m.columns)}
    with np.errstate(divide="ignore", invalid="ignore"):
        point, dist = stat(obs), stat(cols)
    dist = np.asarray(dist, dtype=float)
    return float(point), dist[~np.isnan(dist)]


def summarize(point, dist, level=95):
    lo, hi = np.percentile(dist, [(100 - level) / 2, 100 - (100 - level) / 2])
    p = max(2 * min((dist <= 0).mean(), (dist >= 0).mean()), 1 / len(dist))
    return point, lo, hi, min(p, 1.0)


def holm(ps):
    order = np.argsort(ps)
    adj, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(ps) - rank) * ps[i])
        adj[i] = min(1.0, running)
    return adj


def fmt(x):
    return f"{x * 100:+.1f} pp"


def run(d, label):
    print(f"\n{'=' * 78}\n{label}: {len(d)} calls, {d.run_number.nunique()} batches\n{'=' * 78}")
    if d.run_number.nunique() < 3:
        print("  too few batches to bootstrap yet")
        return
    primary = {}

    # ---- H3: retrieval gap (Claude) -----------------------------------------------------------------
    c = d[d.provider == "anthropic"]
    specs = {}
    for a in AIRLINES:
        s = c.airline_target == a
        specs[f"n_{a}"], specs[f"ret_{a}"] = s, s & c.seen_target
        specs[f"cr_{a}"] = s & c.seen_target & c.cited_target
    m = prep(c, specs)
    ret_stat = lambda v: v["ret_delta"] / v["n_delta"] - (v["ret_alaska"] + v["ret_southwest"]) / (v["n_alaska"] + v["n_southwest"])
    cond_stat = lambda v: v["cr_delta"] / v["ret_delta"] - (v["cr_alaska"] + v["cr_southwest"]) / (v["ret_alaska"] + v["ret_southwest"])
    pt, lo, hi, p = summarize(*bootstrap(m, ret_stat))
    primary["H3 retrieval gap (Claude, delta.com returned by search)"] = p
    print(f"\nH3  Claude's Delta gap is retrieval, not preference")
    print(f"  own site appears in Claude's search results:  Delta {m.ret_delta.sum() / m.n_delta.sum():.0%}  vs  "
          f"Alaska+Southwest {(m.ret_alaska.sum() + m.ret_southwest.sum()) / (m.n_alaska.sum() + m.n_southwest.sum()):.0%}")
    print(f"  difference {fmt(pt)}   95% CI [{fmt(lo)}, {fmt(hi)}]   p = {p:.4f}")
    pt2, lo2, hi2, _ = summarize(*bootstrap(m, cond_stat), level=90)
    print(f"  Claude cites it WHEN it appears:  Delta {m.cr_delta.sum() / m.ret_delta.sum():.0%} (n={int(m.ret_delta.sum())} calls)  vs  "
          f"others {(m.cr_alaska.sum() + m.cr_southwest.sum()) / (m.ret_alaska.sum() + m.ret_southwest.sum()):.0%}")
    eq = lo2 > -EQ_MARGIN and hi2 < EQ_MARGIN
    print(f"  difference {fmt(pt2)}   90% CI [{fmt(lo2)}, {fmt(hi2)}]   equivalence margin +-{EQ_MARGIN * 100:.0f} pp -> "
          f"{'EQUIVALENT (CI inside margin)' if eq else 'NOT established (CI crosses margin: low power)'}")

    # ---- H4: premium cabin -> more OTA ------------------------------------------------------------------
    def contrast(col, hi_level, lo_level):
        specs = {}
        for pr in ("anthropic", "openai"):
            for a in AIRLINES:
                s = (d.provider == pr) & (d.airline_target == a)
                for tag, lvl in (("hi", hi_level), ("lo", lo_level)):
                    k = f"{pr}_{a}_{tag}"
                    specs[f"n_{k}"], specs[f"o_{k}"] = s & (d[col] == lvl), s & (d[col] == lvl) & d.cited_ota
        mm = prep(d, specs)
        keys = [f"{pr}_{a}" for pr in ("anthropic", "openai") for a in AIRLINES]
        stat = lambda v: sum(v[f"o_{k}_hi"] / v[f"n_{k}_hi"] - v[f"o_{k}_lo"] / v[f"n_{k}_lo"] for k in keys) / len(keys)
        return mm, stat

    mm, stat = contrast("fare_type", "first_premium", "basic_economy")
    pt, lo, hi, p = summarize(*bootstrap(mm, stat))
    primary["H4 first class vs basic economy (OTA cited)"] = p
    rate = lambda lvl: d[d.fare_type == lvl].cited_ota.mean()
    print(f"\nH4  First-class queries push agents toward OTAs")
    print(f"  OTA cited:  first class {rate('first_premium'):.0%}   main economy {rate('main_economy'):.0%}   basic economy {rate('basic_economy'):.0%}")
    print(f"  first vs basic (avg within model x airline): {fmt(pt)}   95% CI [{fmt(lo)}, {fmt(hi)}]   p = {p:.4f}")
    print("  controls (same method, NOT primary, descriptive):")
    for col, a, b in (("add_on", "checked_bag", "none"), ("add_on", "seat_selection", "none"),
                      ("booking_window", "holiday", "next_week"), ("booking_window", "next_month", "next_week"),
                      ("direction", "return", "outbound")):
        mm2, st2 = contrast(col, a, b)
        pt2, lo2, hi2, p2 = summarize(*bootstrap(mm2, st2))
        print(f"    {col:15s} {a:>14s} vs {b:<11s} {fmt(pt2):>9s}  95% CI [{fmt(lo2)}, {fmt(hi2)}]  p = {p2:.3f}")

    # ---- H5: OpenAI picks Alaska's own site when it has it --------------------------------------------
    o = d[d.provider == "openai"]
    specs = {}
    for a in AIRLINES:
        s = o.airline_target == a
        specs[f"ret_{a}"], specs[f"cr_{a}"] = s & o.seen_target, s & o.seen_target & o.cited_target
    m = prep(o, specs)
    stat = lambda v: v["cr_alaska"] / v["ret_alaska"] - (v["cr_delta"] + v["cr_southwest"]) / (v["ret_delta"] + v["ret_southwest"])
    pt, lo, hi, p = summarize(*bootstrap(m, stat))
    primary["H5 OpenAI cites Alaska's site when retrieved"] = p
    print(f"\nH5  OpenAI cites Alaska's own site more often than rivals' sites, given it was retrieved")
    for a in AIRLINES:
        print(f"    {a:10s} cited | retrieved = {m['cr_' + a].sum() / m['ret_' + a].sum():.0%}  (n={int(m['ret_' + a].sum())})")
    print(f"  Alaska vs (Delta+Southwest): {fmt(pt)}   95% CI [{fmt(lo)}, {fmt(hi)}]   p = {p:.4f}")

    adj = holm(list(primary.values()))
    print("\nPrimary tests, Holm-adjusted across the three hypotheses:")
    for (k, p), q in zip(primary.items(), adj):
        print(f"  {k:60s} raw p = {p:.4f}   Holm p = {q:.4f}")


def main():
    cfg = load_domains()
    df = build_frame(load_rows(Path(__file__).resolve().parent.parent / "data" / "results.jsonl"), cfg)
    ts = pd.to_datetime(df.timestamp_utc, utc=True)
    cut = pd.Timestamp(CUTOFF)
    run(df[ts <= cut], "DISCOVERY set (data the hypotheses were drawn from, exploratory)")
    run(df[ts > cut], "CONFIRMATION set (batches after the cutoff)")


if __name__ == "__main__":
    main()
