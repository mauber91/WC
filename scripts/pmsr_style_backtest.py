#!/usr/bin/env python3
"""Backtest baseline vs rolling-xG form vs full PMSR style model."""

from __future__ import annotations

import argparse
import json

from world_cup_api.db.session import SessionLocal
from world_cup_api.modeling.backtest import walk_forward_style_backtest
from world_cup_api.modeling.pmsr_style import ensure_style_model, fit_style_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament-id", type=int, default=1)
    parser.add_argument("--alpha-xg", type=float, default=0.08, help="Rolling xG form sensitivity")
    parser.add_argument("--ridge-alpha", type=float, default=1.0, help="Ridge penalty for style models")
    parser.add_argument("--refit", action="store_true", help="Re-fit style ridge models before backtest")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.refit:
            fit_style_model(db, ridge_alpha=args.ridge_alpha)
        else:
            ensure_style_model(db)
        report = walk_forward_style_backtest(
            db,
            tournament_id=args.tournament_id,
            alpha_xg=args.alpha_xg,
        )
        print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    main()
