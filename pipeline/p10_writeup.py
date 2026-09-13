"""Phase E2: the writeup, generated from stored results so no number is retyped.

Charts are inline SVG styled by the page's theme tokens, so they read in light
and dark and cannot drift from outputs/results. Writes docs/index.html, which
GitHub Pages serves as the project site.

Usage:  python -m pipeline.p10_writeup [--body-only PATH]
  --body-only writes a second copy without <html>/<head> wrappers, for hosts
  that supply their own document skeleton.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from line54 import config, figures, rdd
from pipeline.p07_estimate import RESULTS, load_sample

OUT_DIR = config.ROOT / "docs"
REPO_URL = "https://github.com/FireCloud24/london-catchment-line"
GRADE = {1: "Outstanding", 2: "Good", 3: "Requires improvement", 4: "Inadequate"}


# --- formatting ---------------------------------------------------------------

def e(s: object) -> str:
    return html.escape(str(s))


WJ = "⁠"  # word joiner: a line must never break between a sign and its number


def pct(v: float, dp: int = 1) -> str:
    return f"{'−' if v < 0 else '+'}{WJ}{abs(v):.{dp}f}%"


def gbp(v: float, k: bool = False) -> str:
    sign = ("−" if v < 0 else "+") + WJ
    if k:
        return f"{sign}£{abs(v) / 1000:,.1f}k"
    return f"{sign}£{abs(v):,.0f}"


def num(v: float, dp: int = 0) -> str:
    return f"{v:,.{dp}f}".replace("-", "−")


def pval(p: float) -> str:
    if p is None or pd.isna(p):
        return "–"
    return "<0.001" if p < 0.001 else f"{p:.3f}" if p < 0.01 else f"{p:.2f}"


class Lin:
    def __init__(self, d0: float, d1: float, r0: float, r1: float):
        self.d0, self.d1, self.r0, self.r1 = d0, d1, r0, r1

    def __call__(self, v):
        return self.r0 + (np.asarray(v, dtype=float) - self.d0) / (self.d1 - self.d0) * (self.r1 - self.r0)


def path(xs, ys) -> str:
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


# --- charts -------------------------------------------------------------------

def hero_interval(main: dict) -> str:
    lo, mid, hi = main["pct"][1], main["pct"][0], main["pct"][2]
    W, H, L, R = 720, 118, 20, 20
    x = Lin(-6, 10, L, W - R)
    ticks = "".join(
        f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="30" y2="78"/>'
        f'<text class="tick" x="{x(t):.1f}" y="98" text-anchor="middle">{pct(t, 0) if t else "0"}</text>'
        for t in (-5, 0, 5, 10)
    )
    # pounds is ordered like pct: (estimate, low, high).
    _, pl, ph = main["pounds"]
    return f"""<svg class="chart hero-svg" viewBox="0 0 {W} {H}" role="img"
  aria-label="95% interval from {pct(lo)} to {pct(hi)}, estimate {pct(mid)}, crossing zero">
  {ticks}
  <line class="zero" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="22" y2="84"/>
  <rect class="ci-bar" x="{x(lo):.1f}" y="46" width="{x(hi) - x(lo):.1f}" height="16" rx="2"/>
  <circle class="ci-point" cx="{x(mid):.1f}" cy="54" r="7"/>
  <text class="ci-label" x="{x(lo):.1f}" y="36" text-anchor="start">{pct(lo)} · {gbp(pl, True)}</text>
  <text class="ci-label" x="{x(hi):.1f}" y="36" text-anchor="end">{pct(hi)} · {gbp(ph, True)}</text>
  <text class="tick" x="{W - R}" y="116" text-anchor="end">premium for being inside the line, 95% interval</text>
