"""Streamlit dashboard. Reads data/results.jsonl from the repo (Streamlit Community Cloud redeploys on push).

Look: a flight-deck theme (navy banner, boarding-pass stat tiles, departures-board tables). Colors are
inspired by Alaska Airlines' deep blue; this is independent research, not an official or affiliated site.
Chart colors were validated with the dataviz skill's palette validator (light mode, white surface).
"""
import base64
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

from src.analyze import MIN_BATCHES, build_frame, compare_airlines_clustered, load_rows, url_category_share
from src.classify import CATEGORIES, classify_url, load_domains

ROOT = Path(__file__).parent
RESULTS = ROOT / "data" / "results.jsonl"
ASSETS = ROOT / "assets"

# ---- design tokens ---------------------------------------------------------------------------------
INK, INK2, MUTED = "#0d2238", "#4a5a6a", "#6b7a89"
NAVY, SURFACE, PAGE, HAIR = "#0b2a45", "#ffffff", "#f3f6f9", "#e3e8ee"
CAT = {"airline_direct_target": "#1768ad", "airline_direct_other": "#7d8b9a",
       "ota_aggregator": "#eb6834", "ai_travel_agent": "#a3195b", "other": "#c9d2db"}
CAT_LABEL = {"airline_direct_target": "Target airline's own site", "airline_direct_other": "Other airline's site",
             "ota_aggregator": "OTA / aggregator", "ai_travel_agent": "AI travel agent (helloaxel)",
             "other": "Other (news, blogs, ...)"}
CAT_SHORT = {"airline_direct_target": "OWN SITE", "airline_direct_other": "OTHER AIRLINE",
             "ota_aggregator": "OTA", "ai_travel_agent": "AI AGENT", "other": "OTHER"}
OTA_RAMP = ["#fdeee6", "#f9cdb6", "#f2a07a", "#eb6834", "#b8441a"]  # one-hue sequential for the heatmap
AIRLINES = {"alaska": ("AS", "Alaska Airlines"), "delta": ("DL", "Delta Air Lines"),
            "southwest": ("WN", "Southwest Airlines")}
WINDOWS = ["next_week", "next_month", "holiday"]
FARES = ["basic_economy", "main_economy", "first_premium"]
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

st.set_page_config(page_title="Agent Channel Watch", page_icon=Image.open(ASSETS / "icon.png"), layout="wide",
                   initial_sidebar_state="collapsed")


@st.cache_resource
def b64(name):
    return base64.b64encode((ASSETS / name).read_bytes()).decode()


def html_block(s):
    """st.markdown treats 4-space-indented lines as code, so flatten the HTML first."""
    st.markdown(" ".join(line.strip() for line in s.splitlines()), unsafe_allow_html=True)


