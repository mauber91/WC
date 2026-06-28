#!/usr/bin/env python3
"""Walk-forward backtest comparing baseline Elo vs lagged PMSR xG-adjusted forecasts."""

from __future__ import annotations

import argparse
import json

from world_cup_api.db.session import SessionLocal
from world_cup_api.modeling.backtest import walk_forward_group_backtest, walk_forward_pmsr_backtest
from world_cup_api.modeling.pmsr_features import index_features_by_match, load_team_match_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament-id", type=int, default=1)
    parser.add_argument("--alpha-xg", type=float, default=0.08, help="xG net balance sensitivity")
    parser.add_argument(
        "--rolling-window",
        type=int,
        default=None,
        help="Prior matches per team to include (default: all prior group games)",
    )
    parser.add_argument("--features-only", action="store_true", help="Print feature summary and exit")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.features_only:
            features = load_team_match_features(db)
            by_match = index_features_by_match(features)
            print(
                json.dumps(
                    {
                        "team_match_rows": len(features),
                        "matches_with_reports": len(by_match),
                        "sample": [
                            {
                                "match_id": feature.match_id,
                                "match_number": feature.official_match_number,
                                "team_id": feature.team_id,
                                "possession_pct": feature.possession_pct,
                                "xg": feature.xg,
                                "goals": feature.goals,
                                "pressures": feature.pressures,
                            }
                            for feature in features[:4]
                        ],
                    },
                    indent=2,
                )
            )
            return

        baseline = walk_forward_group_backtest(db, tournament_id=args.tournament_id)
        comparison = walk_forward_pmsr_backtest(
            db,
            tournament_id=args.tournament_id,
            alpha_xg=args.alpha_xg,
            rolling_window=args.rolling_window,
        )
        print(
            json.dumps(
                {
                    "baseline_only": baseline.to_dict(),
                    "comparison": comparison.to_dict(),
                    "delta_log_loss": comparison.pmsr_adjusted.log_loss - comparison.baseline.log_loss,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
