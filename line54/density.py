"""McCrary (2008) density discontinuity test on the running variable.

If sales bunch just inside the line, buyers or developers are sorting on it,
and houses either side are no longer comparable. The test fits a local linear
density on each side of the cut-off and compares the two limits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats


@dataclass
class DensityResult:
    theta: float  # log difference of densities, inside minus outside
    se: float
    z: float
    p_value: float
    f_inside: float
    f_outside: float
    n: int
    bin_m: float
    bandwidth_m: float

    def to_dict(self) -> dict:
        return asdict(self)


def _local_linear_at(x: np.ndarray, y: np.ndarray, h: float, at: float) -> float:
    w = np.clip(1.0 - np.abs(x - at) / h, 0.0, None)
    keep = w > 0
    if keep.sum() < 3:
        return float("nan")
    X = np.column_stack([np.ones(keep.sum()), x[keep] - at])
    sw = np.sqrt(w[keep])
    beta = np.linalg.lstsq(X * sw[:, None], y[keep] * sw, rcond=None)[0]
    return float(beta[0])


def histogram(d: np.ndarray, bin_m: float, cutoff: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Bin midpoints and normalised frequencies. No bin straddles the cut-off.

    Empty bins inside the data's range are kept as zeros: dropping them would
    bias the density up exactly where there is least data.
    """
    x = np.asarray(d, dtype=float) - cutoff
    # Bins are (k*b, (k+1)*b] on integer k, so zero is always an edge and a
    # value of exactly zero counts as outside, matching treatment = d > 0.
    k = np.ceil(x / bin_m).astype(int) - 1
    k_lo, k_hi = int(k.min()), int(k.max())
    counts = np.bincount(k - k_lo, minlength=k_hi - k_lo + 1)
    mids = (np.arange(k_lo, k_hi + 1) + 0.5) * bin_m
    return mids + cutoff, counts / (len(x) * bin_m)


def mccrary(d: np.ndarray, bin_m: float, bandwidth_m: float, cutoff: float = 0.0) -> DensityResult:
    d = np.asarray(d, dtype=float)
    n = len(d)
    mids, freq = histogram(d, bin_m, cutoff)
    x = mids - cutoff
    right = x > 0
    f_in = _local_linear_at(x[right], freq[right], bandwidth_m, 0.0)
    f_out = _local_linear_at(x[~right], freq[~right], bandwidth_m, 0.0)
    theta = np.log(f_in) - np.log(f_out)
    # McCrary (2008), eq. for the asymptotic standard error of theta.
    se = np.sqrt((1.0 / (n * bandwidth_m)) * (24.0 / 5.0) * (1.0 / f_in + 1.0 / f_out))
    z = theta / se
    return DensityResult(
        theta=float(theta),
        se=float(se),
        z=float(z),
        p_value=float(2 * stats.norm.sf(abs(z))),
        f_inside=f_in,
        f_outside=f_out,
        n=n,
        bin_m=bin_m,
        bandwidth_m=bandwidth_m,
    )