</svg>"""


def headline_chart(df: pd.DataFrame, main: dict, h: float = config.MAIN_BANDWIDTH_M) -> str:
    w = df.loc[df["d_signed_m"].abs() < h].copy()
    w["_y"] = rdd.residualise_fe(w, "log_price", rdd.MAIN_FE)
    bins = rdd.binned_means(df, h, 25.0)
    fits = {}
    for inside in (False, True):
        grid = np.linspace(0.5, h, 50) if inside else np.linspace(-h, -0.5, 50)
        fits[inside] = (grid, *figures._side_fit(w, h, inside, grid))
    ys = np.concatenate([bins["mean"], *[np.concatenate([f[2], f[3]]) for f in fits.values()]])
    y_lo, y_hi = np.exp(ys.min()) * 0.985, np.exp(ys.max()) * 1.015
    W, H, L, R, T, B = 920, 470, 72, 24, 34, 58
    x = Lin(-h, h, L, W - R)
    y = Lin(np.log(y_lo), np.log(y_hi), H - B, T)
    step = 10_000
    yt = np.arange(np.ceil(y_lo / step) * step, y_hi, step)
    parts = []
    for v in yt:
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(np.log(v)):.1f}" y2="{y(np.log(v)):.1f}"/>'
                     f'<text class="tick" x="{L - 10}" y="{y(np.log(v)) + 4:.1f}" text-anchor="end">£{v / 1000:,.0f}k</text>')
    for v in range(-400, 401, 100):
        parts.append(f'<text class="tick" x="{x(v):.1f}" y="{H - B + 22}" text-anchor="middle">{num(v)}</text>')
    for inside in (False, True):
        grid, mean, lo, hi = fits[inside]
        cls = "in" if inside else "out"
        band = path(x(grid), y(hi)) + " L" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(x(grid)[::-1], y(lo)[::-1])) + " Z"
        parts.append(f'<path class="band {cls}" d="{band}"/><path class="fit {cls}" d="{path(x(grid), y(mean))}"/>')
    nmax = bins["n"].max()
    for r in bins.itertuples():
        cls = "in" if r.mid_m > 0 else "out"
        rad = 2.5 + 3.5 * np.sqrt(r.n / nmax)
        parts.append(f'<circle class="dot {cls}" cx="{x(r.mid_m):.1f}" cy="{y(r.mean):.1f}" r="{rad:.1f}"/>')
    parts.append(f'<line class="boundary" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{T - 12}" y2="{H - B}"/>')
    parts.append(f'<text class="side out" x="{x(-10):.1f}" y="{T - 16}" text-anchor="end">← outside the catchment</text>')
    parts.append(f'<text class="side in" x="{x(10):.1f}" y="{T - 16}" text-anchor="start">inside →</text>')
    parts.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">distance to the boundary, metres (British National Grid)</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Binned mean sale price by distance to the '
            f'catchment boundary, with a fitted line on each side">{"".join(parts)}</svg>')


def forest_chart(per: pd.DataFrame, main: dict, names: dict) -> str:
    p = per.dropna(subset=["pct"]).sort_values("pct", ascending=False).reset_index(drop=True)
    row, T, B, L, R, W = 30, 16, 50, 250, 30, 920
    H = T + row * len(p) + B
    x = Lin(-25, 50, L, W - R)
    parts = []
    for v in range(-20, 51, 10):
        parts.append(f'<line class="grid" x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T}" y2="{H - B}"/>'
                     f'<text class="tick" x="{x(v):.1f}" y="{H - B + 20}" text-anchor="middle">{pct(v, 0) if v else "0"}</text>')
    pl, ph = main["pct"][1], main["pct"][2]
    parts.append(f'<rect class="pooled-band" x="{x(pl):.1f}" y="{T}" width="{x(ph) - x(pl):.1f}" height="{H - B - T}"/>')
    parts.append(f'<line class="zero" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{T}" y2="{H - B}"/>')
    for i, r in p.iterrows():
        cy = T + row * i + row / 2
        a, b = max(r.pct_low, -25), min(r.pct_high, 50)
        parts.append(f'<text class="label" x="{L - 14}" y="{cy + 4:.1f}" text-anchor="end">{e(names.get(r.boundary_id, r.boundary_id))}</text>'
                     f'<line class="whisker" x1="{x(a):.1f}" x2="{x(b):.1f}" y1="{cy:.1f}" y2="{cy:.1f}"/>'
                     f'<circle class="dot in" cx="{x(r.pct):.1f}" cy="{cy:.1f}" r="4.5"/>')
    parts.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">premium, % with 95% interval · shaded band: pooled estimate</text>')
    return f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Premium estimated at each boundary separately">{"".join(parts)}</svg>'


def bandwidth_chart(sweep: pd.DataFrame) -> str:
    s = sweep.dropna(subset=["tau"])
    bw = s["bandwidth_m"].to_numpy()
    mid, lo, hi = (np.expm1(s[c].to_numpy()) * 100 for c in ("tau", "ci_low", "ci_high"))
    W, H, L, R, T, B = 920, 330, 60, 24, 20, 56
    x = Lin(100, 750, L, W - R)
    y = Lin(-6, 16, H - B, T)
    parts = []
    for v in range(-5, 16, 5):
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="tick" x="{L - 10}" y="{y(v) + 4:.1f}" text-anchor="end">{pct(v, 0) if v else "0"}</text>')
    for v in range(100, 751, 100):
        parts.append(f'<text class="tick" x="{x(v):.1f}" y="{H - B + 20}" text-anchor="middle">{v} m</text>')
    band = path(x(bw), y(hi)) + " L" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(x(bw)[::-1], y(lo)[::-1])) + " Z"
    parts.append(f'<path class="band in" d="{band}"/><line class="zero" x1="{L}" x2="{W - R}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    parts.append(f'<line class="prereg" x1="{x(400):.1f}" x2="{x(400):.1f}" y1="{T}" y2="{H - B}"/>'
                 f'<text class="tick" x="{x(400) + 6:.1f}" y="{T + 12}">pre-registered 400 m</text>')
    parts.append(f'<path class="fit in" d="{path(x(bw), y(mid))}"/>')
    parts += [f'<circle class="dot in" cx="{a:.1f}" cy="{b:.1f}" r="3.5"/>' for a, b in zip(x(bw), y(mid))]
    parts.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">bandwidth: sales within this distance of the line, either side</text>')
    return f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Estimate against bandwidth">{"".join(parts)}</svg>'


def density_chart(df: pd.DataFrame, h: float = config.MAX_BANDWIDTH_M, bin_m: float = 10.0) -> str:
    d = df.loc[df["d_signed_m"].abs() < h, "d_signed_m"].to_numpy()
    edges = np.arange(-h, h + bin_m, bin_m)
    counts, _ = np.histogram(d, bins=edges)
    W, H, L, R, T, B = 920, 290, 60, 24, 16, 52
    x = Lin(-h, h, L, W - R)
    top = int(np.ceil(counts.max() / 200) * 200)
    y = Lin(0, top, H - B, T)
    parts = []
    for v in range(0, top + 1, 200):
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="tick" x="{L - 10}" y="{y(v) + 4:.1f}" text-anchor="end">{num(v)}</text>')
    for v in range(-750, 751, 250):
        parts.append(f'<text class="tick" x="{x(v):.1f}" y="{H - B + 20}" text-anchor="middle">{num(v)}</text>')
    for a, c in zip(edges[:-1], counts):
        cls = "in" if a >= 0 else "out"
        parts.append(f'<rect class="bar {cls}" x="{x(a) + 0.4:.1f}" y="{y(c):.1f}" width="{x(a + bin_m) - x(a) - 0.8:.1f}" height="{y(0) - y(c):.1f}"/>')
    parts.append(f'<line class="boundary" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{T}" y2="{H - B}"/>')
    parts.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">distance to the boundary, metres · sales per 10 m band</text>')
    return f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Number of sales by distance to the boundary">{"".join(parts)}</svg>'


# --- tables -------------------------------------------------------------------

def chip(kind: str) -> str:
    label = {"holds": "holds", "flag": "flag", "mixed": "no clear pattern", "context": "context"}[kind]
    return f'<span class="chip {kind}">{label}</span>'


def robustness_rows(rob: pd.DataFrame) -> tuple[str, dict]:
    def ci_excludes_zero(r) -> bool:
        return (r.ci_low > 0) or (r.ci_high < 0)

    rows, facts = [], {}

    def add(test: str, spec: str, est: str, ci: str, p: str, kind: str):
        rows.append(f"<tr><td>{e(test)}</td><td>{e(spec)}</td><td class='n'>{est}</td><td class='n'>{ci}</td>"
                    f"<td class='n'>{p}</td><td>{chip(kind)}</td></tr>")

    def as_pct(r):
        return pct(np.expm1(r.tau) * 100), f"{pct(np.expm1(r.ci_low) * 100)} to {pct(np.expm1(r.ci_high) * 100)}"

    for r in rob[rob.test == "R1 placebo cut-off"].itertuples():
        side = "inside" if "+" in r.spec.split(",")[0] else "outside"
        est, ci = as_pct(r)
        add("Placebo line", f"fake boundary {r.spec.split(',')[0].replace('d = ', '')} ({side} sales only)", est, ci, pval(r.p_value),
            "flag" if ci_excludes_zero(r) else "holds")
    units = {"share flat": ("pp", 100), "share detached": ("pp", 100), "share leasehold": ("pp", 100), "share new build": ("pp", 100)}
    for r in rob[rob.test == "R2 covariate balance"].itertuples():
        key = next((k for k in units if r.spec.startswith(k)), None)
        if key:
            s = lambda v: f"{'−' if v < 0 else '+'}{abs(v) * 100:.1f} pp"
            est, ci, label = s(r.tau), f"{s(r.ci_low)} to {s(r.ci_high)}", key
        elif r.spec.startswith("LSOA IMD"):
            s = lambda v: f"{'−' if v < 0 else '+'}{abs(v):,.0f}"
            est, ci, label = s(r.tau), f"{s(r.ci_low)} to {s(r.ci_high)}", "deprivation rank of the area (IMD 2019)"
        else:
            s = lambda v: f"{'−' if v < 0 else '+'}{abs(v):,.0f} m"
            est, ci, label = s(r.tau), f"{s(r.ci_low)} to {s(r.ci_high)}", "distance to nearest station"
        if r.spec.startswith("share flat"):
            facts["flat"] = (r.tau * 100, r.p_value)
        add("Balance", label, est, ci, pval(r.p_value), "flag" if ci_excludes_zero(r) else "holds")
    for r in rob[rob.test == "R3 density (McCrary)"].itertuples():
        add("Bunching at the line", f"McCrary density test, {r.spec}", f"{r.tau:+.3f}".replace("-", "−"),
            f"{r.ci_low:+.3f} to {r.ci_high:+.3f}".replace("-", "−"), pval(r.p_value), "flag" if ci_excludes_zero(r) else "holds")
        if r.spec == "sales":
            facts["mccrary_p"] = r.p_value
    for r in rob[rob.test == "R4 donut"].itertuples():
        est, ci = as_pct(r)
        add("Donut", r.spec.replace("drop", "drop sales within").replace("|d| < ", ""), est, ci, pval(r.p_value), "flag" if ci_excludes_zero(r) else "holds")
    timing = rob[rob.test == "R5 timing"].dropna(subset=["tau"])
    add("Ofsted grade changes", f"premium before vs after {len(timing) // 2} changes (Appendix A6)", "–", "–", "–",
        "flag" if timing.apply(ci_excludes_zero, axis=1).any() else "mixed")
    for r in rob[rob.test == "R6 measurement error"].itertuples():
        band = re.search(r"< (\d+) m", r.spec).group(1)
        add("Measurement error", f"sales within {band} m of the line", f"{r.tau * 100:.1f}%", "–", "–", "context")
        facts[f"within_{band}"] = r.tau * 100
    for name, label in (("R7 year-matched radius", "cut-off from latest offer day before each sale"),
                        ("R8 single-boundary sales", "drop sales near two or more boundaries"),
                        ("R9 boundary-specific slopes", "separate distance slopes per boundary"),
                        ("R10 extra controls", "add tenure and new-build controls"),
                        ("R11 local quadratic", "curved instead of straight fit")):
        for r in rob[rob.test == name].itertuples():
            est, ci = as_pct(r)
            add("Specification", label, est, ci, pval(r.p_value), "flag" if ci_excludes_zero(r) else "holds")
            if name.startswith("R7"):
                facts["yearly"] = (np.expm1(r.tau) * 100, r.p_value)
    loo = rob[rob.test == "R12 leave one boundary out"].dropna(subset=["tau"])
    lo_pct, hi_pct = np.expm1(loo["tau"].min()) * 100, np.expm1(loo["tau"].max()) * 100
    add("Leave one boundary out", "12 re-estimates (Appendix A6)", f"{pct(lo_pct)} to {pct(hi_pct)}", "–", "–", "flag")
    return "\n".join(rows), facts


def main() -> None:
    df, meta = load_sample()
    main_r = json.loads((RESULTS / "main.json").read_text())
    rob = pd.read_csv(RESULTS / "robustness.csv")
    sweep = pd.read_csv(RESULTS / "bandwidth_sensitivity.csv")
    per = pd.read_csv(RESULTS / "per_boundary.csv", dtype={"boundary_id": str})
    octs = pd.read_csv(config.ROOT / "outputs" / "exploratory" / "octant_check.csv")
    construction = pd.read_csv(config.TABLES / "sample_construction.csv")
    summary = pd.read_csv(config.TABLES / "boundary_summary.csv", dtype={"urn": str}).set_index("urn")
    screen = pd.read_csv(config.TABLES / "school_screen_c1_c3.csv", dtype={"urn": str}).set_index("urn")
    prov = pd.read_csv(config.PROVENANCE_FILE, dtype=str, keep_default_na=False)
    recheck = pd.read_csv(config.CATCHMENTS / "recheck.csv", dtype=str)
    lock_payload = json.loads(config.SELECTION_LOCK.read_text())
    selected = lock_payload["selected_urns"]
    names = screen["name"].to_dict()
    short = {u: n.replace(" and Sixth Form", "").replace(" High School", " High").replace(" School", "") for u, n in names.items()}

    rob_rows, facts = robustness_rows(rob)
    pm, plo, phi = main_r["pct"]
    gm, glo, ghi = main_r["pounds"]
    oc = octs.set_index("spec")
    per_i = per.set_index("boundary_id")
    coombe = "137848"

    # A1: the twelve boundaries
    w400 = df[df["d_signed_m"].abs() < config.MAIN_BANDWIDTH_M]
    counts = w400.groupby(["boundary_id", "inside"]).size().unstack(fill_value=0)
    a1 = []
    order = summary.loc[selected].sort_values("radius_median_m").index
    for u in order:
        s, c = summary.loc[u], screen.loc[u]
        years = prov[(prov.urn == u) & (prov.status == "verified")]["entry_year"].astype(int)
        gap = f"{GRADE[int(float(c['grade_2020']))]} vs {GRADE[int(round(float(c['comparator_median'])))].lower()}"
        a1.append(f"<tr><td>{e(names[u])}</td><td>{e(c['la_name'])}</td><td>{e(c['gender'])}</td><td>{e(gap)}</td>"
                  f"<td class='n'>{years.min()}–{years.max()} ({len(years)})</td><td class='n'>{num(s['radius_median_m'])} m</td>"
                  f"<td class='n'>{s['cv']:.2f}</td><td class='n'>{num(counts.loc[u, False])} / {num(counts.loc[u, True])}</td></tr>")

    # A1 detail: every figure
    ok = recheck.set_index(["urn", "year"])["check"].to_dict()
    detail = []
    for r in prov[prov.urn.isin(selected) & (prov.status == "verified")].sort_values(["school_name", "entry_year"]).itertuples():
        how = "script" if ok.get((r.urn, r.entry_year)) == "match" else "individual"
        detail.append(f"<tr><td>{e(r.school_name)}</td><td class='n'>{e(r.entry_year)}</td><td class='n'>{e(r.cutoff_as_published)}</td>"
                      f"<td class='n'>{num(float(r.cutoff_m))} m</td><td>{how}</td>"
                      f"<td><a href='{e(r.source_url)}'>{e(r.source_title[:90])}{'…' if len(r.source_title) > 90 else ''}</a></td></tr>")
    rejected = prov[prov.urn.isin(selected) & (prov.status == "rejected")]

    # A2: sample construction
    a2 = "".join(
        f"<tr><td>{e(r.phase.split(' ', 1)[1])}</td><td>{e(r.step.replace('boundary 143428 not in force', 'Harris Rainham boundary starts 2018'))}</td>"
        f"<td class='n'>{num(r.rows_after)}</td><td class='n'>{num(r.dropped) if r.dropped else '–'}</td><td>{e(r.reason)}</td></tr>"
        for r in construction.itertuples() if not (r.dropped == 0 and r.step in ("record status", "property type", "window", "grid reference", "geolocated sales"))
    )

    # A6: timing and leave-one-out
    timing = rob[rob.test == "R5 timing"].dropna(subset=["tau"])
    a6t = []
    for r in timing.itertuples():
        m = re.match(r"URN (\d+): grade (\d) -> (\d) published (\S+), (\w+)", r.spec)
        a6t.append(f"<tr><td>{e(names[m.group(1)])}</td><td>{GRADE[int(m.group(2))]} → {GRADE[int(m.group(3))]}</td><td class='n'>{m.group(4)}</td>"
                   f"<td>{m.group(5)}</td><td class='n'>{pct(np.expm1(r.tau) * 100)}</td>"
                   f"<td class='n'>{pct(np.expm1(r.ci_low) * 100)} to {pct(np.expm1(r.ci_high) * 100)}</td><td class='n'>{num(r.n_obs)}</td></tr>")
    loo = rob[rob.test == "R12 leave one boundary out"].dropna(subset=["tau"])
    a6l = "".join(
        f"<tr><td>{e(names[r.spec.replace('without ', '')])}</td><td class='n'>{pct(np.expm1(r.tau) * 100)}</td>"
        f"<td class='n'>{pct(np.expm1(r.ci_low) * 100)} to {pct(np.expm1(r.ci_high) * 100)}</td><td class='n'>{pval(r.p_value)}</td></tr>"
        for r in loo.sort_values("tau").itertuples()
    )
    a7 = "".join(
        f"<tr><td>{e(r.spec)}</td><td class='n'>{pct(r.pct)}</td><td class='n'>{pct(r.pct_low)} to {pct(r.pct_high)}</td>"
        f"<td class='n'>{pval(r.p)}</td><td class='n'>{num(r.n)}</td></tr>" for r in octs.itertuples()
    )

    coombe_alone = per_i.loc[coombe]
    without = oc.loc["main, without Coombe Girls'"]
    octant = oc.loc["boundary x octant FE"]
    coombe_oct = oc.loc["Coombe Girls' alone, octant FE"]
    radius_lo, radius_hi = summary.loc[selected, "radius_median_m"].min(), summary.loc[selected, "radius_median_m"].max()
    n_candidates = len(screen)
    n_c3 = int(screen["research_candidate"].astype(str).eq("True").sum())

    page = f"""<title>What a London Catchment Line Is Worth</title>
