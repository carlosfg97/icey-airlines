"""Streamlit dashboard. Reads data/results.jsonl from the repo (Streamlit Community Cloud redeploys on push)."""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.analyze import (build_frame, compare_airlines, load_rows, share_table, top_domains,
                         url_category_share)
from src.classify import CATEGORIES, load_domains

RESULTS = Path(__file__).parent / "data" / "results.jsonl"
CAT_COLORS = {"airline_direct_target": "#2a6fdb", "airline_direct_other": "#8f98a3",
              "ota_aggregator": "#e8833a", "other": "#d5d9de"}
CAT_LABELS = {"airline_direct_target": "Target airline's own site", "airline_direct_other": "Other airline site",
              "ota_aggregator": "OTA / aggregator", "other": "Other (news, blogs, ...)"}

st.set_page_config(page_title="Agent channel experiment", layout="wide")
st.title("Do AI agents send flight shoppers to airline sites or to OTAs?")
st.caption("Claude and OpenAI with web search, asked for flight prices on Alaska, Delta and Southwest routes. "
           "API behaviour, not exactly what ChatGPT/Claude app users see. No bookings are made.")


@st.cache_data(ttl=300)
def load(include_tests):
    cfg = load_domains()
    rows = load_rows(RESULTS, include_tests)
    return rows, build_frame(rows, cfg), cfg


with st.sidebar:
    include_tests = st.checkbox("Include test runs", value=False)
    view = st.radio("URL set", ["cited", "seen"], format_func=lambda v: {
        "cited": "Cited in the answer", "seen": "Consulted (all search results)"}[v])
    st.caption("OpenAI cites few URLs but consults many, so compare both views.")

rows, df, cfg = load(include_tests)
if df.empty:
    st.info("No data yet. Results appear here after the first successful run.")
    st.stop()

providers = sorted(df.provider.unique())
with st.sidebar:
    chosen = st.multiselect("Providers", providers, default=providers)
df = df[df.provider.isin(chosen)]
rows = [r for r in rows if r["provider"] in chosen]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Successful calls", len(df))
c2.metric("Runs", df.run_number.nunique())
c3.metric("Failed calls", sum(1 for r in rows if r.get("error")))
c4.metric("Last run (UTC)", str(df.timestamp_utc.max())[:16].replace("T", " "))

color = alt.Color("category:N", title=None, sort=CATEGORIES,
                  scale=alt.Scale(domain=CATEGORIES, range=[CAT_COLORS[c] for c in CATEGORIES]),
                  legend=alt.Legend(labelExpr="{'airline_direct_target':'Target airline site',"
                                              "'airline_direct_other':'Other airline site',"
                                              "'ota_aggregator':'OTA / aggregator','other':'Other'}[datum.label]"))


def stacked(data, x, **kw):
    return (alt.Chart(data).mark_bar().encode(
        x=alt.X(f"{x}:N", title=None, sort=kw.get("sort")),
        y=alt.Y("share:Q", title="Share of URLs", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        color=color, order=alt.Order("category:N", sort="ascending"),
        tooltip=["category", alt.Tooltip("share:Q", format=".0%"), "urls"]))


st.subheader("1. Where do the URLs come from? (airline × model)")
d1 = url_category_share(df, ["airline_target", "provider"], view)
d1["group"] = d1["airline_target"] + " / " + d1["provider"]
st.altair_chart(stacked(d1, "group").properties(height=320), width="stretch")

st.subheader("2. By booking window and fare type")
col_a, col_b = st.columns(2)
for col, dim, order in ((col_a, "booking_window", ["next_week", "next_month", "holiday"]),
                        (col_b, "fare_type", ["basic_economy", "main_economy", "first_premium"])):
    d = url_category_share(df, ["airline_target", dim], view)
    chart = stacked(d, dim, sort=order).facet(column=alt.Column("airline_target:N", title=None)).properties(
        title=dim.replace("_", " "))
    col.altair_chart(chart, width="content")

st.subheader("3. Top 15 cited domains")
which = "cited_urls" if view == "cited" else "result_urls"
td = top_domains(rows, cfg, 15, which)
if not td.empty:
    st.altair_chart(alt.Chart(td).mark_bar().encode(
        y=alt.Y("domain:N", sort="-x", title=None), x=alt.X("count:Q", title="URLs"),
        color=alt.Color("category:N", scale=alt.Scale(domain=CATEGORIES, range=[CAT_COLORS[c] for c in CATEGORIES]),
                        title=None)).properties(height=380), width="stretch")

st.subheader("Core comparison: share of calls that include an OTA/aggregator")
flag = f"{view}_ota"
comp = compare_airlines(df, flag)
st.dataframe(comp.drop(columns="metric").rename(columns={"airline_a": "airline A", "airline_b": "airline B"})
             .style.format({"share_a": "{:.0%}", "share_b": "{:.0%}", "diff": "{:+.0%}", "z": "{:.2f}",
                            "p_value": "{:.3f}"}), hide_index=True, width="stretch")
st.caption("Two-proportion z-test, Alaska (A) vs. each other airline (B). Small samples early on: read p-values with care. "
           "Delta and Southwest serve different markets than Alaska, so differences can reflect routes, not only the airline.")

st.subheader("Share of calls by airline × model (95% Wilson CI)")
sh = share_table(df, ["airline_target", "provider"], flags=(f"{view}_target", f"{view}_ota", "absent"))
st.dataframe(sh.style.format({"share": "{:.0%}", "ci_low": "{:.0%}", "ci_high": "{:.0%}"}),
             hide_index=True, width="stretch")
st.caption("'absent' = the answer never mentions the target airline (text heuristic, approximate).")

st.subheader("Sample responses")
sample = [r for r in rows if not r.get("error")][-30:][::-1]
tbl = pd.DataFrame([{"time": r["timestamp_utc"][:16], "provider": r["provider"], "airline": r["airline_target"],
                     "route": f"{r['origin']}→{r['destination']}", "fare": r["fare_type"], "window": r["booking_window"],
                     "cited": ", ".join(sorted({u.split('/')[2].removeprefix('www.') for u in r["cited_urls"] if "//" in u})),
                     "response": (r.get("response_text") or "")[:400]} for r in sample])
st.dataframe(tbl, hide_index=True, width="stretch")