html_block(f"""
<style>
:root {{ --ink:{INK}; --ink2:{INK2}; --muted:{MUTED}; --navy:{NAVY}; --surface:{SURFACE}; --page:{PAGE};
  --hair:{HAIR}; --own:{CAT['airline_direct_target']}; --ota:{CAT['ota_aggregator']}; --ai:{CAT['ai_travel_agent']}; --amber:#ffb74d; }}
.block-container {{ padding-top: 3.4rem; max-width: 1180px; }}
html, body, [class*="css"], .stMarkdown {{ font-family: {FONT}; }}
h2, h3 {{ color: var(--ink); letter-spacing: -0.01em; }}
.hero {{ position: relative; border-radius: 18px; overflow: hidden; color: #fff; min-height: 250px;
  background: #06182a url(data:image/png;base64,{b64('hero.png')}) center/cover no-repeat; margin-bottom: 1.1rem; }}
.hero::before {{ content:""; position:absolute; inset:0;
  background: linear-gradient(90deg, rgba(6,24,42,.94) 0%, rgba(6,24,42,.78) 46%, rgba(6,24,42,.15) 100%); }}
.hero-in {{ position: relative; padding: 28px 30px 26px; max-width: 760px; }}
.kicker {{ font: 600 12px {MONO}; letter-spacing: .18em; color: var(--amber); text-transform: uppercase; }}
.hero h1 {{ font-size: clamp(26px, 4.4vw, 42px); line-height: 1.08; margin: 10px 0 10px; font-weight: 750;
  letter-spacing: -0.02em; color:#fff; padding:0; }}
.hero p {{ color: #cfe3f5; font-size: 15px; margin: 0 0 16px; max-width: 620px; }}
.pill {{ display:inline-block; font: 600 12px {MONO}; padding: 5px 10px; border-radius: 999px;
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22); margin: 0 6px 6px 0; color:#e8f4ff; }}
.pill b {{ color: var(--amber); }}
.kpis {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 4px 0 18px; }}
.kpi {{ background: var(--surface); border:1px solid var(--hair); border-radius: 14px; padding: 12px 16px; }}
.kpi .l {{ font: 600 11px {MONO}; letter-spacing:.14em; color: var(--muted); text-transform: uppercase; }}
.kpi .v {{ font-size: 28px; font-weight: 750; color: var(--ink); line-height: 1.15; }}
.bps {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 6px 0 8px; }}
.bp {{ display:flex; background: var(--surface); border:1px solid var(--hair); border-radius: 16px; overflow:hidden;
  box-shadow: 0 1px 2px rgba(11,42,69,.05); }}
.bp-main {{ flex: 1; padding: 14px 16px 14px; min-width: 0; }}
.bp-top {{ display:flex; align-items:baseline; gap:10px; margin-bottom: 10px; }}
.bp-code {{ font: 800 22px {MONO}; color: var(--navy); background: #e6edf4; padding: 2px 8px; border-radius: 8px; }}
.bp-name {{ font-weight: 650; color: var(--ink); }}
.bp-row {{ margin-bottom: 9px; }}
.bp-l {{ font: 600 10.5px {MONO}; letter-spacing:.12em; color: var(--muted); text-transform: uppercase; }}
.bp-h {{ font-size: 34px; font-weight: 780; line-height: 1.05; color: var(--ink); }}
.bp-h.ota {{ color: #b8441a; }} .bp-h.own {{ color: #11588f; }} .bp-h.ai {{ color: #a3195b; }}
.bp-track {{ height: 6px; border-radius: 6px; background: #e6edf4; margin-top: 4px; overflow: hidden; }}
.bp-track i {{ display:block; height:100%; border-radius: 6px; }}
.bp-stub {{ width: 92px; border-left: 2px dashed var(--hair); background: #f7fafc; padding: 14px 8px; text-align:center;
  display:flex; flex-direction:column; justify-content:center; gap: 8px; }}
.bp-stub .n {{ font: 800 20px {MONO}; color: var(--navy); }}
.bp-stub .s {{ font: 600 9.5px {MONO}; letter-spacing:.1em; color: var(--muted); text-transform: uppercase; }}
.card {{ background: var(--surface); border:1px solid var(--hair); border-radius: 14px; padding: 14px 18px; margin: 8px 0; }}
.card p {{ margin: 0; color: var(--ink2); font-size: 14.5px; }}
.card b {{ color: var(--ink); }}
.board {{ background: #06182a; border-radius: 14px; padding: 10px 6px; overflow-x: auto; }}
.board table {{ border-collapse: collapse; width: 100%; font: 500 13px {MONO}; color: #ffe0a3; }}
.board th {{ text-align:left; font-weight: 600; color: #7fa6c8; font-size: 11px; letter-spacing:.14em; padding: 6px 12px;
  border-bottom: 1px solid rgba(169,212,245,.2); white-space: nowrap; }}
.board td {{ padding: 7px 12px; border-bottom: 1px solid rgba(169,212,245,.08); white-space: nowrap; }}
.board td.dim {{ color: #a9d4f5; }}
.tag {{ display:inline-block; padding: 1px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; letter-spacing:.06em; }}
.legend {{ display:flex; flex-wrap:wrap; gap: 6px 16px; margin: 2px 0 6px; font-size: 13px; color: var(--ink2); }}
.lg i {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:6px; vertical-align:-1px; }}
.foot {{ color: var(--muted); font-size: 12.5px; margin: 22px 0 6px; line-height: 1.5; }}
@media (max-width: 760px) {{
  .hm {{ display: none; }}
  .kpis {{ grid-template-columns: repeat(2, 1fr); }} .bps {{ grid-template-columns: 1fr; }}
  .hero-in {{ padding: 22px 18px; }} .bp-stub {{ width: 78px; }}
}}
</style>
""")