<meta name="description" content="A pre-registered regression discontinuity study of house prices at twelve London secondary school catchment boundaries.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700;800&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap">
<style>
:root {{
  --paper: #F4F6F3; --plate: #FBFCFA; --ink: #17201C; --graphite: #5A6762; --hair: #D2D9D4;
  --inside: #0A6A4B; --inside-soft: rgba(10, 106, 75, 0.14); --outside: #8C9791; --outside-soft: rgba(90, 103, 98, 0.12);
  --flag: #A4521B; --flag-soft: rgba(164, 82, 27, 0.10); --link: #0A6A4B;
  --display: "Libre Franklin", "Franklin Gothic Medium", "Arial Narrow", Arial, sans-serif;
  --body: "Source Serif 4", "Source Serif Pro", Georgia, "Times New Roman", serif;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper: #0F1412; --plate: #151B18; --ink: #E2E8E4; --graphite: #98A59F; --hair: #29322E;
    --inside: #4DBB8E; --inside-soft: rgba(77, 187, 142, 0.16); --outside: #7D8882; --outside-soft: rgba(152, 165, 159, 0.12);
    --flag: #E39A62; --flag-soft: rgba(227, 154, 98, 0.12); --link: #6FCDA5; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #0F1412; --plate: #151B18; --ink: #E2E8E4; --graphite: #98A59F; --hair: #29322E;
  --inside: #4DBB8E; --inside-soft: rgba(77, 187, 142, 0.16); --outside: #7D8882; --outside-soft: rgba(152, 165, 159, 0.12);
  --flag: #E39A62; --flag-soft: rgba(227, 154, 98, 0.12); --link: #6FCDA5; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink); font: 400 1.125rem/1.62 var(--body); }}
a {{ color: var(--link); text-underline-offset: 2px; text-decoration-thickness: 1px; }}
a:focus-visible, summary:focus-visible {{ outline: 2px solid var(--inside); outline-offset: 3px; border-radius: 2px; }}
.doc {{ max-width: 1000px; margin: 0 auto; padding: 56px 28px 96px; display: grid; grid-template-columns: minmax(0, 1fr); row-gap: 0; }}
.col {{ max-width: 66ch; }}
.eyebrow, .label, th, .chip, figcaption .fig, .meta {{ font-family: var(--display); }}
.eyebrow {{ font-size: 0.78rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--graphite); margin: 0 0 18px; }}
h1 {{ font-family: var(--display); font-weight: 800; font-size: clamp(2.2rem, 5vw, 3.5rem); line-height: 1.02; letter-spacing: -0.025em; margin: 0 0 22px; text-wrap: balance; max-width: 16ch; }}
.lede {{ font-size: 1.32rem; line-height: 1.5; margin: 0; max-width: 58ch; }}
.lede strong {{ font-weight: 600; }}
.hero {{ margin: 34px 0 10px; padding: 18px 0 8px; border-top: 1px solid var(--hair); border-bottom: 1px solid var(--hair); }}
.meta {{ display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 0.82rem; color: var(--graphite); margin: 14px 0 0; font-variant-numeric: tabular-nums; }}
.meta b {{ color: var(--ink); font-weight: 600; }}
h2 {{ font-family: var(--display); font-weight: 700; font-size: 1.5rem; letter-spacing: -0.01em; line-height: 1.2; margin: 64px 0 14px; text-wrap: balance; }}
h3 {{ font-family: var(--display); font-weight: 700; font-size: 1.05rem; margin: 40px 0 8px; }}
p {{ margin: 0 0 16px; }}
.note {{ color: var(--graphite); font-size: 1rem; }}
figure {{ margin: 34px 0 30px; background: var(--plate); border: 1px solid var(--hair); border-radius: 4px; padding: 20px 20px 14px; }}
figcaption {{ font-size: 0.98rem; color: var(--graphite); margin-top: 10px; max-width: 72ch; }}
figcaption .fig {{ font-size: 0.74rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink); margin-right: 8px; }}
.chart {{ width: 100%; height: auto; display: block; overflow: visible; }}
.chart text {{ font-family: var(--display); fill: var(--graphite); }}
.chart .tick {{ font-size: 13px; font-variant-numeric: tabular-nums; }}
.chart .axis {{ font-size: 13px; fill: var(--graphite); }}
.chart .label {{ font-size: 14px; fill: var(--ink); }}
.chart .side {{ font-size: 13px; font-weight: 600; }}
.chart .side.in {{ fill: var(--inside); }} .chart .side.out {{ fill: var(--graphite); }}
.chart .grid {{ stroke: var(--hair); stroke-width: 1; }}
.chart .zero {{ stroke: var(--ink); stroke-width: 1.2; }}
.chart .boundary {{ stroke: var(--ink); stroke-width: 1.4; stroke-dasharray: 9 4 2 4; }}
.chart .prereg {{ stroke: var(--graphite); stroke-width: 1; stroke-dasharray: 4 4; }}
.chart .band.in {{ fill: var(--inside-soft); }} .chart .band.out {{ fill: var(--outside-soft); }}
.chart .fit {{ fill: none; stroke-width: 2.4; }} .chart .fit.in {{ stroke: var(--inside); }} .chart .fit.out {{ stroke: var(--outside); }}
.chart .dot.in {{ fill: var(--inside); }} .chart .dot.out {{ fill: var(--outside); }}
.chart .bar.in {{ fill: var(--inside); opacity: 0.8; }} .chart .bar.out {{ fill: var(--outside); opacity: 0.8; }}
.chart .whisker {{ stroke: var(--outside); stroke-width: 1.6; }}
.chart .pooled-band {{ fill: var(--inside-soft); }}
.hero-svg .ci-bar {{ fill: var(--inside-soft); stroke: var(--inside); stroke-width: 1.5; }}
.hero-svg .ci-point {{ fill: var(--inside); stroke: var(--paper); stroke-width: 3; }}
.hero-svg .ci-label {{ font-size: 15px; font-weight: 600; fill: var(--ink); font-variant-numeric: tabular-nums; }}
.hero-svg .zero {{ stroke-width: 2; }}
.table-wrap {{ overflow-x: auto; margin: 24px 0 30px; border-top: 2px solid var(--ink); }}
table {{ border-collapse: collapse; width: 100%; font-family: var(--display); font-size: 0.86rem; line-height: 1.35; }}
th {{ text-align: left; font-weight: 600; font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--graphite); padding: 10px 12px 8px 0; border-bottom: 1px solid var(--hair); vertical-align: bottom; white-space: nowrap; }}
td {{ padding: 8px 12px 8px 0; border-bottom: 1px solid var(--hair); vertical-align: top; }}
td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
tr.group td {{ padding-top: 16px; font-weight: 600; }}
.chip {{ display: inline-block; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; padding: 2px 7px; border-radius: 3px; white-space: nowrap; }}
.chip.holds {{ color: var(--inside); background: var(--inside-soft); }}
.chip.flag {{ color: var(--flag); background: var(--flag-soft); }}
.chip.mixed, .chip.context {{ color: var(--graphite); box-shadow: inset 0 0 0 1px var(--hair); }}
.caution {{ border-left: 3px solid var(--flag); padding: 2px 0 2px 18px; margin: 22px 0; }}
.caution .label {{ font-size: 0.74rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--flag); display: block; margin-bottom: 4px; }}
ul.plain {{ padding-left: 1.1em; margin: 0 0 16px; }} ul.plain li {{ margin-bottom: 8px; }}
.appendix {{ margin-top: 88px; padding-top: 8px; border-top: 2px solid var(--ink); }}
.appendix h2 {{ margin-top: 28px; }}
details {{ margin: 8px 0 26px; }}
summary {{ cursor: pointer; font-family: var(--display); font-weight: 600; font-size: 0.92rem; color: var(--link); }}
code {{ font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 0.86em; background: var(--outside-soft); padding: 1px 5px; border-radius: 3px; }}
@media (max-width: 640px) {{ .doc {{ padding: 36px 16px 64px; }} .lede {{ font-size: 1.14rem; }} figure {{ padding: 12px 10px 10px; }} }}
</style>

