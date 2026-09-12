"""The four figures the plan calls for. matplotlib only, no style packages.

The headline chart is built so the finding is visible before any statistic is
read: binned means either side of zero, a fitted line per side with its band,
and a gap at the boundary. Everything else in the writeup exists to convince
the reader that gap is real.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import config, rdd

INK = "#1f2328"
MUTED = "#6e7781"
OUTSIDE = "#8c959f"
INSIDE = "#0b6e4f"


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color="#d0d7de", linewidth=0.6)
    ax.set_axisbelow(True)


def _side_fit(w: pd.DataFrame, h: float, inside: bool, grid: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Weighted local linear fit on one side, with a pointwise 95% band.

    For display only. The estimate in the text comes from the pooled
    regression with fixed effects; this line is fitted to the same
    residualised outcome the dots show, so the picture and the model agree.
    """
    part = w[(w["d_signed_m"] > 0) == inside]
    X = sm.add_constant(part["d_signed_m"].to_numpy())
    res = sm.WLS(part["_y"].to_numpy(), X, weights=rdd.triangular_weights(part["d_signed_m"].to_numpy(), h)).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(part["boundary_id"])[0]})
    pred = res.get_prediction(sm.add_constant(grid, has_constant="add")).summary_frame(alpha=0.05)
    return pred["mean"].to_numpy(), pred["mean_ci_lower"].to_numpy(), pred["mean_ci_upper"].to_numpy()


def headline(df: pd.DataFrame, main: rdd.RDResult, path, h: float = config.MAIN_BANDWIDTH_M, bin_m: float = 25.0) -> None:
    w = df.loc[df["d_signed_m"].abs() < h].copy()
    w["_y"] = rdd.residualise_fe(w, "log_price", rdd.MAIN_FE)
    bins = rdd.binned_means(df, h, bin_m)

    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=200)
    _style(ax)
    for inside, colour in ((False, OUTSIDE), (True, INSIDE)):
        grid = np.linspace(0.5, h, 60) if inside else np.linspace(-h, -0.5, 60)
        mean, lo, hi = _side_fit(w, h, inside, grid)
        ax.fill_between(grid, lo, hi, color=colour, alpha=0.15, linewidth=0)
        ax.plot(grid, mean, color=colour, linewidth=2)
        b = bins[(bins["mid_m"] > 0) == inside]
        ax.scatter(b["mid_m"], b["mean"], s=np.clip(b["n"] / b["n"].max() * 40, 8, 40), color=colour, zorder=3)
    ax.axvline(0, color=INK, linewidth=0.8, linestyle=(0, (4, 3)))

    # Log price on the scale, pounds on the labels: pounds are what a reader
    # understands. Ticks sit on round pounds, so the labels are not £259k.
    lo, hi = ax.get_ylim()
    p_lo, p_hi = np.exp(lo), np.exp(hi)
    step = next(s for s in (5e3, 1e4, 2e4, 2.5e4, 5e4, 1e5, 2e5, 2.5e5, 5e5) if (p_hi - p_lo) / s <= 7)
    pounds_ticks = np.arange(np.ceil(p_lo / step) * step, p_hi, step)
    ax.set_yticks(np.log(pounds_ticks))
    ax.set_yticklabels([f"£{v / 1000:,.0f}k" for v in pounds_ticks])
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Distance to catchment boundary (m)   ← outside   |   inside →", color=INK, fontsize=10)
    ax.set_ylabel("Price, adjusted for type, quarter and boundary", color=INK, fontsize=10)

    pct, pct_lo, pct_hi = main.pct
    pounds = main.pounds
    headline_txt = f"Crossing the line: {pct:+.1f}% (95% CI {pct_lo:+.1f}% to {pct_hi:+.1f}%)"
    if pounds:
        headline_txt += f"\n≈ £{pounds[0]:,.0f} at the median outside price (£{pounds[1]:,.0f} to £{pounds[2]:,.0f})"
    ax.set_title(headline_txt, loc="left", color=INK, fontsize=11)
    ax.text(0.0, -0.2, f"{main.n_clusters} boundaries · {main.n_obs:,} sales within {h:.0f} m · triangular kernel · "
            f"SE clustered by boundary", transform=ax.transAxes, color=MUTED, fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def bandwidth(sweep: pd.DataFrame, path) -> None:
    s = sweep.dropna(subset=["tau"])
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=200)
    _style(ax)
    pct = np.expm1(s[["tau", "ci_low", "ci_high"]].to_numpy()) * 100
    ax.fill_between(s["bandwidth_m"], pct[:, 1], pct[:, 2], color=INSIDE, alpha=0.15, linewidth=0)
    ax.plot(s["bandwidth_m"], pct[:, 0], color=INSIDE, marker="o", markersize=3, linewidth=1.5)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.axvline(config.MAIN_BANDWIDTH_M, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.text(config.MAIN_BANDWIDTH_M, ax.get_ylim()[1], " pre-registered h", color=MUTED, fontsize=8, va="top")
    ax.set_xlabel("Bandwidth (m)", color=INK)
    ax.set_ylabel("Premium (%) with 95% CI", color=INK)
    ax.set_title("Estimate against bandwidth, published whatever it shows", loc="left", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def forest(per: pd.DataFrame, pooled: rdd.RDResult, names: dict[str, str], path) -> None:
    p = per.dropna(subset=["pct"]).sort_values("pct")
    fig, ax = plt.subplots(figsize=(7, 0.35 * len(p) + 1.4), dpi=200)
    _style(ax)
    ax.grid(axis="x", color="#d0d7de", linewidth=0.6)
    ax.grid(axis="y", visible=False)
    y = np.arange(len(p))
    ax.errorbar(p["pct"], y, xerr=[p["pct"] - p["pct_low"], p["pct_high"] - p["pct"]], fmt="o", color=INSIDE,
                ecolor=OUTSIDE, markersize=4, capsize=0, linewidth=1)
    pc, pl, ph = pooled.pct
    ax.axvspan(pl, ph, color=INSIDE, alpha=0.08)
    ax.axvline(pc, color=INSIDE, linewidth=1)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([names.get(b, b) for b in p["boundary_id"]], fontsize=8, color=INK)
    ax.set_xlabel("Premium (%) with 95% CI; band = pooled estimate", color=INK)
    ax.set_title("Each boundary on its own", loc="left", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def density_hist(df: pd.DataFrame, path, h: float = config.MAX_BANDWIDTH_M, bin_m: float = config.DENSITY_BIN_M) -> None:
    d = df.loc[df["d_signed_m"].abs() < h, "d_signed_m"]
    fig, ax = plt.subplots(figsize=(7, 3.4), dpi=200)
    _style(ax)
    edges = np.arange(-h, h + bin_m, bin_m)
    counts, _ = np.histogram(d, bins=edges)
    mids = edges[:-1] + bin_m / 2
    ax.bar(mids, counts, width=bin_m, color=np.where(mids > 0, INSIDE, OUTSIDE), linewidth=0)
    ax.axvline(0, color=INK, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.set_xlabel("Distance to boundary (m)", color=INK)
    ax.set_ylabel(f"Sales per {bin_m:.0f} m bin", color=INK)
    ax.set_title("Where sales sit relative to the line", loc="left", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
