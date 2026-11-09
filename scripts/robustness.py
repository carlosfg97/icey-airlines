"""Robustness checks for docs/hypotheses.md (Nov 9 review). Deterministic, no API calls, no LLMs.

  python scripts/robustness.py

Each section asks whether a conclusion in docs/hypotheses.md survives a different, defensible way of
using the same data. Base prompt only (airline not named), except R9.

  R1  Classification: does counting the AI travel agent (helloaxel.com) as an intermediary move H1/H2?
  R2  Exclusive outcomes: OTA only / own site only / both / neither (Claude cites ~6 URLs, so "any OTA" saturates)
  R3  Own-site page type: fare/route page vs info page (baggage, onboard, PDFs) -> H1/H2/H5 on fare pages
  R4  Route as the unit: only 10 routes per airline, so airline claims (H2, H5) need a route-level interval
  R5  H4 (first class) within route x model strata, plus "more citations" vs "more OTA" check
  R6  H3 mechanism: does the search query name the airline, and is the site returned when it does?
  R7  X1 absence: the "alaska" regex also matches the state (Anchorage, Alaska) -> stricter brand regex
  R8  Model drift: OpenAI results with gpt-6-luna only
  R9  H6: named batch vs base batches with the same routes (instead of adjacent batches)
  R10 AI travel agent (helloaxel.com): who cites it, when it is retrieved, and on which trips

The domain list was reviewed on Nov 9 (missing OTAs and airline domains added to config/domains.yaml;
helloaxel.com, an AI-native ticket search, stays "other" but is tracked here by domain). Fee/policy guides and small
fare sites stay "other".
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from hypotheses import AIRLINES, CUTOFF, REPS, SEED, bootstrap, fmt, prep, summarize  # noqa: E402
from src.analyze import build_frame, load_rows  # noqa: E402
from src.classify import classify_url, load_domains, split_url  # noqa: E402

# Own-site URL that can show a fare or start a booking (vs baggage, onboard, news, PDFs, agency pages).
FARE_PATH = re.compile(r"flights-from-|/flights/|flightsearch|flight-search|/shopping/|/air/booking|"
                       r"fare-information|comparefares|/deals/|book-a-flight|/booking", re.I)
AI_AGENT = {"helloaxel.com"}  # AI travel agents, tracked by domain (they stay "other" in config/domains.yaml)
BRAND = {"alaska": r"alaska airlines|alaska air\b|alaskaair|alaska's|hawaiian airlines",
         "delta": r"\bdelta\b", "southwest": r"\bsouthwest\b"}
KEYS = [f"{p}_{a}" for p in ("anthropic", "openai") for a in AIRLINES]


def frame():
    cfg = load_domains()
    rows = load_rows(ROOT / "data" / "results.jsonl")
    df = build_frame(rows, cfg)
    ext = []
    for r in rows:
        if r.get("error"):
            continue
        a = r["airline_target"]
        cit = [(classify_url(u, a, cfg), u) for u in r.get("cited_urls", [])]
        ret = [(classify_url(u, a, cfg), u) for u in r.get("result_urls", [])]
        ai_doms = AI_AGENT
        own_c = [u for (_, c), u in cit if c == "airline_direct_target"]
        own_r = [u for (_, c), u in ret if c == "airline_direct_target"]
        q = " | ".join(r.get("search_queries") or []).lower()
        text = (r.get("response_text") or "").lower()
        ext.append({
            "cited_ai": any(d in ai_doms for (d, _), _ in cit),
            "seen_ai": any(d in ai_doms for (d, _), _ in ret),
            "own_fare_cited": any(FARE_PATH.search(urlparse(u).path) for u in own_c),
            "own_fare_seen": any(FARE_PATH.search(urlparse(u).path) for u in own_r),
            "q_names": bool(re.search({"alaska": r"alaska air|alaskaair", "delta": r"delta",
                                       "southwest": r"southwest"}[a], q)),
            "absent_strict": not re.search(BRAND[a], text),
        })
    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(ext)], axis=1)
    df["ota_or_ai"] = df.cited_ota | df.cited_ai
    df["ota_only"] = df.cited_ota & ~df.cited_target
    df["own_only"] = df.cited_target & ~df.cited_ota
    df["both"] = df.cited_ota & df.cited_target
    df["neither"] = ~df.cited_ota & ~df.cited_target
    return df


def batch_ci(d, flag_a, flag_b=None, airline_a="alaska", airline_b="delta"):
    """Share(flag) airline_a - airline_b (or flag_a - flag_b within all calls), batch-cluster bootstrap."""
    if flag_b is None:
        m = prep(d, {"na": d.airline_target == airline_a, "ka": (d.airline_target == airline_a) & d[flag_a],
                     "nb": d.airline_target == airline_b, "kb": (d.airline_target == airline_b) & d[flag_a]})
        st = lambda v: v["ka"] / v["na"] - v["kb"] / v["nb"]
    else:
        m = prep(d, {"n": d[flag_a] | True, "a": d[flag_a], "b": d[flag_b]})
        st = lambda v: (v["a"] - v["b"]) / v["n"]
    return summarize(*bootstrap(m, st))


def route_boot(d, num, den, airline_a, airlines_b, reps=REPS):
    """sum(num)/sum(den) for airline_a minus the same for airlines_b, resampling ROUTES within each airline."""
    g = d.groupby(["airline_target", "route_id"]).agg(num=(num, "sum"), den=(den, "sum")).reset_index()
    rng = np.random.default_rng(SEED)
    arr = {a: g[g.airline_target == a][["num", "den"]].values for a in AIRLINES}

    def rate(parts):
        s = sum(p.sum(axis=0) for p in parts)
        return s[0] / s[1] if s[1] else np.nan

    point = rate([arr[airline_a]]) - rate([arr[b] for b in airlines_b])
    dist = []
    for _ in range(reps):
        res = {a: x[rng.integers(0, len(x), len(x))] for a, x in arr.items()}
        dist.append(rate([res[airline_a]]) - rate([res[b] for b in airlines_b]))
    dist = np.array(dist)
    return summarize(point, dist[~np.isnan(dist)])


def line(label, res):
    pt, lo, hi, p = res
    return f"  {label:52s} {fmt(pt):>9s}  95% CI [{fmt(lo)}, {fmt(hi)}]  p = {p:.3f}"


def table(d, flags, by=("provider", "airline_target")):
    return (d.groupby(list(by))[list(flags)].mean() * 100).round(0).astype(int).to_string()


def main():
    pd.set_option("display.width", 200)
    df = frame()
    b = df[df.prompt_variant == "base"].copy()
    b["one"] = True
    print(f"Base prompt: {len(b)} calls, {b.run_number.nunique()} batches, {b.route_id.nunique()} routes\n")

    print("=" * 78 + "\nR1  Classification sensitivity (share of calls, %)\n" + "=" * 78)
    print("  cited_ai = cites the AI travel agent (helloaxel.com); ota_or_ai = OTA or AI travel agent")
    print(table(b, ["cited_target", "cited_ota", "cited_ai", "ota_or_ai"]))
    for flag in ("cited_ota", "ota_or_ai"):
        for prov in ("anthropic", "openai"):
            s = b[b.provider == prov]
            print(line(f"H2 {flag} Alaska - Delta ({prov})", batch_ci(s, flag)))
    o = b[(b.provider == "openai") & (b.airline_target == "alaska")]
    print(line("H1 OpenAI Alaska: own - OTA (docs definition)", batch_ci(o, "cited_target", "cited_ota")))
    print(line("H1 OpenAI Alaska: own - (OTA or AI agent)", batch_ci(o, "cited_target", "ota_or_ai")))

    print("\n" + "=" * 78 + "\nR2  Exclusive outcomes (share of calls, %)\n" + "=" * 78)
    print(table(b, ["ota_only", "both", "own_only", "neither"]))
    for prov in ("anthropic", "openai"):
        s = b[b.provider == prov]
        print(line(f"H2 on 'OTA only' Alaska - Delta ({prov})", batch_ci(s, "ota_only")))
        print(line(f"H2 on 'OTA only' Alaska - Southwest ({prov})", batch_ci(s, "ota_only", airline_b="southwest")))

    print("\n" + "=" * 78 + "\nR3  Own-site page type (share of calls, %)\n" + "=" * 78)
    print("  own_fare_* = own-site URL that can show a fare or start a booking (route page, booking page)")
    print(table(b, ["seen_target", "own_fare_seen", "cited_target", "own_fare_cited"]))
    o = b[b.provider == "openai"]
    for cond, lab in (("seen_target", "any own page retrieved"), ("own_fare_seen", "own FARE page retrieved")):
        s = o[o[cond]]
        print(f"  OpenAI cites own site | {lab}: " + ", ".join(
            f"{a} {s[s.airline_target == a].cited_target.mean():.0%} (n={(s.airline_target == a).sum()})" for a in AIRLINES))
        m = prep(s, {**{f"n_{a}": s.airline_target == a for a in AIRLINES},
                     **{f"k_{a}": (s.airline_target == a) & s.cited_target for a in AIRLINES}})
        st = lambda v: v["k_alaska"] / v["n_alaska"] - (v["k_delta"] + v["k_southwest"]) / (v["n_delta"] + v["n_southwest"])
        print(line(f"H5 Alaska - others | {lab}", summarize(*bootstrap(m, st))))

    print("\n" + "=" * 78 + "\nR4  Route as the unit (10 routes per airline; resample routes within airline)\n" + "=" * 78)
    for prov in ("anthropic", "openai"):
        s = b[b.provider == prov]
        print(f"  {prov}: OTA cited by route (%):  " + "  ".join(
            f"{r}:{v:.0f}" for r, v in (s.groupby('route_id').cited_ota.mean() * 100).items()))
    for prov in ("anthropic", "openai"):
        s = b[b.provider == prov]
        print(line(f"H2 cited_ota Alaska - Delta ({prov}), route CI", route_boot(s, "cited_ota", "one", "alaska", ["delta"])))
        print(line(f"H2 cited_ota Alaska - Southwest ({prov}), route CI",
                   route_boot(s, "cited_ota", "one", "alaska", ["southwest"])))
    o = b[b.provider == "openai"].copy()
    o["cr"] = o.cited_target & o.seen_target
    print(line("H5 (OpenAI cited|retrieved) Alaska - others, route CI",
               route_boot(o, "cr", "seen_target", "alaska", ["delta", "southwest"])))
    oa = o[o.airline_target == "alaska"]
    rest = o[o.airline_target != "alaska"]
    base_other = rest.cr.sum() / rest.seen_target.sum()
    loo = [(r, oa[oa.route_id != r].cr.sum() / oa[oa.route_id != r].seen_target.sum() - base_other)
           for r in sorted(oa.route_id.unique())]
    print("  H5 leave-one-Alaska-route-out: " + ", ".join(f"-{r}: {fmt(v)}" for r, v in loo))
    per = (oa.groupby("route_id").cr.sum() / oa.groupby("route_id").seen_target.sum() * 100).round(0)
    print("  OpenAI cited|retrieved by Alaska route (%): " + "  ".join(f"{r}:{v:.0f}" for r, v in per.items()))

    print("\n" + "=" * 78 + "\nR5  H4 first class vs basic economy, within route x model strata\n" + "=" * 78)
    for flag in ("cited_ota", "ota_only", "cited_target", "own_fare_cited"):
        specs, keys = {}, []
        for pr in ("anthropic", "openai"):
            for r in b.route_id.unique():
                s = (b.provider == pr) & (b.route_id == r)
                if (s & (b.fare_type == "first_premium")).sum() and (s & (b.fare_type == "basic_economy")).sum():
                    k = f"{pr}_{r}"
                    keys.append(k)
                    for tag, lvl in (("hi", "first_premium"), ("lo", "basic_economy")):
                        specs[f"n_{k}_{tag}"] = s & (b.fare_type == lvl)
                        specs[f"o_{k}_{tag}"] = s & (b.fare_type == lvl) & b[flag]
        m = prep(b, specs)
        st = lambda v: sum(v[f"o_{k}_hi"] / v[f"n_{k}_hi"] - v[f"o_{k}_lo"] / v[f"n_{k}_lo"] for k in keys) / len(keys)
        print(line(f"{flag}: first - basic ({len(keys)} strata)", summarize(*bootstrap(m, st))))
    print("  cited URLs per call by fare: " + ", ".join(
        f"{p} {f}: {b[(b.provider == p) & (b.fare_type == f)].cited_n.mean():.1f}"
        for p in ("anthropic", "openai") for f in ("basic_economy", "first_premium")))
    print("  by discovery / confirmation set (OTA cited, first - basic, raw):")
    ts = pd.to_datetime(b.timestamp_utc, utc=True)
    for lab, s in (("discovery", b[ts <= pd.Timestamp(CUTOFF)]), ("confirmation", b[ts > pd.Timestamp(CUTOFF)])):
        print(f"    {lab:12s} " + ", ".join(
            f"{p}: {s[(s.provider == p) & (s.fare_type == 'first_premium')].cited_ota.mean() - s[(s.provider == p) & (s.fare_type == 'basic_economy')].cited_ota.mean():+.0%}"
            for p in ("anthropic", "openai")))

    print("\n" + "=" * 78 + "\nR6  H3 mechanism: search query names the airline -> own site returned?\n" + "=" * 78)
    g = b.groupby(["provider", "airline_target"]).agg(query_names=("q_names", "mean"))
    g["retrieved_if_named"] = b[b.q_names].groupby(["provider", "airline_target"]).seen_target.mean()
    g["retrieved_if_not"] = b[~b.q_names].groupby(["provider", "airline_target"]).seen_target.mean()
    g["n_named"] = b[b.q_names].groupby(["provider", "airline_target"]).size()
    print((g * [100, 100, 100, 1]).round(0).astype(int).to_string())

    print("\n" + "=" * 78 + "\nR7  X1 absence: docs regex vs brand-only regex (share of calls, %)\n" + "=" * 78)
    print(table(b, ["absent", "absent_strict"]))

    print("\n" + "=" * 78 + "\nR8  OpenAI by model (share of calls, %)\n" + "=" * 78)
    o = b[b.provider == "openai"]
    print(table(o, ["cited_target", "cited_ota", "seen_target"], by=("model", "airline_target")))
    print("  calls per model in discovery / confirmation: " + str(
        o.assign(conf=pd.to_datetime(o.timestamp_utc, utc=True) > pd.Timestamp(CUTOFF))
        .groupby(["conf", "model"]).size().to_dict()))
    o = o.assign(cr=o.cited_target & o.seen_target, conf=pd.to_datetime(o.timestamp_utc, utc=True) > pd.Timestamp(CUTOFF))
    for lab, s in (("sol (all discovery)", o[o.model == "gpt-6.1-sol"]),
                   ("luna, discovery", o[(o.model == "gpt-6-luna") & ~o.conf]),
                   ("luna, confirmation", o[(o.model == "gpt-6-luna") & o.conf])):
        print(line(f"H5 {lab}, route CI", route_boot(s, "cr", "seen_target", "alaska", ["delta", "southwest"])))
    for m_ in ("gpt-6.1-sol", "gpt-6-luna"):
        s = o[o.model == m_]
        print(line(f"H1 {m_}, Alaska own - OTA", batch_ci(s[s.airline_target == "alaska"], "cited_target", "cited_ota")))
        print(f"  H4 {m_}: OTA cited first - basic (raw) "
              f"{s[s.fare_type == 'first_premium'].cited_ota.mean() - s[s.fare_type == 'basic_economy'].cited_ota.mean():+.0%}")

    print("\n" + "=" * 78 + "\nR9  H6 named batch vs base batches covering the SAME routes and directions\n" + "=" * 78)
    nm = df[df.prompt_variant == "named"]
    key = ["provider", "route_id", "direction"]
    mb = b.merge(nm[key].drop_duplicates(), on=key)
    print(f"  named: {len(nm)} calls (batch {sorted(nm.run_number.unique())});  matched base: {len(mb)} calls "
          f"from batches {sorted(mb.run_number.unique())}")
    out = pd.DataFrame({
        "named": nm.groupby("provider")[["cited_ota", "cited_target", "seen_target", "absent_strict"]].mean().stack(),
        "base_same_routes": mb.groupby("provider")[["cited_ota", "cited_target", "seen_target", "absent_strict"]].mean().stack()})
    print((out * 100).round(0).astype(int).to_string())

    print("\n" + "=" * 78 + "\nR10 AI travel agent (helloaxel.com)\n" + "=" * 78)
    b["ai_cr"] = b.cited_ai & b.seen_ai
    g = b.groupby(["provider", "airline_target"]).agg(retrieved=("seen_ai", "mean"), cited=("cited_ai", "mean"))
    g["cited_if_retrieved"] = b[b.seen_ai].groupby(["provider", "airline_target"]).cited_ai.mean()
    g["n_retrieved"] = b[b.seen_ai].groupby(["provider", "airline_target"]).size()
    print((g * [100, 100, 100, 1]).round(0).fillna(0).astype(int).to_string())
    for col in ("fare_type", "booking_window"):
        print(f"  cited by {col} (%): " + ", ".join(f"{k} {v:.0f}" for k, v in (b.groupby(col).cited_ai.mean() * 100).items()))
    print("  cited by route (%, top 8): " + ", ".join(
        f"{k} {v:.0f}" for k, v in (b.groupby("route_id").cited_ai.mean() * 100).sort_values(ascending=False).head(8).items()))
    ai = b[b.cited_ai]
    print(f"  when cited (n={len(ai)}): also cites an OTA {ai.cited_ota.mean():.0%}, own site {ai.cited_target.mean():.0%}, "
          f"AI agent only intermediary (no OTA) {(~ai.cited_ota).mean():.0%}")
    t = pd.to_datetime(b.timestamp_utc, utc=True).dt.floor("D")
    print("  cited by day (%): " + ", ".join(f"{k:%b %d} {v:.0f}" for k, v in (b.groupby(t).cited_ai.mean() * 100).items()))
    o = b[b.provider == "openai"]
    print("  OpenAI by model (%): " + ", ".join(f"{m} {v:.0f}" for m, v in (o.groupby("model").cited_ai.mean() * 100).items()))


if __name__ == "__main__":
    main()