<main class="doc">
<header>
  <p class="eyebrow">Regression discontinuity · 12 London secondary schools · sales 2015–2025</p>
  <h1>What a London catchment line is worth</h1>
  <p class="lede">Across twelve oversubscribed London secondary schools, a home just inside the admissions line sold for an estimated
  <strong>{pct(pm)}</strong> more than one just outside, about <strong>{gbp(gm)}</strong> at the median outside price of £{num(main_r['median_price_outside'])}.
  The 95% interval runs from {pct(plo)} to {pct(phi)} ({gbp(glo)} to {gbp(ghi)}), so this study cannot tell that premium apart from zero.</p>
  <div class="hero">{hero_interval(main_r)}</div>
  <p class="meta"><span><b>{num(main_r['n_obs'])}</b> sales within 400 m</span><span><b>12</b> boundaries, {num(radius_lo)}–{num(radius_hi)} m radius</span>
  <span>clustered <i>t</i>({main_r['df_inference']}) <b>p = {pval(main_r['p_value'])}</b></span><span>wild cluster bootstrap <b>p = {pval(main_r['p_wild_bootstrap'])}</b></span>
  <span>selection locked before prices were read</span><span><a href="{REPO_URL}">code, data sources and pre-registration</a></span></p>
</header>

<figure>
  {headline_chart(df, main_r)}
  <figcaption><span class="fig">Figure 1</span>Mean sale price in 25 m bands either side of the boundary, after removing differences
  by property type, quarter and boundary; dot size shows how many sales each band holds. Lines are fitted separately on each side with
  95% bands. The two lines meet the boundary close together: whatever jump there is, it is small next to the scatter around it.</figcaption>