# ---- data ----------------------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load(include_tests, split_models=False, schema=4):
    # `schema` is part of the cache key: bump it whenever build_frame gains or changes columns, otherwise
    # Streamlit Cloud can keep serving a frame cached by the previous version of src/analyze.py.
    cfg = load_domains()
    rows = load_rows(RESULTS, include_tests)
    df = build_frame(rows, cfg, split_models=split_models)
    if "prompt_variant" not in df.columns:  # empty frame, or rows written before the column existed
        df["prompt_variant"] = "base"
    if not df.empty:
        # Disintermediation without an alternative: the answer links an OTA but not the airline's own site.
        # Claude links ~6 URLs per answer, so "links any OTA" is near 90% for every airline; this one discriminates.
        for v in ("cited", "seen"):
            df[f"{v}_ota_only"] = df[f"{v}_ota"] & ~df[f"{v}_target"]
    return rows, df, cfg


ET = ZoneInfo("America/New_York")


def to_et(ts, fmt):
    """ISO UTC timestamp from the data -> Eastern Time (EST/EDT handled by the tz database)."""
    return datetime.fromisoformat(ts).astimezone(ET).strftime(fmt).replace(" 0", " ").lstrip("0")


def provider_label(p):
    kind, _, model = p.partition(":")
    base = {"anthropic": "Claude", "openai": "OpenAI"}.get(kind, kind)
    if not model:
        return base
    short = model.split("-")[-1] if model.startswith("gpt") else model.replace("claude-", "")
    return f"{base} {short}"


def style(chart):
    return (chart.configure(font=FONT, background=SURFACE)
            .configure_view(stroke=None)
            .configure_axis(gridColor=HAIR, domainColor=HAIR, tickColor=HAIR, labelColor=MUTED, titleColor=INK2,
                            labelFontSize=12)
            .configure_legend(labelColor=INK2, labelFontSize=12, symbolType="square", symbolSize=110, orient="top",
                              padding=4)
            .configure_header(labelColor=INK, labelFontSize=13, labelFontWeight=600))


LEGEND_EXPR = ("{'airline_direct_target':'Own site','airline_direct_other':'Other airline',"
               "'ota_aggregator':'OTA / aggregator','ai_travel_agent':'AI travel agent','other':'Other'}[datum.label]")
cat_color = alt.Color("category:N", title=None, sort=CATEGORIES,
                      scale=alt.Scale(domain=CATEGORIES, range=[CAT[c] for c in CATEGORIES]), legend=None)
LEGEND_NAMES = {"airline_direct_target": "Own site", "airline_direct_other": "Other airline",
                "ota_aggregator": "OTA / aggregator", "ai_travel_agent": "AI travel agent", "other": "Other"}


def legend_html():
    """Legend as HTML so it wraps on narrow screens instead of being clipped inside the chart."""
    items = "".join(f'<span class="lg"><i style="background:{CAT[c]}"></i>{LEGEND_NAMES[c]}</span>' for c in CATEGORIES)
    html_block(f'<div class="legend">{items}</div>')

# ---- filter row (one row above everything it scopes) --------------------------------------------------
f1, f4, f2, f3 = st.columns([1.5, 1.6, 2, 1.1])
with f3:
    include_tests = st.toggle("Include test runs", value=False)
    split = st.toggle("Split OpenAI", value=False,
                      help="OpenAI switched from gpt-6.1-sol to gpt-6-luna on Nov 7. They differ on how often they "
                           "link the airline's own site (e.g. Delta 50% vs 18%), so pooled OpenAI numbers mix both.")
rows, df, cfg = load(include_tests, split)

with f4:
    variant = st.segmented_control("Prompt", ["base", "named"], default="base", key="variant",
                                   format_func={"base": "Airline not named", "named": "Airline named"}.get) or "base"
df = df[df.prompt_variant == variant]
rows = [r for r in rows if (r.get("prompt_variant") or "base") == variant]

with f1:
    view = st.segmented_control("URL set", ["cited", "seen"], default="cited", key="view",
                                format_func={"cited": "Cited in the answer", "seen": "All consulted"}.get) or "cited"

