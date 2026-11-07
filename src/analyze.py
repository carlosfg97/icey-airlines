"""Metrics and tests on data/results.jsonl.

  python -m src.analyze                 # print summary, write data/summary.csv and data/domains.csv
  python -m src.analyze --include-tests # also count rows from test runs

Two views of "which sites did the model use":
  cited     = URLs the answer actually cites (what a user would be pointed to)
  consulted = every URL the search returned / the model looked at (broader; OpenAI cites few URLs)
URLs are classified at analysis time from config/domains.yaml, so editing that file reclassifies old data.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from src.classify import CATEGORIES, classify_url, load_domains, registrable_domain

ROOT = Path(__file__).resolve().parent.parent
DIMENSIONS = ["direction", "booking_window", "fare_type", "add_on"]
AIRLINE_WORDS = {"alaska": r"\balaska\b|\bhawaiian\b", "delta": r"\bdelta\b", "southwest": r"\bsouthwest\b"}
DOMAIN_RE = re.compile(r"[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+", re.IGNORECASE)


def load_rows(path, include_tests=False):
    p = Path(path)
    if not p.exists():
        return []
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return [r for r in rows if include_tests or not r.get("is_test")]


def self_reported_domains(text):
    """'KAYAK (kayak.com); Trip.com' -> {'kayak.com', 'trip.com'}"""
    return {d for d in (registrable_domain(m) for m in DOMAIN_RE.findall((text or "").lower())) if d}


def build_frame(rows, cfg, split_models=False):
    """One row per successful call, with per-call flags."""
    out = []
    for r in rows:
        if r.get("error"):
            continue
        a = r["airline_target"]
        cited = [classify_url(u, a, cfg) for u in r.get("cited_urls", [])]
        seen = [classify_url(u, a, cfg) for u in r.get("result_urls", [])]
        text = (r.get("response_text") or "").lower()
        mentioned = {k: bool(re.search(p, text)) for k, p in AIRLINE_WORDS.items()}
        rec = {k: r.get(k) for k in ["run_number", "timestamp_utc", "provider", "model", "airline_target", "route_id",
                                      "direction", "booking_window", "fare_type", "add_on"]}
        for label, items in (("cited", cited), ("seen", seen)):
            cats = Counter(c for _, c in items)
            for c in CATEGORIES:
                rec[f"{label}_{c}"] = cats.get(c, 0)
            rec[f"{label}_n"] = len(items)
            rec[f"{label}_target"] = cats.get("airline_direct_target", 0) > 0
            rec[f"{label}_ota"] = cats.get("ota_aggregator", 0) > 0
        rec["primary_source"] = cited[0][1] if cited else "none"
        rec["target_mentioned"] = mentioned[a]
        rec["other_airline_mentioned"] = any(v for k, v in mentioned.items() if k != a)
        # Absence: the answer never mentions the target airline (approximate text heuristic).
        rec["absent"] = not mentioned[a]
        rep = self_reported_domains(r.get("self_reported_sources"))
        used = {d for d, _ in cited} | {d for d, _ in seen}
        rec["selfreport_n"] = len(rep)
        rec["selfreport_in_used"] = (len(rep & used) / len(rep)) if rep else None
        out.append(rec)
    df = pd.DataFrame(out)
    # Models are pooled per provider by default ("openai"). Pass split_models=True to label them separately
    # ("openai:gpt-6-luna") when a provider's model changed mid-experiment; the `model` column is always kept.
    if split_models and not df.empty:
        multi = df.groupby("provider")["model"].nunique()
        for prov in multi[multi > 1].index:
            m = df["provider"] == prov
            df.loc[m, "provider"] = prov + ":" + df.loc[m, "model"]
    return df


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (centre - half, centre + half)


def two_prop_ztest(k1, n1, k2, n2):
    """Two-sided two-proportion z-test. Returns (z, p) or (nan, nan) if undefined."""
    if n1 == 0 or n2 == 0:
        return (float("nan"), float("nan"))
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return (float("nan"), float("nan"))
    z = (k1 / n1 - k2 / n2) / se
    return (z, math.erfc(abs(z) / math.sqrt(2)))


def share_table(df, by, flags=("cited_target", "cited_ota", "seen_target", "seen_ota", "absent")):
    """Share of calls with each flag, per group, with Wilson 95% CI."""
    rows = []
    for key, g in df.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        for flag in flags:
            k, n = int(g[flag].sum()), len(g)
            lo, hi = wilson(k, n)
            rows.append({**dict(zip(by, key)), "metric": flag, "calls": n, "count": k,
                         "share": k / n, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


def url_category_share(df, by, label="cited"):
    """Share of URLs by category (total URL counts, not per call)."""
    cols = [f"{label}_{c}" for c in CATEGORIES]
    g = df.groupby(by)[cols].sum()
    totals = g.sum(axis=1)
    out = g.div(totals.where(totals > 0), axis=0).reset_index()
    out = out.melt(id_vars=by, var_name="category", value_name="share")
    out["category"] = out["category"].str.replace(f"{label}_", "", regex=False)
    out["urls"] = out.apply(lambda r: int(totals.loc[tuple(r[b] for b in by) if len(by) > 1 else r[by[0]]]), axis=1)
    return out


def primary_source_share(df, by):
    t = df.groupby(by + ["primary_source"]).size().rename("calls").reset_index()
    t["share"] = t["calls"] / t.groupby(by)["calls"].transform("sum")
    return t


def compare_airlines(df, flag="cited_ota", base="alaska"):
    """Core test: share of calls with the flag, base airline vs each other airline (all providers + per provider)."""
    rows = []
    for scope, sub in [("all", df)] + [(p, df[df.provider == p]) for p in sorted(df.provider.unique())]:
        a = sub[sub.airline_target == base]
        for other in sorted(set(sub.airline_target) - {base}):
            b = sub[sub.airline_target == other]
            k1, n1, k2, n2 = int(a[flag].sum()), len(a), int(b[flag].sum()), len(b)
            z, p = two_prop_ztest(k1, n1, k2, n2)
            rows.append({"provider": scope, "metric": flag, "airline_a": base, "airline_b": other,
                         "share_a": k1 / n1 if n1 else float("nan"), "n_a": n1,
                         "share_b": k2 / n2 if n2 else float("nan"), "n_b": n2,
                         "diff": (k1 / n1 - k2 / n2) if n1 and n2 else float("nan"), "z": z, "p_value": p})
    return pd.DataFrame(rows)


def top_domains(rows, cfg, n=15, which="cited_urls"):
    c = Counter()
    for r in rows:
        if r.get("error"):
            continue
        for u in r.get(which, []):
            d, cat = classify_url(u, r["airline_target"], cfg)
            if d:
                c[(d, cat)] += 1
    return pd.DataFrame([{"domain": d, "category": cat, "count": k} for (d, cat), k in c.most_common(n)])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--results", default=str(ROOT / "data" / "results.jsonl"))
    args = ap.parse_args(argv)
    cfg = load_domains()
    rows = load_rows(args.results, args.include_tests)
    df = build_frame(rows, cfg)
    if df.empty:
        print("No successful non-test rows yet.")
        return 0
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.float_format", "{:.2f}".format)
    print(f"{len(df)} successful calls from {df.run_number.nunique()} run(s), "
          f"{len(rows) - len(df)} failed.\n")
    by = ["airline_target", "provider"]
    shares = share_table(df, by)
    print("Share of calls by airline x provider (cited_* = in the answer, seen_* = anywhere in search results):")
    print(shares.pivot_table(index=by, columns="metric", values="share"), "\n")
    print("Share of cited URLs by category:")
    print(url_category_share(df, by).pivot_table(index=by, columns="category", values="share"), "\n")
    for flag in ("cited_ota", "seen_ota"):
        print(f"OTA/aggregator share ({flag}): Alaska vs others, two-proportion z-test")
        print(compare_airlines(df, flag).drop(columns="metric").to_string(index=False), "\n")
    print("Agreement: mean share of self-reported domains found in cited/seen URLs:",
          round(df["selfreport_in_used"].dropna().mean(), 2))
    out = ROOT / "data"
    pd.concat([share_table(df, by + [d]).assign(dimension=d).rename(columns={d: "level"}) for d in DIMENSIONS] +
              [shares.assign(dimension="overall", level="all")]).to_csv(out / "summary.csv", index=False)
    top_domains(rows, cfg, 50).to_csv(out / "domains.csv", index=False)
    print("\nWrote data/summary.csv and data/domains.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