</figure>

<section class="col">
<h2>Why not just regress price on school quality</h2>
<p>The obvious analysis takes every sale, records the Ofsted grade of the nearest school, adds controls for transport, crime and
green space, and reads off the coefficient. It almost always finds a large premium, and it is almost always wrong about what that premium is.</p>
<p>Good schools are not scattered at random. They sit where families with money already live, and those families bid up housing for
reasons of their own: larger gardens, quieter streets, better shops. The school coefficient soaks all of that up. Controls remove only the
confounders somebody thought of and managed to measure well.</p>
<p>The causation also runs the other way. Affluent catchments produce better-resourced intakes and better inspection grades. A model that treats
school quality as fixed and price as the response cannot tell a school raising prices from prices raising a school.</p>

<h2>The comparison instead</h2>
<p>This study controls for none of that. It looks where the school changes and nothing else does. An oversubscribed secondary that ranks
applicants by distance gives its last place to a child living a particular distance away, and councils publish that distance on national offer day
each March. Around a school that admits purely on straight-line distance, it traces a circle. Two houses fifty metres apart, one on each side, share a
street, a bus stop and a postcode sector. Only one carries the expectation of a place.</p>
<p>Schools were chosen by rules committed to the repository before any price was downloaded: mainstream, non-selective and without faith
criteria; places ranked by straight-line distance with no banding, feeder schools or lottery; rated better than the three nearest alternatives;
at least three years of published cut-offs that varied little; and enough sales on both sides. Of {n_candidates} London secondary school records screened,
{n_c3} cleared the type, faith and quality rules, and twelve cleared the rest. Each boundary is the circle at the school's median cut-off.
The choice of schools was locked, and the lock committed, before the first price was read.</p>
<p>The estimate compares sales within 400 metres of each line, weighting nearer sales more, with a straight-line fit on each side and
allowances for property type, quarter and boundary. Uncertainty is measured across boundaries, not sales, and with only twelve boundaries a
bootstrap built for few clusters is reported as well. What this measures is the price of <em>advertised</em> eligibility: living inside the
historical cut-off raises the chance of a place, it does not guarantee one.</p>

