"""One command from raw downloads to the headline figure.

    python -m pipeline.run              # everything, downloads included
    python -m pipeline.run --from 06    # after the selection is locked

Phases 06 onward refuse to run until catchments/selection_lock.json exists,
so on a fresh clone this stops after the screen with a message saying why.
"""
from __future__ import annotations

import argparse
import importlib
import sys

PHASES = [
    ("01", "pipeline.p01_download", []),
    ("02", "pipeline.p02_ingest_sales", None),
    ("03", "pipeline.p03_ingest_schools", None),
    ("04", "pipeline.p04_build_catchments", ["--statuses", "verified"]),
    ("05", "pipeline.p05_screen", ["--statuses", "verified"]),
    ("06", "pipeline.p06_assemble_sample", None),
    ("07", "pipeline.p07_estimate", None),
    ("08", "pipeline.p08_robustness", None),
    ("09", "pipeline.p09_figures", None),
    ("10", "pipeline.p10_writeup", None),
]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default="01")
    ap.add_argument("--to", dest="end", default="10")
    args = ap.parse_args(argv)
    for code, module, phase_args in PHASES:
        if not args.start <= code <= args.end:
            continue
        print(f"\n=== phase {code}: {module}", flush=True)
        mod = importlib.import_module(module)
        if phase_args is None:
            mod.main()
        else:
            mod.main(phase_args)


if __name__ == "__main__":
    sys.exit(main())