if df.empty:
    html_block(f"""<div class="hero"><div class="hero-in"><div class="kicker">Flight deck</div>
      <h1>Waiting for the first departures</h1><p>No data yet. Results appear here after the first successful run.</p>
      </div></div>""")
    st.stop()

providers = sorted(df.provider.unique())
with f2:
    chosen = st.multiselect("Models", providers, default=providers, format_func=provider_label)
df = df[df.provider.isin(chosen)]
rows = [r for r in rows if f"{r['provider']}:{r['model']}" in chosen or r["provider"] in chosen]
if df.empty:
    st.info("Pick at least one model.")
    st.stop()
flag_ota, flag_own, flag_only, flag_ai = f"{view}_ota", f"{view}_target", f"{view}_ota_only", f"{view}_ai"
last = to_et(df.timestamp_utc.max(), "%b %d, %I:%M %p %Z")
first = to_et(df.timestamp_utc.min(), "%b %d")
n_fail = sum(1 for r in rows if r.get("error"))

# ---- hero + KPIs -------------------------------------------------------------------------------------
html_block(f"""
<div class="hero"><div class="hero-in">
  <div class="kicker">Flight deck · AI shopping agents</div>
  <h1>Do AI agents send flight shoppers to the airline, or to an OTA?</h1>
  <p>Claude and OpenAI, with web search, price the same trips on Alaska, Delta and Southwest in repeated batches,
  and we log which websites they actually point travelers to.</p>
  <span class="pill">AS · DL · WN</span><span class="pill">36 searches / batch</span>
  <span class="pill">from <b>{first}</b> to <b>{last}</b></span>
</div></div>
<div class="kpis">
  <div class="kpi"><div class="l">Answers logged</div><div class="v">{len(df):,}</div></div>
  <div class="kpi"><div class="l">Batches</div><div class="v">{df.run_number.nunique()}</div></div>
  <div class="kpi"><div class="l">Failed calls</div><div class="v">{n_fail}</div></div>
  <div class="kpi"><div class="l">Routes covered</div><div class="v">{df.route_id.nunique()}</div></div>
</div>
""")

# ---- boarding passes: one stat tile per airline -------------------------------------------------------
st.subheader("Boarding passes: who gets the click?")
L_OTA = "Answers linking an OTA" if view == "cited" else "Searches showing an OTA"
L_OWN = "Answers linking own site" if view == "cited" else "Searches showing own site"
L_ONLY = "OTA, no own-site link" if view == "cited" else "OTA shown, own site not"
L_AI = "Answers linking AI agent" if view == "cited" else "Searches showing AI agent"
tiles = []
for key, (code, name) in AIRLINES.items():
    g = df[df.airline_target == key]
    if g.empty:
        continue
    ota, own, only, ai = g[flag_ota].mean(), g[flag_own].mean(), g[flag_only].mean(), g[flag_ai].mean()
    tiles.append(f"""<div class="bp"><div class="bp-main">
      <div class="bp-top"><span class="bp-code">{code}</span><span class="bp-name">{name}</span></div>
      <div class="bp-row"><div class="bp-l">{L_OTA}</div><div class="bp-h ota">{ota:.0%}</div>
        <div class="bp-track"><i style="width:{ota:.0%};background:var(--ota)"></i></div></div>
      <div class="bp-row"><div class="bp-l">{L_OWN}</div><div class="bp-h own">{own:.0%}</div>
        <div class="bp-track"><i style="width:{own:.0%};background:var(--own)"></i></div></div>
      <div class="bp-row"><div class="bp-l">{L_ONLY}</div><div class="bp-h ota">{only:.0%}</div>
        <div class="bp-track"><i style="width:{only:.0%};background:var(--ota)"></i></div></div>
      <div class="bp-row"><div class="bp-l">{L_AI}</div><div class="bp-h ai">{ai:.0%}</div>
        <div class="bp-track"><i style="width:{ai:.0%};background:var(--ai)"></i></div></div>
    </div><div class="bp-stub"><div class="s">Answers</div><div class="n">{len(g)}</div></div></div>""")
html_block('<div class="bps">' + "".join(tiles) + "</div>")