<h2>Trying to break it</h2>
<p>Every pre-registered check was run. Table 1 reports all of them, including the ones that came out awkwardly.</p>
</section>

<div class="table-wrap">
<table>
  <thead><tr><th>Check</th><th>What changes</th><th class="n">Estimate</th><th class="n">95% interval</th><th class="n">p</th><th>Result</th></tr></thead>
  <tbody>
  <tr><td>Main estimate</td><td>pre-registered specification, 400 m</td><td class="n">{pct(pm)}</td><td class="n">{pct(plo)} to {pct(phi)}</td><td class="n">{pval(main_r['p_value'])}</td><td>{chip('context')}</td></tr>
  {rob_rows}
  </tbody>
</table>
</div>
<p class="note col" style="margin-top:-18px">Table 1. Balance checks use the same comparison with a neighbourhood characteristic in place of price;
"pp" is percentage points. A placebo or balance check is flagged when its interval excludes zero, a specification check when its own interval does.</p>

<section class="col">
<p>Most checks hold. Fake boundaries 250 and 500 metres either side of the real one show nothing. Sales do not bunch just inside the line
(McCrary test p = {pval(facts['mccrary_p'])}), so neither buyers nor developers are visibly sorting on it. Dropping sales within 25 or 50 metres
of the line, where location is least precise, leaves the estimate in place, and it barely moves across bandwidths from 350 to 750 metres
(Appendix A3).</p>
<p>Three checks do not hold. Inside the line there are {abs(facts['flat'][0]):.1f} percentage points fewer flats (p = {pval(facts['flat'][1])}): the
price comparison already allows for property type, but the two sides are not quite alike. Measuring each sale against the cut-off published
just before it, rather than the median, gives {pct(facts['yearly'][0])} (p = {pval(facts['yearly'][1])}). And one boundary carries much of the positive
point estimate. Coombe Girls' School in New Malden shows {pct(coombe_alone.pct)} on its own; without it the pooled estimate is
{pct(without.pct)} ({pct(without.pct_low)} to {pct(without.pct_high)}).</p>
<div class="caution"><span class="label">Exploratory, not pre-registered</span>
<p style="margin:0">Written after the results were seen, to understand Coombe Girls'. Its northern arc passes Coombe Hill, one of London's most
expensive enclaves, where prices change by hundreds of thousands of pounds within a few streets for reasons unrelated to any school; none of the
pre-registered balance variables captures that. Comparing sales only within the same 45° arc of each circle cuts Coombe's jump to
{pct(coombe_oct.pct)} and moves the pooled estimate to {pct(octant.pct)} ({pct(octant.pct_low)} to {pct(octant.pct_high)}). Reasonable choices move the
point estimate to either side of zero, which is exactly why the pre-registered number stays the headline.</p></div>

