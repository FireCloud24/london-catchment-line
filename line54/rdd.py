"""Local linear regression discontinuity with fixed effects and few clusters.

The regression itself goes through statsmodels. The wild cluster bootstrap is
written out in linear algebra, because with 10-25 boundaries conventional
cluster-robust p-values are too small, and the standard fix is cheap once the
projection matrix is in hand.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from . import config

MAIN_FE = ("property_type", "year_quarter", "boundary_id")


@dataclass
class RDResult:
    tau: float
    se: float
    ci_low: float
    ci_high: float
    p_value: float
    df_inference: int
    n_obs: int
    n_inside: int
    n_outside: int
    n_clusters: int
    bandwidth_m: float
    cutoff_m: float = 0.0
    donut_m: float = 0.0
    poly: int = 1
    p_wild_bootstrap: float | None = None
    median_price_outside: float | None = None
    label: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def pct(self) -> tuple[float, float, float]:
        """Premium as a percentage: exp(tau) - 1, transformed endpoint-wise."""
        return tuple(float(np.expm1(v)) * 100 for v in (self.tau, self.ci_low, self.ci_high))

    @property
    def pounds(self) -> tuple[float, float, float] | None:
        if self.median_price_outside is None:
            return None
        return tuple(float(np.expm1(v)) * self.median_price_outside for v in (self.tau, self.ci_low, self.ci_high))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pct"], d["pounds"] = self.pct, self.pounds
        return d


def triangular_weights(x: np.ndarray, h: float) -> np.ndarray:
    return np.clip(1.0 - np.abs(x) / h, 0.0, None)


def _window(
    df: pd.DataFrame, h: float, cutoff: float, donut: float, side: str | None, running: str
) -> pd.DataFrame:
    x = df[running].to_numpy() - cutoff
    keep = np.abs(x) < h
    if donut:
        keep &= np.abs(x) >= donut
    # Placebo cut-offs use one side of the real boundary only, so the real
    # jump cannot leak into the placebo estimate.
    if side == "inside":
        keep &= df[running].to_numpy() > 0
    elif side == "outside":
        keep &= df[running].to_numpy() <= 0
    out = df.loc[keep].copy()
    out["_x"] = x[keep]
    return out


def design(
    w: pd.DataFrame, poly: int, fe: tuple[str, ...], boundary_slopes: bool
) -> tuple[pd.DataFrame, list[str]]:
    x = w["_x"].to_numpy()
    inside = (x > 0).astype(float)
    cols = {"const": np.ones(len(w)), "inside": inside}
    for k in range(1, poly + 1):
        cols[f"x{k}"] = x**k
        cols[f"x{k}_inside"] = (x**k) * inside
    X = pd.DataFrame(cols, index=w.index)
    notes = []
    if boundary_slopes and "boundary_id" in w:
        # Each boundary gets its own slope on each side, relative to the first.
        b = pd.get_dummies(w["boundary_id"], prefix="bs", drop_first=True, dtype=float)
        for c in b.columns:
            X[f"{c}_x1"] = b[c] * x
            X[f"{c}_x1_inside"] = b[c] * x * inside
    for name in fe:
        if name not in w:
            continue
        d = pd.get_dummies(w[name].astype(str), prefix=f"fe_{name}", drop_first=True, dtype=float)
        if d.shape[1]:
            X = pd.concat([X, d], axis=1)
    # A dummy that never varies inside the window is collinear with const.
    constant = [c for c in X.columns if c.startswith(("fe_", "bs_")) and X[c].std() == 0]
    if constant:
        X = X.drop(columns=constant)
        notes.append(f"dropped {len(constant)} constant FE columns")
    return X, notes


def fit(
    df: pd.DataFrame,
    h: float = config.MAIN_BANDWIDTH_M,
    *,
    outcome: str = "log_price",
    running: str = "d_signed_m",
    cutoff: float = 0.0,
    donut: float = 0.0,
    side: str | None = None,
    poly: int = 1,
    fe: tuple[str, ...] = MAIN_FE,
    cluster: str = "boundary_id",
    boundary_slopes: bool = False,
    bootstrap_draws: int = 0,
    seed: int = config.BOOTSTRAP_SEED,
    label: str = "",
) -> RDResult:
    w = _window(df, h, cutoff, donut, side, running)
    w = w.dropna(subset=[outcome])
    if w.empty or (w["_x"] > 0).sum() == 0 or (w["_x"] <= 0).sum() == 0:
        raise ValueError(f"{label or 'fit'}: no observations on one side within h={h}")
    X, notes = design(w, poly, fe, boundary_slopes)
    y = w[outcome].to_numpy(dtype=float)
    wt = triangular_weights(w["_x"].to_numpy(), h)
    groups = pd.factorize(w[cluster])[0]
    G = int(groups.max()) + 1
    if G < 2:
        raise ValueError(f"{label or 'fit'}: need at least 2 clusters, got {G}")

    res = sm.WLS(y, X, weights=wt).fit(cov_type="cluster", cov_kwds={"groups": groups}, use_t=True)
    tau = float(res.params["inside"])
    se = float(res.bse["inside"])
    # Explicit t(G-1): the number of clusters, not observations, sets how much
    # information there is about the standard error.
    dfi = G - 1
    crit = stats.t.ppf(0.975, dfi)
    p = float(2 * stats.t.sf(abs(tau / se), dfi)) if se > 0 else float("nan")

    result = RDResult(
        tau=tau,
        se=se,
        ci_low=tau - crit * se,
        ci_high=tau + crit * se,
        p_value=p,
        df_inference=dfi,
        n_obs=len(w),
        n_inside=int((w["_x"] > 0).sum()),
        n_outside=int((w["_x"] <= 0).sum()),
        n_clusters=G,
        bandwidth_m=h,
        cutoff_m=cutoff,
        donut_m=donut,
        poly=poly,
        label=label,
        notes=notes,
    )
    if "price" in w:
        result.median_price_outside = float(w.loc[w["_x"] <= 0, "price"].median())
    if bootstrap_draws:
        result.p_wild_bootstrap = wild_cluster_bootstrap_p(
            X.to_numpy(dtype=float), y, wt, groups, list(X.columns).index("inside"), bootstrap_draws, seed
        )
    return result


def cluster_se(X: np.ndarray, resid: np.ndarray, w: np.ndarray, groups: np.ndarray, k: int) -> float:
    """CR1 standard error for coefficient k, matching statsmodels' correction."""
    n, K = X.shape
    G = int(groups.max()) + 1
    XtWX_inv = np.linalg.pinv(X.T @ (X * w[:, None]))
    m = (XtWX_inv @ (X * w[:, None]).T)[k]  # row k of (X'WX)^-1 X'W
    s = np.bincount(groups, weights=m * resid, minlength=G)
    c = G / (G - 1) * (n - 1) / (n - K)
    return float(np.sqrt(c * np.sum(s**2)))


_WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])


def wild_cluster_bootstrap_p(
    X: np.ndarray, y: np.ndarray, w: np.ndarray, groups: np.ndarray, k: int, draws: int, seed: int
) -> float:
    """Restricted wild cluster bootstrap (WCR) p-value for H0: beta_k = 0.

    Webb six-point weights, because Rademacher weights only give 2^G distinct
    draws and with 10 clusters that is 1,024.

    Every draw is linear in the cluster weights, so each draw collapses to a
    G-vector: y* = y_r + u_r * v[g] gives beta* = beta_r + A v and cluster
    scores s = (C1 - B A) v. No N-length arithmetic per draw.
    """
    n, K = X.shape
    G = int(groups.max()) + 1
    Xw = X * w[:, None]
    XtWX_inv = np.linalg.pinv(X.T @ Xw)
    M = XtWX_inv @ Xw.T  # K x N

    # Restricted fit: drop column k, so the null is imposed on the DGP.
    Xr = np.delete(X, k, axis=1)
    beta_r = np.linalg.lstsq(Xr * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)[0]
    y_r = Xr @ beta_r
    u_r = y - y_r

    c = G / (G - 1) * (n - 1) / (n - K)

    def t_stat(beta_k: float, scores: np.ndarray) -> float:
        return beta_k / np.sqrt(c * np.sum(scores**2))

    beta_hat = M @ y
    t_obs = t_stat(beta_hat[k], np.bincount(groups, weights=M[k] * (y - X @ beta_hat), minlength=G))

    # A[:, g] = M restricted to cluster g, times u_r.
    A = np.vstack([np.bincount(groups, weights=M[j] * u_r, minlength=G) for j in range(K)])  # K x G
    # B[g, j] = sum over i in g of M[k, i] * X[i, j]
    B = np.vstack([np.bincount(groups, weights=M[k] * X[:, j], minlength=G) for j in range(K)]).T  # G x K
    C1 = A[k]  # sum over i in g of M[k, i] * u_r[i]
    # beta_r in the full-column space: y_r is exactly in span(X), so M @ y_r
    # recovers it and the restricted beta_k is 0 by construction.
    beta_k_base = (M @ y_r)[k]

    rng = np.random.default_rng(seed)
    V = rng.choice(_WEBB, size=(draws, G))
    beta_k_star = beta_k_base + V @ A[k]
    scores = V * C1 - V @ (B @ A).T
    t_star = beta_k_star / np.sqrt(c * np.sum(scores**2, axis=1))
    return float(np.mean(np.abs(t_star) >= abs(t_obs)))


def bandwidth_sweep(df: pd.DataFrame, grid=config.BANDWIDTH_GRID_M, **kw) -> pd.DataFrame:
    rows = []
    for h in grid:
        try:
            r = fit(df, h, label=f"h={h:g}", **kw)
            rows.append(r.to_dict())
        except ValueError as e:
            rows.append({"bandwidth_m": h, "label": f"h={h:g}", "notes": [str(e)]})
    return pd.DataFrame(rows)


def residualise_fe(df: pd.DataFrame, outcome: str, fe: tuple[str, ...]) -> np.ndarray:
    """Outcome net of fixed effects, re-centred on its mean, for binned plots.

    Binned raw means would mix the step at zero with composition: a bin that
    happens to hold more flats or more 2016 sales moves for reasons the
    regression has already absorbed.
    """
    dummies = [pd.get_dummies(df[c].astype(str), drop_first=True, dtype=float) for c in fe if c in df]
    y = df[outcome].to_numpy(dtype=float)
    if not dummies:
        return y
    Z = np.column_stack([np.ones(len(df))] + [d.to_numpy() for d in dummies])
    beta = np.linalg.lstsq(Z, y, rcond=None)[0]
    return y - Z @ beta + y.mean()


def binned_means(
    df: pd.DataFrame, h: float, bin_m: float, outcome: str = "log_price", running: str = "d_signed_m",
    fe: tuple[str, ...] = MAIN_FE,
) -> pd.DataFrame:
    w = df.loc[np.abs(df[running]) < h].copy()
    w["_y"] = residualise_fe(w, outcome, fe)
    # Bins (k*b, (k+1)*b]: zero is always an edge, and d = 0 falls outside,
    # the same rule as treatment and as the density histogram.
    w["_k"] = np.ceil(w[running].to_numpy() / bin_m).astype(int) - 1
    out = w.groupby("_k").agg(mean=("_y", "mean"), n=("_y", "size"), sd=("_y", "std")).reset_index()
    out["mid_m"] = (out["_k"] + 0.5) * bin_m
    return out.drop(columns="_k")
