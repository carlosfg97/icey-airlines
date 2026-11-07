"""Generate the dashboard's PNG assets (flight-tracker style banner, route maps, app icon).

  python scripts/make_assets.py

Stylised on purpose: airports are plotted on a plain lon/lat grid with curved arcs, no coastline data.
Run it again if config/routes.yaml changes. Needs matplotlib + pyyaml.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
NAVY, NAVY_DEEP, ICE, GLOW, AMBER = "#0b2a45", "#06182a", "#a9d4f5", "#e8f4ff", "#ffb74d"
# (lat, lon)
AIRPORTS = {
    "SEA": (47.45, -122.31), "ANC": (61.17, -150.0), "LAX": (33.94, -118.41), "SFO": (37.62, -122.38),
    "LAS": (36.08, -115.15), "PHX": (33.43, -112.01), "SAN": (32.73, -117.19), "FAI": (64.82, -147.86),
    "JNU": (58.35, -134.58), "HNL": (21.32, -157.92), "PDX": (45.59, -122.60), "ATL": (33.64, -84.43),
    "MCO": (28.43, -81.31), "FLL": (26.07, -80.15), "TPA": (27.98, -82.53), "PBI": (26.68, -80.10),
    "MIA": (25.79, -80.29), "LGA": (40.78, -73.87), "BOS": (42.36, -71.01), "DCA": (38.85, -77.04),
    "JFK": (40.64, -73.78), "DEN": (39.86, -104.67), "DAL": (32.85, -96.85), "HOU": (29.65, -95.28),
    "MDW": (41.79, -87.75), "BWI": (39.18, -76.67),
}
HUBS = {"alaska": ["SEA"], "delta": ["ATL", "JFK"], "southwest": ["DEN", "LAS", "DAL", "BWI"]}
TITLES = {"alaska": "ALASKA  ·  SEA hub", "delta": "DELTA  ·  ATL hub", "southwest": "SOUTHWEST  ·  point to point"}


def load_routes():
    return yaml.safe_load(open(ROOT / "config" / "routes.yaml"))["routes"]


def sky(ax, w, h):
    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    cmap = LinearSegmentedColormap.from_list("sky", [NAVY_DEEP, NAVY, "#12426b"])
    ax.imshow(grad, extent=[0, w, 0, h], origin="upper", aspect="auto", cmap=cmap, zorder=0)
    rng = np.random.default_rng(7)
    ax.scatter(rng.uniform(0, w, 70), rng.uniform(0, h, 70), s=rng.uniform(0.5, 3, 70), c="white", alpha=0.25, zorder=1)


def arc(ax, p, q, color, lw=1.4, alpha=0.8, lift=0.22):
    (x1, y1), (x2, y2) = p, q
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dist = np.hypot(x2 - x1, y2 - y1)
    cx, cy = mx, my + lift * dist
    t = np.linspace(0, 1, 80)
    xs = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t ** 2 * x2
    ys = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t ** 2 * y2
    ax.plot(xs, ys, color=color, lw=lw * 3.2, alpha=alpha * 0.12, solid_capstyle="round", zorder=2)  # glow
    ax.plot(xs, ys, color=color, lw=lw, alpha=alpha, solid_capstyle="round", zorder=3)
    k = 55  # tiny plane near the arc's far end
    ang = np.degrees(np.arctan2(ys[k + 1] - ys[k], xs[k + 1] - xs[k]))
    ax.text(xs[k], ys[k], "✈", color=GLOW, fontsize=9 * lw, ha="center", va="center", rotation=ang - 45,
            alpha=min(1, alpha + 0.15), zorder=5)


def project(lat, lon, box, pad):
    (x0, x1, y0, y1), (lon0, lon1, lat0, lat1) = box, pad
    return x0 + (lon - lon0) / (lon1 - lon0) * (x1 - x0), y0 + (lat - lat0) / (lat1 - lat0) * (y1 - y0)


# label offsets (dx, dy in px) for crowded airports; default is just below the dot (hubs: above-left)
LABEL = {"SEA": (-22, 14), "PDX": (22, -10), "SFO": (-24, -6), "LAX": (-24, -14), "SAN": (20, -18), "LAS": (-4, 16),
         "PHX": (0, -18), "FLL": (24, -4), "MIA": (24, -20), "PBI": (26, 6), "MCO": (-24, -4), "TPA": (-22, -10),
         "ATL": (-20, 14), "LGA": (-6, 16), "JFK": (28, -14), "DCA": (-24, -8), "BOS": (0, 16), "BWI": (-4, 16),
         "DEN": (0, 16), "DAL": (0, 16), "FAI": (0, 16), "ANC": (-8, -18), "JNU": (0, -18)}


def dots(ax, codes, pts, hubs, fs):
    for c in codes:
        x, y = pts[c]
        hub = c in hubs
        ax.scatter([x], [y], s=64 if hub else 26, c=AMBER if hub else GLOW, zorder=6, edgecolors=NAVY, linewidths=1.2)
        dx, dy = LABEL.get(c, (0, 16 if hub else -18))
        ax.text(x + dx, y + dy, c, color=AMBER if hub else GLOW, fontsize=fs, fontweight="bold",
                ha="center", va="center", zorder=7, family="DejaVu Sans Mono")


def banner(routes):
    W, H = 1600, 520
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    sky(ax, W, H)
    box, pad = (60, W - 60, 70, H - 70), (-160, -68, 20, 66)
    pts = {c: project(la, lo, box, pad) for c, (la, lo) in AIRPORTS.items()}
    seen = set()
    for al, lst in routes.items():
        for a, b in lst:
            arc(ax, pts[a], pts[b], ICE, lw=1.1, alpha=0.7, lift=0.18)
            seen |= {a, b}
    dots(ax, sorted(seen), pts, {h for v in HUBS.values() for h in v}, 8)
    fig.savefig(OUT / "hero.png", facecolor=NAVY_DEEP); plt.close(fig)


def route_maps(routes):
    """One image per airline (readable on a phone), same flight-tracker look as the banner."""
    W, H = 1100, 720
    for al in ("alaska", "delta", "southwest"):
        fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
        sky(ax, W, H)
        codes = sorted({c for r in routes[al] for c in r})
        lats = [AIRPORTS[c][0] for c in codes]; lons = [AIRPORTS[c][1] for c in codes]
        box = (70, W - 70, 110, H - 110)
        pad = (min(lons) - 2, max(lons) + 2, min(lats) - 4, max(lats) + 4)
        pts = {c: project(*AIRPORTS[c], box, pad) for c in codes}
        for a_, b_ in routes[al]:
            arc(ax, pts[a_], pts[b_], ICE, lw=1.6, alpha=0.85, lift=0.16)
        dots(ax, codes, pts, set(HUBS[al]), 11)
        ax.text(W / 2, H - 46, TITLES[al], color=GLOW, fontsize=17, fontweight="bold", ha="center",
                family="DejaVu Sans Mono")
        fig.savefig(OUT / f"route_{al}.png", facecolor=NAVY_DEEP); plt.close(fig)


def icon():
    S = 256
    fig = plt.figure(figsize=(S / 100, S / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, S); ax.set_ylim(0, S); ax.axis("off")
    ax.add_patch(FancyBboxPatch((8, 8), S - 16, S - 16, boxstyle="round,pad=0,rounding_size=48", fc=NAVY, ec="none"))
    ax.text(S / 2, S / 2 - 6, "✈", color="white", fontsize=104, ha="center", va="center", rotation=-0)
    fig.savefig(OUT / "icon.png", transparent=True); plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    r = load_routes()
    banner(r); route_maps(r); icon()
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