<h2>What the number supports</h2>
<p>At these boundaries, large premiums are ruled out. An effect above {pct(phi)} of price lies outside the interval, and the kind of five-figure
catchment premium that circulates among buyers is not supported here. A small premium of a few percent is compatible with the data but not
established by it.</p>
<p>Two known problems push the estimate toward zero, so it is nearer a floor than a ceiling. Sale locations are postcode centroids, about fifteen
addresses each, so some sales near every line sit on the wrong side of it ({facts['within_25']:.1f}% of the sample lies within 25 metres). And several schools
measure to a named gate while the boundaries are drawn from the school's registered coordinate. Both blur the line and flatten a jump.</p>

<h2>What this does not show</h2>
<ul class="plain">
  <li><strong>London's other secondaries.</strong> These twelve admit on distance, are rated above their neighbours and are mostly in outer
  boroughs. Banded, faith and selective schools, which dominate inner London, are excluded by design.</li>
  <li><strong>Whether the schools are good.</strong> The comparison prices eligibility for a school parents rate, not the quality of its teaching.</li>
  <li><strong>Any effect on children.</strong> Nothing here follows a pupil.</li>
  <li><strong>The value of a guaranteed place.</strong> Being inside the line raises the odds; siblings and moving cut-offs mean it does not secure one.</li>
</ul>
</section>

<section class="appendix">
<h2>Appendix</h2>

<h3>A1 · The twelve boundaries</h3>
<p class="note col">Ordered by radius. "Ofsted" compares the grade in force on 1 January 2020 with the median of the three nearest
alternatives. Sales are those in the final sample within 400 m, outside / inside. Harris Academy Rainham's boundary applies only to sales
from 2018, because its 2017 round gave priority to partner-school applicants.</p>
<div class="table-wrap"><table>
<thead><tr><th>School</th><th>Borough</th><th>Pupils</th><th>Ofsted, 2020</th><th class="n">Cut-off years</th><th class="n">Median radius</th><th class="n">CV</th><th class="n">Sales out / in</th></tr></thead>
<tbody>{"".join(a1)}</tbody></table></div>
<p class="note col">Cut-offs were transcribed from council allocation tables, booklets and spreadsheets, some through Internet Archive copies
of files councils have since removed. Of the {len(detail)} school-year figures used, {sum(1 for d in detail if '>script<' in d)} were confirmed by an automated re-read of the source (value on
the school's own row, correct entry year) and {sum(1 for d in detail if '>individual<' in d)} were checked individually (image-only PDFs re-read from enlarged scans, one split-column
table re-aligned). The author approved the set without re-reading every source; <a href="{REPO_URL}/blob/main/DEVIATIONS.md"><code>DEVIATIONS.md</code></a> records how it was checked. {len(rejected)} figures were
rejected, including Merton's 2025 rows, which repeat 2024 to the penny.</p>
<details><summary>All {len(detail)} cut-off figures and their sources</summary>
<div class="table-wrap"><table>
<thead><tr><th>School</th><th class="n">Entry</th><th class="n">As published</th><th class="n">Metres</th><th>Checked</th><th>Source</th></tr></thead>
<tbody>{"".join(detail)}</tbody></table></div></details>

