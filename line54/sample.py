"""Sample construction: sale-boundary pairs, the pre-registered drop rules, and
the step log that becomes the sample construction table.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .catchments import Boundary


@dataclass
class StepLog:
    """Rows at each filtering step, with the count dropped and why.

    Reviewers read this table before the conclusion, so every filter in the
    pipeline goes through `record` rather than happening silently.
    """

    rows: list[dict] = field(default_factory=list)

    def record(self, step: str, n_after: int, reason: str, n_before: int | None = None) -> None:
        if n_before is None:
            n_before = self.rows[-1]["rows_after"] if self.rows else n_after
        self.rows.append(
            {"step": step, "rows_before": n_before, "rows_after": n_after, "dropped": n_before - n_after, "reason": reason}
        )

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.frame().to_csv(path, index=False)


def distance_matrix(e: np.ndarray, n: np.ndarray, boundaries: list[Boundary]) -> np.ndarray:
    """Signed distance from every sale to every boundary (N x B)."""
    return np.column_stack([b.signed_distance(e, n) for b in boundaries]) if boundaries else np.empty((len(e), 0))


def compatibility(genders: list[str], sex_aware: bool) -> np.ndarray:
    """B x B: does being inside boundary j count as an alternative for boundary i?

    Under the pre-registered rule, any other selected catchment does. With
    sex_aware, a girls' school and a boys' school are not alternatives for each
    other, because a place at one does nothing for a child eligible for the
    other. Mixed schools are alternatives for everyone.
    """
    g = [str(x).lower() for x in genders]
    B = len(g)
    if not sex_aware:
        return np.ones((B, B), dtype=bool)
    return np.array([[not ({g[i], g[j]} == {"girls", "boys"}) for j in range(B)] for i in range(B)])


def assign(
    txn_id: np.ndarray, D: np.ndarray, boundary_ids: list[str], max_abs_d: float = config.MAX_BANDWIDTH_M,
    log: StepLog | None = None, compatible: np.ndarray | None = None,
) -> pd.DataFrame:
    """Apply section 5 steps 6-8 of the pre-registration.

    6. A sale outside boundary A but inside some other selected catchment is
       not ineligible, so the pair (sale, A) is dropped.
    7. Each sale keeps only its nearest remaining boundary.
    8. Pairs further than the widest bandwidth are dropped.
    """
    N, B = D.shape
    compat = np.ones((B, B), dtype=bool) if compatible is None else compatible
    # For pair (i, a): number of boundaries j that contain sale i and count as
    # an alternative to a. D[i, a] <= 0 means a itself never contributes.
    alternatives = (D > 0).astype(np.int32) @ compat.T.astype(np.int32)
    within = np.abs(D) < max_abs_d
    contaminated = (D <= 0) & (alternatives >= 1)

    n_pairs_within = int(within.sum())
    valid = within & ~contaminated
    if log is not None:
        log.record("candidate pairs", n_pairs_within, f"sale-boundary pairs with |d| < {max_abs_d:g} m", n_before=n_pairs_within)
        log.record("contaminated outside", int(valid.sum()), "outside this boundary but inside another selected catchment")

    absD = np.where(valid, np.abs(D), np.inf)
    best = absD.argmin(axis=1)
    has = np.isfinite(absD[np.arange(N), best])
    rows = np.flatnonzero(has)
    cols = best[has]
    if log is not None:
        log.record("nearest boundary", len(rows), "each sale kept once, against its nearest valid boundary")

    near_main = (np.abs(D) < config.MAIN_BANDWIDTH_M).sum(axis=1)
    return pd.DataFrame(
        {
            "txn_id": txn_id[rows],
            "boundary_id": np.asarray(boundary_ids, dtype=object)[cols],
            "d_signed_m": D[rows, cols],
            "inside": D[rows, cols] > 0,
            # R8 drops sales within the main bandwidth of two or more boundaries.
            "n_boundaries_within_main_h": near_main[rows],
        }
    )


def frame_sha256(df: pd.DataFrame) -> str:
    """Content hash independent of the parquet writer's metadata."""
    h = hashlib.sha256()
    h.update(",".join(df.columns).encode())
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()