comp = compare_airlines_clustered(df, flag_only)
what = "answers that link an OTA but not the airline's site" if view == "cited" else "searches that show an OTA but not the airline's site"
lines = []
for _, r in comp.iterrows():
    if pd.isna(r.p_value):
        verdict = f"only {r.batches} batch{'es' if r.batches != 1 else ''}, too few to test"
    else:
        verdict = (f"gap {r['diff'] * 100:+.0f} pts, 95% CI {r.ci_low * 100:+.0f} to {r.ci_high * 100:+.0f}, "
                   + ("distinguishable" if r.p_value < 0.05 else "not distinguishable"))
    lines.append(f"<b>{provider_label(r.provider)}</b> · {AIRLINES[r.airline_a][1].split()[0]} {r.share_a:.0%} vs "
                 f"{AIRLINES[r.airline_b][1].split()[0]} {r.share_b:.0%} ({verdict})")
if lines:
    html_block(f'<div class="card"><p>Share of {what}:<br>' + "<br>".join(lines) + "</p></div>")
st.caption(f"Tests are per model, with a bootstrap that resamples whole batches (calls in one batch share routes and "
           f"dates; at least {MIN_BATCHES} batches needed). The airlines fly different markets and each has only 10 "
           "routes, so gaps can reflect routes, not just the carrier.")

# ---- chart 1: URL mix --------------------------------------------------------------------------------
st.subheader("1 · Where do the links come from?")
pooled = [f"{provider_label(p)} = " + " + ".join(sorted(df.loc[df.provider == p, "model"].unique()))
          for p in providers if df.loc[df.provider == p, "model"].nunique() > 1]
st.caption("Own site = the airline the trip was about. AI travel agent = AI-native flight search built for agents (so far only helloaxel.com), shown apart from OTAs. Each bar is 100% of the links in that group."
           + (" Pooled models: " + "; ".join(pooled) + "." if pooled else ""))
legend_html()
d1 = url_category_share(df, ["airline_target", "provider"], view)
SHORT = {k: v[1].split()[0] for k, v in AIRLINES.items()}
d1["label"] = d1["airline_target"].map(SHORT) + " · " + d1["provider"].map(provider_label)
order = [SHORT[a] + " · " + provider_label(p) for a in AIRLINES for p in providers
         if ((df.airline_target == a) & (df.provider == p)).any()]
seg = []
for lab, sub in d1.groupby("label", sort=False):
    start = 0.0
    for c in CATEGORIES:
        v = sub.loc[sub.category == c, "share"]
        v = 0.0 if v.empty or pd.isna(v.iloc[0]) else float(v.iloc[0])
        seg.append({"label": lab, "category": c, "start": start, "end": start + v, "mid": start + v / 2,
                    "share": v, "pct": f"{v:.0%}", "urls": int(sub.urls.iloc[0])})
        start += v
seg = pd.DataFrame(seg)
yenc = alt.Y("label:N", sort=order, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=170))
bars = alt.Chart(seg).mark_bar(size=26, stroke=SURFACE, strokeWidth=2).encode(
    y=yenc, x=alt.X("start:Q", title=None, scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", tickCount=5)),
    x2="end:Q", color=cat_color,
    tooltip=[alt.Tooltip("label:N", title="Who"), alt.Tooltip("category:N", title="Category"),
             alt.Tooltip("share:Q", format=".0%", title="Share of URLs"), alt.Tooltip("urls:Q", title="URLs in total")])
txt = alt.Chart(seg).transform_filter("datum.share >= 0.09").mark_text(fontSize=11, fontWeight=700).encode(
    y=yenc, x="mid:Q", text="pct:N",
    color=alt.condition("datum.category == 'other'", alt.value(INK), alt.value("#ffffff")))
st.altair_chart(style((bars + txt).properties(height=max(120, 38 * len(order)))), width="stretch")
with st.expander("Show the numbers"):
    st.dataframe(d1.pivot_table(index="label", columns="category", values="share").reindex(order)
                 .style.format("{:.0%}"), width="stretch")

# ---- chart 2: heatmap --------------------------------------------------------------------------------
st.subheader("2 · Does the trip type change it?")
st.caption("Share linking an OTA, by how far ahead the trip is (a week, a month, or the Dec 23 holiday) and the fare, "
           "pooled across the selected models. Faded cells have fewer than 3 answers. Fare and route are not fully "
           "balanced, but the first-class effect also holds when compared within each route and model.")
hm = (df.groupby(["airline_target", "fare_type", "booking_window"])
      .agg(share=(flag_ota, "mean"), n=(flag_ota, "size")).reset_index())
hm["airline"] = hm["airline_target"].map(lambda a: AIRLINES[a][1])
hm["fare"] = hm["fare_type"].str.replace("_", " ")
hm["window"] = hm["booking_window"].map({"next_week": "+1 week", "next_month": "+1 month", "holiday": "holiday"})
wl, fl = ["+1 week", "+1 month", "holiday"], [f.replace("_", " ") for f in FARES]
base = alt.Chart(hm).encode(
    x=alt.X("window:N", sort=wl, title=None, axis=alt.Axis(orient="top", labelAngle=0, ticks=False, domain=False)),
    y=alt.Y("fare:N", sort=fl, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=100)))