<h3>A2 · Sample construction</h3>
<div class="table-wrap"><table>
<thead><tr><th>Stage</th><th>Step</th><th class="n">Rows after</th><th class="n">Dropped</th><th>Why</th></tr></thead>
<tbody>{a2}</tbody></table></div>
<p class="note col">From the "candidate pairs" step, rows are sale–boundary pairs rather than sales; the final {num(len(df))} rows are one per sale.</p>

<h3>A3 · Bandwidth</h3>
<figure>{bandwidth_chart(sweep)}
<figcaption><span class="fig">Figure A3</span>The same comparison using sales within 100 m to 750 m of the line. Narrow bandwidths are noisier
and lean positive; from 350 m outward the estimate sits between {pct(np.expm1(sweep[sweep.bandwidth_m >= 350].tau.min()) * 100)} and {pct(np.expm1(sweep[sweep.bandwidth_m >= 350].tau.max()) * 100)}.</figcaption></figure>

<h3>A4 · Each boundary on its own</h3>
<figure>{forest_chart(per, main_r, short)}
<figcaption><span class="fig">Figure A4</span>One estimate per school, with uncertainty measured across postcodes. Eleven intervals include
zero; Coombe Girls' does not. The shaded band is the pooled interval.</figcaption></figure>

<h3>A5 · Where sales sit</h3>
<figure>{density_chart(df)}
<figcaption><span class="fig">Figure A5</span>Sales per 10 m band. Counts rise outward because a circle's circumference grows with radius; the
test is for a jump at zero, not a slope. McCrary log-density difference {rob[(rob.test == 'R3 density (McCrary)') & (rob.spec == 'sales')].tau.iloc[0]:+.3f}, p = {pval(facts['mccrary_p'])}.</figcaption></figure>

<h3>A6 · Grade changes and leave-one-out</h3>
<p class="note col">If buyers price the school rather than the line, the premium at a boundary should move when the school's Ofsted
grade changes. Eight selected schools changed grade with at least two years of sales on either side. No consistent pattern appears, and the
per-school intervals are wide.</p>
<div class="table-wrap"><table>
<thead><tr><th>School</th><th>Grade change</th><th class="n">Published</th><th>Sales</th><th class="n">Estimate</th><th class="n">95% interval</th><th class="n">Sales</th></tr></thead>
<tbody>{"".join(a6t)}</tbody></table></div>
<div class="table-wrap"><table>
<thead><tr><th>Boundary left out</th><th class="n">Estimate</th><th class="n">95% interval</th><th class="n">p</th></tr></thead>
<tbody>{a6l}</tbody></table></div>

<h3>A7 · Exploratory diagnostics</h3>
<p class="note col">Not pre-registered. Written after the main results, to diagnose one boundary. "Octant" comparisons use only sales
within the same 45° arc of each circle. Per-boundary balance tables are in <code>outputs/exploratory/</code>.</p>
<div class="table-wrap"><table>
<thead><tr><th>Specification</th><th class="n">Estimate</th><th class="n">95% interval</th><th class="n">p</th><th class="n">Sales</th></tr></thead>
<tbody>{a7}</tbody></table></div>

<h3>A8 · Changes to the plan</h3>
<ul class="plain col">
  <li>Opposite-sex schools do not count as alternatives when deciding whether an outside sale is contaminated (Ricards Lodge and Rutlish overlap).</li>
  <li>A school with any undersubscribed year in the window fails; schools ranking a priority area before distance fail; three years of cut-offs remain the minimum.</li>
  <li>Harris Academy Rainham's boundary applies from 2018, after a partner-school priority in its 2017 round.</li>
  <li>The deprivation balance check uses the IMD 2019 rank that ONS publishes with postcodes, not the score.</li>
  <li>Boundary figures were re-checked by script and individually rather than read row by row by the author.</li>
</ul>
<p class="note col">Each change is dated in <a href="{REPO_URL}/blob/main/DEVIATIONS.md"><code>DEVIATIONS.md</code></a> with whether prices had been examined; none had. Reproduce everything from public
downloads with <code>python -m pipeline.run</code> from the <a href="{REPO_URL}">code repository</a>. Sample hash <code>{meta['sha256'][:16]}</code>.</p>

<h3>Data</h3>
<p class="note col">Contains HM Land Registry data © Crown copyright and database right 2021, licensed under the Open Government Licence v3.0.
ONS Postcode Directory (August 2026): source Office for National Statistics, OGL v3.0; contains OS data © Crown copyright and database right and
Royal Mail data © Royal Mail copyright and database right. Get Information About Schools, Ofsted management information and NaPTAN: OGL v3.0.
Council admissions documents are cited per figure in A1.</p>
</section>
</main>
"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text("<!doctype html>\n<html lang=\"en-GB\"><head><meta charset=\"utf-8\">"
                                        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
                                        + page.replace("<main", "</head><body>\n<main", 1) + "</body></html>\n", encoding="utf-8")
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    if "--body-only" in sys.argv:
        Path(sys.argv[sys.argv.index("--body-only") + 1]).write_text(page, encoding="utf-8")
    prose = re.sub(r"<[^>]+>", " ", page.split('<section class="appendix">')[0].split("</style>")[1])
    prose = re.sub(r"<svg.*?</svg>", " ", prose, flags=re.S)
    print(f"writeup -> {OUT_DIR / 'index.html'}; main text about {len(re.findall(r'[A-Za-z£%0-9]+', prose))} words")


if __name__ == "__main__":
    sys.exit(main())
