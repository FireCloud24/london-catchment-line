"""Tests for the analysis library. Plain unittest, no data downloads needed.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import shapely

from line54 import catchments, config, density, geo, grades, lock, rdd, sample
from tests.synthetic import make_sample


class TestPostcodes(unittest.TestCase):
    CASES = ["sw1a 1aa", "SW1A1AA", "SW1A  1AA", " n1 9gu ", "E1W 1AA", "M1 1AE", "b33 8th", "", "AB1"]

    def test_python_rule(self):
        self.assertEqual(geo.normalise_postcode("sw1a  1aa"), "SW1A 1AA")
        self.assertEqual(geo.normalise_postcode("N19GU"), "N1 9GU")
        self.assertIsNone(geo.normalise_postcode("AB1"))

    def test_sql_matches_python(self):
        """Ingestion joins in SQL; the two rules must never disagree."""
        con = duckdb.connect()
        for pc in self.CASES:
            sql = con.execute(f"SELECT {geo.normalise_postcode_sql('x')} FROM (SELECT ?::VARCHAR AS x)", [pc]).fetchone()[0]
            self.assertEqual(sql, geo.normalise_postcode(pc), pc)


class TestGeometry(unittest.TestCase):
    def test_refuses_degrees(self):
        with self.assertRaises(ValueError):
            geo.require_projected("EPSG:4326")
        geo.require_projected("EPSG:27700")

    def test_circle_sign_convention(self):
        d = geo.signed_distance_circle(np.array([530000.0, 531000.0]), np.array([180000.0, 180000.0]), 530000, 180000, 800)
        np.testing.assert_allclose(d, [800.0, -200.0])

    def test_polygon_agrees_with_circle(self):
        """Routes 1 and 3 must give the same answer as Route 2 for the same shape."""
        rng = np.random.default_rng(1)
        e = 530000 + rng.uniform(-1500, 1500, 500)
        n = 180000 + rng.uniform(-1500, 1500, 500)
        poly = shapely.Point(530000, 180000).buffer(900, quad_segs=256)
        np.testing.assert_allclose(
            geo.signed_distance_polygon(e, n, poly), geo.signed_distance_circle(e, n, 530000, 180000, 900), atol=0.1
        )


class TestEstimator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = make_sample(tau=0.08, seed=42)
        cls.null = make_sample(tau=0.0, seed=7)

    def test_recovers_planted_effect(self):
        r = rdd.fit(self.df, 400)
        self.assertLess(r.ci_low, 0.08)
        self.assertGreater(r.ci_high, 0.08)
        self.assertLess(r.p_value, 0.001)
        self.assertEqual(r.df_inference, 19)

    def test_null_is_null(self):
        r = rdd.fit(self.null, 400)
        self.assertLess(r.ci_low, 0.0)
        self.assertGreater(r.ci_high, 0.0)

    def test_placebo_cutoffs_find_nothing(self):
        for c in config.PLACEBO_CUTOFFS_M:
            side = "inside" if c > 0 else "outside"
            r = rdd.fit(self.df, 250, cutoff=c, side=side)
            self.assertTrue(r.ci_low < 0 < r.ci_high, f"placebo at {c} m: {r.tau:.3f} [{r.ci_low:.3f}, {r.ci_high:.3f}]")

    def test_placebo_side_restriction(self):
        """Without the side restriction, the real jump leaks into a nearby placebo."""
        r = rdd.fit(self.df, 400, cutoff=250, side="inside")
        self.assertEqual(r.n_outside + r.n_inside, r.n_obs)
        w = self.df[(self.df.d_signed_m > 0) & ((self.df.d_signed_m - 250).abs() < 400)]
        self.assertEqual(r.n_obs, len(w))

    def test_donut_and_quadratic_stable(self):
        for kw in ({"donut": 50.0}, {"poly": 2}):
            r = rdd.fit(self.df, 400, **kw)
            self.assertTrue(r.ci_low < 0.08 < r.ci_high, kw)

    def test_boundary_slopes(self):
        r = rdd.fit(self.df, 400, boundary_slopes=True)
        self.assertTrue(r.ci_low < 0.08 < r.ci_high)

    def test_cluster_se_matches_statsmodels(self):
        """The bootstrap's hand-written sandwich must equal statsmodels' CR1."""
        w = rdd._window(self.df, 400, 0.0, 0.0, None, "d_signed_m")
        X, _ = rdd.design(w, 1, rdd.MAIN_FE, False)
        y = w["log_price"].to_numpy()
        wt = rdd.triangular_weights(w["_x"].to_numpy(), 400)
        g = pd.factorize(w["boundary_id"])[0]
        Xa = X.to_numpy(dtype=float)
        beta = np.linalg.lstsq(Xa * np.sqrt(wt)[:, None], y * np.sqrt(wt), rcond=None)[0]
        k = list(X.columns).index("inside")
        mine = rdd.cluster_se(Xa, y - Xa @ beta, wt, g, k)
        self.assertAlmostEqual(mine, rdd.fit(self.df, 400).se, places=10)

    def test_wild_bootstrap(self):
        strong = rdd.fit(self.df, 400, bootstrap_draws=999)
        self.assertLess(strong.p_wild_bootstrap, 0.01)
        null = rdd.fit(self.null, 400, bootstrap_draws=999)
        self.assertGreater(null.p_wild_bootstrap, 0.05)

    def test_pounds_use_outside_median(self):
        r = rdd.fit(self.df, 400)
        self.assertAlmostEqual(r.pounds[0], np.expm1(r.tau) * r.median_price_outside)

    def test_bandwidth_sweep_covers_grid(self):
        sweep = rdd.bandwidth_sweep(self.df, grid=(150.0, 400.0, 750.0))
        self.assertEqual(sweep["bandwidth_m"].tolist(), [150.0, 400.0, 750.0])

    def test_binned_means_never_straddle_zero(self):
        b = rdd.binned_means(self.df, 400, 25)
        self.assertTrue(np.all(np.abs(b["mid_m"] % 25 - 12.5) < 1e-9))


class TestDensity(unittest.TestCase):
    def test_no_jump_without_sorting(self):
        d = make_sample(seed=3, sales_per_boundary=4000)["d_signed_m"].to_numpy()
        r = density.mccrary(d, config.DENSITY_BIN_M, config.DENSITY_BANDWIDTH_M)
        self.assertGreater(r.p_value, 0.05)

    def test_detects_bunching(self):
        d = make_sample(seed=3, sales_per_boundary=4000, bunching=0.5)["d_signed_m"].to_numpy()
        r = density.mccrary(d, config.DENSITY_BIN_M, config.DENSITY_BANDWIDTH_M)
        self.assertLess(r.p_value, 0.001)
        self.assertGreater(r.theta, 0)

    def test_histogram_zero_is_outside(self):
        mids, freq = density.histogram(np.array([-10.0, 0.0, 0.0, 5.0]), 10.0)
        self.assertEqual(dict(zip(mids, freq * 4 * 10)), {-15.0: 1.0, -5.0: 2.0, 5.0: 1.0})


class TestGrades(unittest.TestCase):
    def setUp(self):
        self.events = pd.DataFrame(
            {
                "urn": ["100", "100", "200"],
                "publication_date": pd.to_datetime(["2008-05-01", "2013-02-01", "2018-06-01"]),
                "grade": [2, 1, 2],
            }
        )
        # 200 is the academy that replaced 100 in 2014.
        self.links = pd.DataFrame({"URN": ["200", "100"], "LinkURN": ["100", "200"], "LinkType": ["Predecessor", "Successor"]})

    def test_predecessor_grade_carries_over(self):
        lineage = grades.predecessors("200", self.links)
        self.assertEqual(lineage, ["200", "100"])
        self.assertEqual(grades.grade_in_force(self.events, lineage, date(2016, 1, 1))[0], 1)
        self.assertEqual(grades.grade_in_force(self.events, lineage, date(2020, 1, 1))[0], 2)

    def test_publication_date_not_inspection_date(self):
        self.assertIsNone(grades.grade_in_force(self.events, ["100"], date(2008, 4, 30))[0])

    def test_events_from_real_layout(self):
        df = pd.DataFrame(
            {
                "URN": ["300"], "Publication date": ["01/03/2019"], "Overall effectiveness": ["9"],
                "Inspection number": ["X1"], "URN at time of previous inspection": ["299"],
                "Previous publication date": ["10/10/2012"], "Previous overall effectiveness": ["1"],
                "Previous inspection number": ["X0"],
            }
        )
        ev = grades.events_from_frame(df, "t")
        # Grade 9 (ungraded) is not an event; the previous graded one is.
        self.assertEqual(ev[["urn", "grade"]].values.tolist(), [["299", 1]])

    @staticmethod
    def _ev(rows):
        cols = ["urn", "publication_date", "grade", "inspection_number", "inspection_start", "role", "source"]
        df = pd.DataFrame(rows, columns=cols)
        df["publication_date"] = pd.to_datetime(df["publication_date"])
        df["inspection_start"] = pd.to_datetime(df["inspection_start"])
        return df

    def test_current_row_beats_back_reference_date(self):
        """URN 141499: a 2022 file copied the 2022 publication date onto the 2020 inspection."""
        ev = self._ev([
            ["141499", "2020-04-20", 3, "I2020", "2020-03-10", "current", "ytd_2020"],
            ["141499", "2022-05-17", 3, "I2020", "2020-03-10", "previous", "ytd_2022"],
            ["141499", "2022-05-17", 2, "I2022", "2022-03-29", "current", "ytd_2022"],
        ])
        out = grades.dedupe_events(ev)
        self.assertEqual(out[["publication_date", "grade"]].astype(str).values.tolist(),
                         [["2020-04-20", "3"], ["2022-05-17", "2"]])

    def test_same_day_publication_later_inspection_wins(self):
        """Chislehurst School for Girls: two reports published on 28 Feb 2018."""
        ev = self._ev([
            ["136467", "2018-02-28", 4, "A", "2017-05-23", "current", "f"],
            ["136467", "2018-02-28", 2, "B", "2017-12-12", "current", "f"],
        ])
        self.assertEqual(grades.dedupe_events(ev)["grade"].tolist(), [2])

    def test_true_conflict_raises(self):
        ev = self._ev([
            ["1", "2019-01-01", 1, "A", "2018-11-01", "current", "a"],
            ["1", "2019-01-01", 2, "B", "2018-11-01", "current", "b"],
        ])
        with self.assertRaises(ValueError):
            grades.dedupe_events(ev)

    def test_index_matches_frame_lookup(self):
        idx = grades.index_events(self.events)
        for on in (date(2010, 1, 1), date(2016, 1, 1), date(2020, 1, 1)):
            self.assertEqual(grades.grade_in_force(idx, ["200", "100"], on), grades.grade_in_force(self.events, ["200", "100"], on))


class TestCatchments(unittest.TestCase):
    def test_units(self):
        self.assertAlmostEqual(catchments.parse_published_distance("0.5 miles"), 804.672)
        self.assertEqual(catchments.parse_published_distance("1,254m"), 1254.0)
        self.assertEqual(catchments.parse_published_distance("1.25 km"), 1250.0)
        with self.assertRaises(ValueError):
            catchments.parse_published_distance("about a mile")

    def test_stability(self):
        k, med, cv = catchments.stability([1000, 1200, 1400, 1600])
        self.assertEqual((k, med), (4, 1300.0))
        self.assertAlmostEqual(cv, 0.1986, places=3)

    def test_year_matched_radius_uses_offer_day(self):
        b = catchments.Boundary("1", "reconstructed_radius", 0, 0, 1000, {2019: 900.0, 2020: 1100.0}, None, 2, None)
        self.assertIsNone(b.radius_for_sale(date(2019, 2, 28)))
        self.assertEqual(b.radius_for_sale(date(2019, 3, 1)), 900.0)
        self.assertEqual(b.radius_for_sale(date(2024, 1, 1)), 1100.0)

    def test_validation_catches_bad_rows(self):
        row = {c: "" for c in catchments.PROVENANCE_COLUMNS}
        row.update(urn="1", entry_year=2020, route="reconstructed_radius", cutoff_as_published="0.5 miles",
                   cutoff_m=800.0, status="verified", source_url="https://example.org")
        errs = catchments.validate(pd.DataFrame([row]))
        self.assertTrue(any("cutoff_m" in e for e in errs))  # 0.5 miles is 805 m
        self.assertTrue(any("verified_by" in e for e in errs))


class TestSampleAssembly(unittest.TestCase):
    def test_contaminated_and_nearest(self):
        # Sale 0: outside A (-100) but inside B (+300) -> A pair contaminated, keeps B.
        # Sale 1: outside A (-50) and outside B (-600) -> nearest valid is A.
        # Sale 2: inside A (+20) and inside B (+30) -> inside pairs never contaminated; nearest A.
        D = np.array([[-100.0, 300.0], [-50.0, -600.0], [20.0, 30.0]])
        log = sample.StepLog()
        out = sample.assign(np.array(["s0", "s1", "s2"]), D, ["A", "B"], log=log)
        self.assertEqual(dict(zip(out.txn_id, out.boundary_id)), {"s0": "B", "s1": "A", "s2": "A"})
        self.assertEqual(log.frame()["dropped"].tolist(), [0, 1, 2])

    def test_hash_is_content_based(self):
        df = pd.DataFrame({"a": [1, 2]})
        self.assertEqual(sample.frame_sha256(df), sample.frame_sha256(df.copy()))
        self.assertNotEqual(sample.frame_sha256(df), sample.frame_sha256(df.assign(a=[1, 3])))


class TestLock(unittest.TestCase):
    def test_lock_blocks_until_written_and_detects_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            prov, lk = Path(tmp) / "provenance.csv", Path(tmp) / "lock.json"
            prov.write_text("urn\n1\n")
            with self.assertRaises(lock.SelectionNotLocked):
                lock.require_lock(prov, lk)
            lock.write_lock("tester", ["1"], prov, lk)
            self.assertEqual(lock.require_lock(prov, lk)["selected_urns"], ["1"])
            prov.write_text("urn\n1\n2\n")
            with self.assertRaises(lock.SelectionNotLocked):
                lock.require_lock(prov, lk)

    def test_crlf_checkout_does_not_break_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            prov, lk = Path(tmp) / "provenance.csv", Path(tmp) / "lock.json"
            prov.write_bytes(b"urn\n1\n")
            lock.write_lock("tester", ["1"], prov, lk)
            prov.write_bytes(b"urn\r\n1\r\n")
            lock.require_lock(prov, lk)


class TestConfigMatchesPreregistration(unittest.TestCase):
    """Spot-check that the numbers in code are the numbers in the document."""

    def test_key_numbers_appear_in_document(self):
        text = (config.ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8")
        for needle in ["**400 m**", "**150**", "**≤ 0.25**", "**3**", "9,999", "**10**", "2020-01-01", "+250"]:
            self.assertIn(needle, text)
        self.assertEqual(config.MAIN_BANDWIDTH_M, 400.0)
        self.assertEqual(config.BANDWIDTH_GRID_M[0], 100.0)
        self.assertEqual(config.BANDWIDTH_GRID_M[-1], 750.0)


if __name__ == "__main__":
    unittest.main()