rect = base.mark_rect(stroke=SURFACE, strokeWidth=3).encode(
    color=alt.Color("share:Q", title="OTA share", scale=alt.Scale(domain=[0, .25, .5, .75, 1], range=OTA_RAMP),
                    legend=alt.Legend(format="%", orient="bottom", gradientLength=160)),
    opacity=alt.condition("datum.n >= 3", alt.value(1), alt.value(0.45)),
    tooltip=[alt.Tooltip("airline:N"), alt.Tooltip("fare:N"), alt.Tooltip("window:N"),
             alt.Tooltip("share:Q", format=".0%", title="OTA share"), alt.Tooltip("n:Q", title="Answers")])
cell_txt = base.mark_text(fontSize=11, fontWeight=700).encode(
    text=alt.Text("share:Q", format=".0%"),
    color=alt.condition("datum.share > 0.62", alt.value("#ffffff"), alt.value(INK)))
heat = (rect + cell_txt).properties(width=240, height=96).facet(
    row=alt.Row("airline:N", title=None, sort=[AIRLINES[a][1] for a in AIRLINES],
                header=alt.Header(labelOrient="top", labelAngle=0, labelAlign="left", labelPadding=4,
                                  labelFontSize=14)), spacing=10)
st.altair_chart(style(heat), width="content")

# ---- route map ---------------------------------------------------------------------------------------
st.subheader("Where we are looking")
tabs = st.tabs([AIRLINES[a][1] for a in AIRLINES])
for tab, a in zip(tabs, AIRLINES):
    with tab:
        st.image(str(ASSETS / f"route_{a}.png"), width="stretch",
                 caption="Ten routes (stylised map, not to scale). Each batch: 3 routes, both directions.")

# ---- chart 3: domains --------------------------------------------------------------------------------
st.subheader("3 · The 15 most-cited websites" if view == "cited" else "3 · The 15 most-consulted websites")
legend_html()
which = "cited_urls" if view == "cited" else "result_urls"
cnt = {}
for r in rows:
    if r.get("error"):
        continue
    for u in r.get(which, []):
        d, c = classify_url(u, r["airline_target"], cfg)
        if d:
            cnt[(d, c)] = cnt.get((d, c), 0) + 1
cdf = pd.DataFrame([{"domain": d, "category": c, "count": n} for (d, c), n in cnt.items()])
if not cdf.empty:
    tot = cdf.groupby("domain")["count"].sum().sort_values(ascending=False).head(15)
    td, order3 = cdf[cdf.domain.isin(tot.index)], list(tot.index)
    tot_df = tot.reset_index().rename(columns={"count": "total"})
    ydom = alt.Y("domain:N", sort=order3, title=None, axis=alt.Axis(ticks=False, domain=False))
    bars3 = alt.Chart(td).mark_bar(size=16, stroke=SURFACE, strokeWidth=1).encode(
        y=ydom, x=alt.X("count:Q", title=None, axis=alt.Axis(tickMinStep=1)), color=cat_color,
        order=alt.Order("category:N"),
        tooltip=["domain", alt.Tooltip("category:N"), alt.Tooltip("count:Q", title="URLs")])
    lab3 = alt.Chart(tot_df).mark_text(align="left", dx=5, fontSize=11, color=INK2).encode(
        y=ydom, x="total:Q", text="total:Q")
    st.altair_chart(style((bars3 + lab3).properties(height=26 * len(tot))), width="stretch")
    st.caption("A site can appear in two colors: southwest.com is 'own site' for Southwest trips and 'other airline' "
               "when the trip was about another carrier. Counts are URLs, and Claude links about 3x as many per "
               "answer as OpenAI, so this list leans toward Claude's choices.")

# ---- departures boards ---------------------------------------------------------------------------------
st.subheader("Departures: the latest answers")
recent = [r for r in rows if not r.get("error")][-9:][::-1]
trs = []
for r in recent:
    urls = r.get("cited_urls") or []
    dom, cat = (classify_url(urls[0], r["airline_target"], cfg) if urls else (None, "other"))
    chip = (f'<span class="tag" style="background:{CAT[cat]};color:{"#0d2238" if cat == "other" else "#fff"}">'
            f"{CAT_SHORT[cat]}</span>") if urls else '<span class="dim">no link</span>'
    trs.append(f'<tr><td class="dim">{to_et(r["timestamp_utc"], "%I:%M %p")}</td>'
               f'<td>{AIRLINES[r["airline_target"]][0]}</td>'
               f'<td>{r["origin"]} → {r["destination"]}</td>'
               f'<td class="dim hm">{html.escape(provider_label(r["provider"]))}</td>'
               f'<td>{html.escape(dom or "—")}</td><td>{chip}</td></tr>')
html_block('<div class="board"><table><tr><th>TIME (ET)</th><th>FLT</th><th>ROUTE</th><th class="hm">MODEL</th><th>FIRST LINK</th>'
           '<th>TYPE</th></tr>' + "".join(trs) + "</table></div>")

with st.expander("Route board: all routes"):
    rb = (df.groupby(["airline_target", "route_id"]).agg(n=("run_number", "size"), ota=(flag_ota, "mean"),
                                                         own=(flag_own, "mean"),
                                                         only=(flag_only, "mean"), ai=(flag_ai, "mean")).reset_index())
    rb["o"] = rb["airline_target"].map(list(AIRLINES).index)
    rb = rb.sort_values(["o", "route_id"])
    rt = "".join(f'<tr><td>{AIRLINES[r.airline_target][0]}</td><td>{r.route_id.replace("-", " ⇄ ")}</td>'
                 f'<td class="dim">{r.n}</td><td>{r.ota:.0%}</td><td>{r.own:.0%}</td><td>{r.only:.0%}</td><td>{r.ai:.0%}</td></tr>' for r in rb.itertuples())
    html_block('<div class="board"><table><tr><th>FLT</th><th>ROUTE</th><th>ANSWERS</th><th>OTA</th><th>OWN SITE</th><th>OTA ONLY</th><th>AI AGENT</th></tr>'
               + rt + "</table></div>")

with st.expander("Sample responses (full text)"):
    sample = [r for r in rows if not r.get("error")][-30:][::-1]
    st.dataframe(pd.DataFrame([{"time (ET)": to_et(r["timestamp_utc"], "%b %d %I:%M %p"), "model": provider_label(r["provider"]),
                                "airline": r["airline_target"], "route": f"{r['origin']}→{r['destination']}",
                                "fare": r["fare_type"], "window": r["booking_window"],
                                "cited": ", ".join(sorted({u.split('/')[2].removeprefix('www.')
                                                           for u in r["cited_urls"] if "//" in u})),
                                "response": (r.get("response_text") or "")[:400]} for r in sample]),
                 hide_index=True, width="stretch")

with st.expander("How the experiment works"):
    st.image(str(ROOT / "docs" / "how-it-works.png"), width="stretch")

html_block("""<div class="foot">Independent research. Not affiliated with or endorsed by Alaska Airlines, Delta Air Lines
or Southwest Airlines; the blue palette is merely inspired by the industry. These are API results with web search,
not exactly what ChatGPT or Claude app users see. No bookings are made. Source:
<a href="https://github.com/carlosfg97/icey-airlines">github.com/carlosfg97/icey-airlines</a>.</div>""")
